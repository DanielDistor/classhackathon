"""Uploading a logbook (POST /api/upload) combines it with Fleet A and Fleet B into one dataset
that every dashboard route serves (the Combined tab)."""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
import api  # noqa: E402
import qc  # noqa: E402

client = TestClient(api.app)
EXAMPLE = ROOT / "data" / "example_upload" / "example_logbook.xlsx"
SHEETS = pd.read_excel(EXAMPLE, sheet_name=None)


def post(name: str, raw: bytes):
    return client.post("/api/upload", files={"file": (name, raw)})


def workbook(**sheets: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xl:
        for name, df in sheets.items():
            df.to_excel(xl, sheet_name=name, index=False)
    return buf.getvalue()


@pytest.fixture(scope="module")
def uploaded():
    r = post(EXAMPLE.name, EXAMPLE.read_bytes())
    assert r.status_code == 200, r.text
    return r.json()


def test_example_is_a_full_fleet_like_the_test_data():
    assert set(SHEETS) == {"README", "flights", "components", "maintenance", "replace_at", "fleet_reference"}
    assert list(SHEETS["flights"].columns) == list(pd.read_csv(ROOT / "data" / "fleet" / "flights.csv").columns)
    assert len(SHEETS["flights"]) == 3000 and SHEETS["flights"]["drone_id"].nunique() == 10


def test_upload_combines_both_fleets_and_the_logbook(uploaded):
    assert uploaded["n_drones"] == 30 and uploaded["n_flights"] == 9000
    assert {s["prefix"]: s["n_drones"] for s in uploaded["sources"]} == {"A": 10, "B": 10, "U": 10}
    assert uploaded["notes"] == []
    ds = uploaded["dataset"]
    for path in ("/api/fleet", "/api/drones/A01", "/api/drones/B10", "/api/drones/U05", "/api/reliability", "/api/cost"):
        r = client.get(f"{path}?dataset={ds}")
        assert r.status_code == 200, (path, r.text)


def test_relabelling_keeps_every_part_and_flight(uploaded):
    d = api.fleet(uploaded["dataset"])
    n = {k: sum(len(pd.read_csv(ROOT / "app" / "data" / ds / f"{k}.csv")) for ds in ("fleet", "fleet_b"))
         for k in ("flights", "components", "maintenance")}
    assert len(d["flights"]) == n["flights"] + len(SHEETS["flights"])
    assert len(d["components"]) == n["components"] + len(SHEETS["components"])
    assert d["flights"]["flight_id"].is_unique and d["components"]["component_id"].is_unique
    assert set(d["flights"]["drone_id"].str[0]) == {"A", "B", "U"}
    # one drone's readings are the same numbers before and after renaming
    mine = SHEETS["flights"][SHEETS["flights"]["drone_id"] == "D-03"]["vibration_rms"].to_numpy()
    assert (d["flights"][d["flights"]["drone_id"] == "U03"]["vibration_rms"].to_numpy() == mine).all()


def test_combined_weibull_pools_every_part(uploaded):
    fits = {f["component_type"]: f for f in client.get(f"/api/reliability?dataset={uploaded['dataset']}").json()["fits"]}
    comps = api.fleet(uploaded["dataset"])["components"]
    direct = qc.fit_by_type(comps).set_index("component_type")
    for t, f in fits.items():
        assert f["n"] == direct.loc[t, "n"] and f["b10"] == pytest.approx(direct.loc[t, "b10"], rel=1e-5)


def test_maintenance_sheet_is_optional():
    r = post("min.xlsx", workbook(flights=SHEETS["flights"], components=SHEETS["components"]))
    assert r.status_code == 200, r.text
    assert len(r.json()["notes"]) == 1
    assert client.get(f"/api/fleet?dataset={r.json()['dataset']}").status_code == 200


def test_the_test_fleets_are_unchanged_by_an_upload(uploaded):
    assert client.get("/api/fleet").json()["n_drones"] == 10
    assert all(r["drone_id"].startswith("D-") for r in client.get("/api/fleet?dataset=fleet_b").json()["status"])


def test_refuses_what_the_tool_cannot_use():
    assert post("notes.txt", b"hello").status_code == 422
    assert post("broken.xlsx", b"not a workbook").status_code == 422
    r = post("no_parts.xlsx", workbook(flights=SHEETS["flights"]))
    assert r.status_code == 422 and "components" in r.json()["detail"]
    bad = SHEETS["flights"].drop(columns=["vibration_rms"])
    r = post("bad.xlsx", workbook(flights=bad, components=SHEETS["components"]))
    assert r.status_code == 422 and "vibration_rms" in r.json()["detail"]
    assert client.get("/api/fleet?dataset=upload-nothere").status_code == 422
