"""The upload route (POST /api/upload) on the example workbook, and on files it must refuse."""

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

client = TestClient(api.app)
EXAMPLE = ROOT / "data" / "example_upload" / "example_logbook.xlsx"


def post(name: str, raw: bytes):
    return client.post("/api/upload", files={"file": (name, raw)})


@pytest.fixture(scope="module")
def example():
    r = post(EXAMPLE.name, EXAMPLE.read_bytes())
    assert r.status_code == 200, r.text
    return r.json()


def test_example_finds_exactly_the_planted_problems(example):
    st = {r["drone_id"]: r for r in example["status"]}
    assert st["D-01"]["status"] == "go"                                   # healthy
    assert st["D-02"]["status"] == "ground" and "vibration" in st["D-02"]["reason"]          # prop strike, flight 64
    assert st["D-03"]["status"] == "ground" and "motor temperature" in st["D-03"]["reason"]  # motor wear from flight 50
    assert "voltage" not in st["D-02"]["reason"] + st["D-03"]["reason"]  # nothing else flagged
    assert example["n_flights"] == 210 and example["n_drones"] == 3


def test_example_charts_and_parts(example):
    vib = [c for c in example["charts"]["D-02"] if c["column"] == "vibration_rms"][0]
    strike = [p for p in vib["points"] if p["flight_no"] == 64][0]
    assert strike["value"] > strike["ucl"]                               # the strike is beyond 3 sigma
    assert {f["component_type"] for f in example["fits"]} == {"motor", "propeller", "battery"}
    due = [p for p in example["plan"] if p["due"]]
    assert [(p["drone_id"], p["component_type"], p["position"]) for p in due] == [("D-01", "propeller", 1)]
    assert example["notes"] == []                                         # every sheet was used


def test_flights_csv_alone_works_with_notes():
    flights = pd.read_excel(EXAMPLE, sheet_name="flights")
    r = post("flights.csv", flights.to_csv(index=False).encode())
    assert r.status_code == 200
    d = r.json()
    assert d["fits"] == [] and len(d["notes"]) == 2                       # no maintenance, no components


def test_refuses_bad_files():
    assert post("notes.txt", b"hello").status_code == 422
    assert post("broken.xlsx", b"not a workbook").status_code == 422
    r = post("x.csv", b"a,b\n1,2\n")
    assert r.status_code == 422 and "missing column" in r.json()["detail"]
    buf = io.BytesIO()
    pd.DataFrame({"x": [1]}).to_excel(buf, sheet_name="other", index=False)
    r = post("no_flights.xlsx", buf.getvalue())
    assert r.status_code == 422 and "flights" in r.json()["detail"]


def test_constant_readings_give_no_limits_not_a_number():
    flights = pd.read_excel(EXAMPLE, sheet_name="flights")
    flights["vibration_rms"] = 3.0                                        # no variation: limits undefined
    r = post("flat.csv", flights.to_csv(index=False).encode())
    assert r.status_code == 200
    assert all(r["status"] == "not enough data" for r in r.json()["status"])
