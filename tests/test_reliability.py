"""Tests for the Weibull reliability statistics in app/qc.py (CONTRACT task H-03, Stage 4).

Known answers by hand, a recovery check on simulated lives with censoring,
a cross-check against scipy, degenerate inputs, and the planted bad battery lot.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from app.qc import b_life, compare_lots, fit_by_type, km_curve, parts_past_b10, reliability, weibull_fit

DATA = Path(__file__).resolve().parents[1] / "data"


# ---------------------------------------------------------------- known answers

def test_b10_known_answer():
    # B10 = eta * (-ln 0.9)^(1/beta) = 100 * 0.10536^0.5 = 32.459
    assert b_life(beta=2, eta=100) == pytest.approx(32.459, abs=1e-3)


def test_reliability_at_eta_is_e_to_minus_one():
    # R(t) = exp(-(t/eta)^beta); at t = eta, R = exp(-1) whatever the shape
    assert reliability(250, beta=3.3, eta=250) == pytest.approx(math.exp(-1))
    assert reliability(0, beta=2, eta=100) == pytest.approx(1.0)


def test_b_life_and_reliability_agree():
    t = b_life(beta=2.5, eta=400, p=0.10)
    assert reliability(t, beta=2.5, eta=400) == pytest.approx(0.90)


# ---------------------------------------------------------------- recovery and cross-check

def simulated(n=2000, beta=2.5, eta=300, seed=11):
    """Weibull lives with independent random censoring (about 30% censored)."""
    rng = np.random.default_rng(seed)
    t = eta * rng.weibull(beta, n)
    c = rng.uniform(0, 900, n)
    return np.minimum(t, c), (t <= c).astype(int)


def test_fit_recovers_true_parameters_with_censoring():
    life, status = simulated()
    assert 0.2 < 1 - status.mean() < 0.4                    # about 30% censored
    fit = weibull_fit(life, status)
    assert fit.beta == pytest.approx(2.5, abs=0.15)
    assert fit.eta == pytest.approx(300, rel=0.05)
    assert fit.beta_lo < 2.5 < fit.beta_hi
    assert fit.eta_lo < 300 < fit.eta_hi
    assert fit.n == 2000 and fit.n_failed == int(status.sum())


def test_fit_matches_scipy_when_nothing_is_censored():
    life = 300 * np.random.default_rng(5).weibull(2.0, 400)
    fit = weibull_fit(life, np.ones_like(life, dtype=int))
    beta_s, _, eta_s = stats.weibull_min.fit(life, floc=0)   # an independent implementation
    assert fit.beta == pytest.approx(beta_s, rel=1e-3)
    assert fit.eta == pytest.approx(eta_s, rel=1e-3)


def test_ignoring_censoring_would_bias_life_down():
    # Why censoring matters: dropping the survivors makes parts look short-lived.
    life, status = simulated()
    honest = weibull_fit(life, status)
    naive = weibull_fit(life[status == 1], np.ones(int(status.sum()), dtype=int))
    assert naive.eta < honest.eta


# ---------------------------------------------------------------- degenerate inputs

def test_all_censored_is_refused():
    with pytest.raises(ValueError, match="failures"):
        weibull_fit([10, 20, 30, 40], [0, 0, 0, 0])


def test_too_few_failures_is_refused():
    with pytest.raises(ValueError, match="at least 3 failures"):
        weibull_fit([10, 20, 30, 40, 50], [1, 1, 0, 0, 0])


@pytest.mark.parametrize("life", [[10, -5, 30, 40], [10, 0, 30, 40], [10, float("nan"), 30, 40]])
def test_non_positive_or_missing_life_is_refused(life):
    with pytest.raises(ValueError):
        weibull_fit(life, [1, 1, 1, 1])


def test_status_must_be_0_or_1_and_match_length():
    with pytest.raises(ValueError):
        weibull_fit([10, 20, 30], [1, 2, 1])
    with pytest.raises(ValueError):
        weibull_fit([10, 20, 30], [1, 1])


# ---------------------------------------------------------------- the planted data

def comps(dataset):
    return pd.read_csv(DATA / dataset / "components.csv")


def test_problem_fleet_battery_lot_b_is_short_lived():
    lots = compare_lots(comps("problem_fleet"), "battery").set_index("lot")
    assert lots.loc["B", "eta"] == pytest.approx(240, rel=0.10)   # planted: 240 cycles
    assert lots.loc["A", "eta"] > lots.loc["B", "eta"] * 1.3
    assert lots.loc["B", "b10"] < lots.loc["A", "b10"]
    assert lots.loc["B", "eta_hi"] < lots.loc["A", "eta_lo"]      # the intervals don't overlap


def test_healthy_batteries_have_no_bad_lot():
    lots = compare_lots(comps("healthy"), "battery").set_index("lot")
    fitted = lots.dropna(subset=["eta"])
    assert (fitted["eta"] > 330).all()                             # planted: 400 for every lot


def test_fit_by_type_units_and_planted_motor_life():
    by = fit_by_type(comps("healthy")).set_index("component_type")
    assert set(by.index) == {"motor", "propeller", "battery"}
    assert by.loc["battery", "unit"] == "charge cycles"
    assert by.loc["motor", "unit"] == "flight hours"
    assert by.loc["motor", "eta"] == pytest.approx(500, rel=0.10)  # planted: 500 h
    assert by.loc["propeller", "eta"] == pytest.approx(150, rel=0.10)


def test_parts_past_b10_are_in_service_and_older_than_b10():
    c = comps("healthy")
    by = fit_by_type(c)
    due = parts_past_b10(c, by)
    assert (due["end_date"].isna()).all()
    b10 = by.set_index("component_type")["b10"]
    assert (due["life_value"] > due["component_type"].map(b10)).all()


def test_km_known_answer():
    # lives 1, 2, 3 (all failed), 4 (censored): S = 3/4, then 3/4 * 2/3 = 1/2, then 1/2 * 1/2 = 1/4
    km = km_curve([2, 1, 4, 3], [1, 1, 0, 1])
    assert list(km["t"]) == [0, 1, 2, 3]
    assert list(km["survival"]) == pytest.approx([1, 0.75, 0.5, 0.25])


def test_km_matches_lifelines():
    from lifelines import KaplanMeierFitter
    life, status = simulated(n=300)
    km = km_curve(life, status)
    ref = KaplanMeierFitter().fit(life, status).survival_function_at_times(km["t"].to_numpy())
    np.testing.assert_allclose(km["survival"], ref.to_numpy(), rtol=1e-10)


def test_check_components_accepts_bundled_and_refuses_bad_status():
    from app.qc import check_components
    c = comps("healthy")
    assert check_components(c) is c
    bad = c.copy()
    bad.loc[0, "status"] = 2
    with pytest.raises(ValueError, match="status"):
        check_components(bad)
    with pytest.raises(ValueError, match="lot"):
        check_components(c.drop(columns=["lot"]))


# ---------------------------------------------------------------- replacement plan (flights and days left)

def tiny_fleet():
    """One drone: 40 flights of 30 min over 10 days (4 a day), one motor and one battery in service."""
    flights = pd.DataFrame({
        "flight_id": [f"F-01-{k:03d}" for k in range(1, 41)], "drone_id": "D-01",
        "datetime": pd.date_range("2026-09-01T08:00", periods=40, freq="6h").strftime("%Y-%m-%dT%H:%M"),
        "flight_min": 30.0,
    })
    comps_ = pd.DataFrame({
        "component_id": ["M-01-1-01", "B-01-1-01", "P-01-1-01", "M-01-2-01"],
        "drone_id": "D-01", "component_type": ["motor", "battery", "propeller", "motor"],
        "lot": "A", "end_date": [None, None, None, "2026-08-01"],
        "life_value": [100.0, 50.0, 80.0, 30.0], "status": [0, 0, 0, 1],
    })
    by = pd.DataFrame({"component_type": ["motor", "battery", "propeller"],
                       "unit": ["flight hours", "charge cycles", "flight hours"], "b10": [200.0, 150.0, 60.0]})
    return flights, comps_, by


def test_replacement_plan_known_answers():
    from app.qc import replacement_plan
    flights, comps_, by = tiny_fleet()
    plan = replacement_plan(comps_, flights, by).set_index("component_id")
    assert "M-01-2-01" not in plan.index                      # removed parts are not planned
    m = plan.loc["M-01-1-01"]
    # 200 h B10 - 100 h used = 100 h left; 30-min flights -> 200 flights; 4 flights a day -> 50 days
    assert m["remaining"] == pytest.approx(100)
    assert m["flights_left"] == pytest.approx(200)
    assert m["days_left"] == pytest.approx(50)
    assert m["pct_used"] == pytest.approx(50)
    b = plan.loc["B-01-1-01"]
    # 150 charges - 50 = 100 charges left; two batteries alternate, so 1 charge = 2 drone flights
    assert b["flights_left"] == pytest.approx(200)
    assert b["days_left"] == pytest.approx(50)
    p = plan.loc["P-01-1-01"]
    assert p["overdue"] and p["flights_left"] == pytest.approx(-40)   # 20 h past B10 = 40 flights


def test_replacement_plan_on_problem_fleet():
    from app.qc import replacement_plan
    c = comps("problem_fleet")
    f = pd.read_csv(DATA / "problem_fleet" / "flights.csv")
    plan = replacement_plan(c, f, fit_by_type(c))
    assert set(plan["component_id"]) == set(c.loc[c["end_date"].isna(), "component_id"])
    assert "D-07" not in set(plan["drone_id"])                # lost in its crash: nothing to replace
    assert plan["overdue"].equals(plan["remaining"] <= 0)
    assert plan.groupby("drone_id").size().max() == 10        # 4 motors, 4 props, 2 batteries
