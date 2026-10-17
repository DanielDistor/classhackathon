"""The API (app/api.py) returns exactly what qc.py computes, and refuses bad input (H-14)."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))  # api.py does "import qc", exactly as on Connect
import api  # noqa: E402
import qc  # noqa: E402

client = TestClient(api.app)
FLEET = ROOT / "app" / "data" / "fleet"


def test_health():
    assert client.get("/api/health").json() == {"status": "ok"}


def test_imr_known_answer():
    # [10, 12, 11, 13, 12] repeated 5 times: center 11.6, MR-bar = 19/12, sigma = MR-bar / 1.128
    r = client.post("/api/spc/imr", json={"values": [10, 12, 11, 13, 12] * 5, "n_baseline": 25}).json()
    assert r["center"] == pytest.approx(11.6)
    assert r["mr_bar"] == pytest.approx(19 / 24 * 2)
    assert r["sigma_hat"] == pytest.approx(r["mr_bar"] / 1.128)
    assert r["ucl"] == pytest.approx(11.6 + 3 * r["sigma_hat"])
    assert r["lcl"] == pytest.approx(11.6 - 3 * r["sigma_hat"])


@pytest.mark.parametrize("values", [[5.0] * 30, [1.0, 2.0, 3.0]])
def test_imr_refuses_degenerate(values):
    # constant data (no variation) and too few baseline points have no limits: 422, not a number
    r = client.post("/api/spc/imr", json={"values": values})
    assert r.status_code == 422
    assert "detail" in r.json()


def test_weibull_matches_qc_and_refuses_all_censored():
    life, status = [120, 340, 410, 95, 260, 500, 380, 210], [1, 1, 0, 1, 1, 0, 1, 1]
    r = client.post("/api/weibull", json={"life": life, "status": status}).json()
    direct = qc.weibull_fit(life, status)
    assert r["beta"] == pytest.approx(direct.beta)
    assert r["b10"] == pytest.approx(direct.b10)
    assert client.post("/api/weibull", json={"life": life, "status": [0] * 8}).status_code == 422


def test_fleet_view_matches_qc():
    d = client.get("/api/fleet").json()
    f = qc.add_derived(pd.read_csv(FLEET / "flights.csv"))
    m = pd.read_csv(FLEET / "maintenance.csv")
    ref = qc.fleet_reference(pd.read_csv(FLEET / "fleet_reference.csv"))
    st = qc.fleet_status(f, m, fleet=ref).set_index("drone_id")
    assert d["n_drones"] == 10 and d["n_flights"] == 300
    for row in d["status"]:
        assert row["status"] == st.loc[row["drone_id"], "status"]
        assert row["reason"] == st.loc[row["drone_id"], "reason"]
    tl = qc.maintenance_timeline(m)
    assert len(d["timeline"]) == len(tl)
    assert d["activity"]["special"] == int((tl["marker"] == "S").sum())
    assert len(d["plan"]) == 100  # 10 drones x 10 installed parts


def test_drone_view_charts_match_monitor_chart():
    d = client.get("/api/drones/D-05").json()
    f = qc.add_derived(pd.read_csv(FLEET / "flights.csv"))
    m = pd.read_csv(FLEET / "maintenance.csv")
    ref = qc.fleet_reference(pd.read_csv(FLEET / "fleet_reference.csv"))
    assert [c["column"] for c in d["charts"]] == [col for col, *_ in api.DRONE_CHARTS]
    for c in d["charts"]:
        s = qc.drone_series(f, "D-05", c["column"])
        resets = qc.reset_flights(m, "D-05", c["column"])
        ch = qc.monitor_chart(s["value"], s["flight_no"], resets, fleet=ref.get(c["column"]))
        assert len(c["points"]) == len(ch)
        assert c["resets"] == resets
        assert sum(p["signal"] for p in c["points"]) == int(ch["signal"].sum())
        assert c["summary"]["ucl"] == pytest.approx(ch["ucl"].iloc[-1])
    assert len(d["parts"]) == 10


def test_unknown_drone_is_404():
    assert client.get("/api/drones/D-99").status_code == 404


def test_reliability_view_matches_fit_by_type():
    d = client.get("/api/reliability").json()
    fits = qc.fit_by_type(pd.read_csv(FLEET / "components.csv")).set_index("component_type")
    assert {f["component_type"] for f in d["fits"]} == set(fits.index)
    for f in d["fits"]:
        assert f["b10"] == pytest.approx(fits.loc[f["component_type"], "b10"], rel=1e-5)
    for c in d["curves"]:
        assert c["r"][0] == pytest.approx(1.0) and c["km"][0]["survival"] == pytest.approx(1.0)


def test_guide_counts_the_answer_key():
    g = client.get("/api/guide").json()
    assert len(g["events"]) == len(pd.read_csv(FLEET / "answer_key.csv"))
    assert len(g["example_flights"]) == 3


def test_dashboard_is_served_at_root():
    # The React build (web/ -> app/static/) is committed so Connect can serve it.
    r = client.get("/")
    assert r.status_code == 200
    assert '<div id="root"></div>' in r.text
