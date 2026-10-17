"""Tests for the control-chart statistics in app/qc.py (CONTRACT task H-03, Stage 2).

Three kinds of check, as SPEC.md section 4 asks:
  1. known answers worked out by hand (SPEC section 4),
  2. degenerate inputs that must be refused, not turned into a number,
  3. the planted signals in data/ found where data/simulate.py planted them.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.qc import (SPC_RULES, add_derived, chart_margin, check_flights, drone_series, ewma_chart,
                    fleet_status, imr_chart, imr_limits, spc_rules)

DATA = Path(__file__).resolve().parents[1] / "data"


# ---------------------------------------------------------------- 1. known answers

def test_imr_limits_known_answer():
    # By hand: moving ranges 2, 1, 2, 1 -> MRbar 1.5; sigma = 1.5 / 1.128 = 1.3298;
    # limits 11.6 +/- 3 * 1.3298; MR UCL = 3.267 * 1.5.
    lim = imr_limits([10, 12, 11, 13, 12], n_baseline=5, min_baseline=2)
    assert lim.center == pytest.approx(11.6)
    assert lim.mr_bar == pytest.approx(1.5)
    assert lim.sigma_hat == pytest.approx(1.3298, abs=1e-4)
    assert lim.ucl == pytest.approx(15.589, abs=1e-3)
    assert lim.lcl == pytest.approx(7.611, abs=1e-3)
    assert lim.mr_ucl == pytest.approx(4.901, abs=1e-3)


def test_imr_limits_use_only_the_baseline():
    # A huge point after the baseline must not move the limits.
    base = [10, 12, 11, 13, 12]
    a = imr_limits(base, n_baseline=5, min_baseline=2)
    b = imr_limits(base + [100], n_baseline=5, min_baseline=2)
    assert a == b


def test_imr_chart_flags_point_beyond_limit():
    chart = imr_chart([10, 12, 11, 13, 12, 16], n_baseline=5, min_baseline=2)
    assert list(chart["signal_i"]) == [False] * 5 + [True]   # 16 > UCL 15.589
    assert chart["mr"].isna().iloc[0]                          # no moving range for point 1
    assert list(chart["t"]) == [1, 2, 3, 4, 5, 6]


def test_ewma_known_answer():
    # By hand with mu0 = 10, sigma = 1, lambda = 0.2, L = 3:
    # z1 = 0.2*11 + 0.8*10 = 10.2;  z2 = 0.2*12 + 0.8*10.2 = 10.56
    # half-width_t = 3 * sqrt(0.2/1.8 * (1 - 0.8^(2t))) -> 0.600, 0.7684
    ch = ewma_chart([11, 12], lam=0.2, L=3, mu0=10, sigma=1)
    assert list(ch["z"].round(4)) == [10.2, 10.56]
    assert list((ch["ucl"] - 10).round(4)) == [0.6, 0.7684]
    assert list((10 - ch["lcl"]).round(4)) == [0.6, 0.7684]
    assert not ch["signal"].any()


def test_ewma_limits_approach_asymptote():
    ch = ewma_chart([10.0] * 200, lam=0.2, L=3, mu0=10, sigma=1)
    assert ch["ucl"].iloc[-1] - 10 == pytest.approx(3 * math.sqrt(0.2 / 1.8), abs=1e-9)  # 1.000


def test_ewma_matches_pandas_cross_check():
    # Independent implementation: pandas ewm, seeded with mu0 as the first value.
    rng = np.random.default_rng(1)
    x = rng.normal(5, 2, 60)
    ch = ewma_chart(x, lam=0.3, L=2.7, mu0=5, sigma=2)
    ref = pd.Series(np.r_[5.0, x]).ewm(alpha=0.3, adjust=False).mean().to_numpy()[1:]
    np.testing.assert_allclose(ch["z"], ref, rtol=1e-12)


def test_ewma_estimates_mu0_and_sigma_from_baseline():
    x = [10, 12, 11, 13, 12, 11, 12]
    ch = ewma_chart(x, n_baseline=5, min_baseline=2)
    lim = imr_limits(x, n_baseline=5, min_baseline=2)
    assert ch["center"].iloc[0] == pytest.approx(lim.center)
    t1_half = 3 * lim.sigma_hat * math.sqrt(0.2 / 1.8 * (1 - 0.8 ** 2))
    assert ch["ucl"].iloc[0] - lim.center == pytest.approx(t1_half)


def test_add_derived_formulas():
    f = pd.DataFrame({"motor_temp_max_c": [40.0, None], "ambient_temp_c": [20.0, 15.0],
                      "voltage_start_v": [25.0, 25.0], "voltage_end_v": [21.0, 22.0],
                      "flight_min": [20.0, 10.0]})
    out = add_derived(f)
    assert out["temp_rise_c"].iloc[0] == pytest.approx(20.0)
    assert math.isnan(out["temp_rise_c"].iloc[1])            # blank reading stays blank
    assert list(out["sag_rate_v_per_min"]) == pytest.approx([0.2, 0.3])
    assert "temp_rise_c" not in f.columns                     # input not modified


# ---------------------------------------------------------------- 2. degenerate cases

def test_constant_data_is_refused():
    with pytest.raises(ValueError, match="no variation"):
        imr_limits([5.0] * 30)
    with pytest.raises(ValueError, match="no variation"):
        ewma_chart([5.0] * 30)


def test_single_point_is_refused():
    with pytest.raises(ValueError):
        imr_limits([5.0], n_baseline=1, min_baseline=1)


def test_short_baseline_is_refused():
    with pytest.raises(ValueError, match="at least 20"):
        imr_chart(list(range(19)))


def test_missing_values_are_refused():
    with pytest.raises(ValueError, match="finite"):
        imr_limits([1.0, 2.0, float("nan"), 3.0], n_baseline=4, min_baseline=2)


@pytest.mark.parametrize("lam, L", [(0, 3), (1.5, 3), (0.2, 0)])
def test_bad_ewma_parameters_are_refused(lam, L):
    with pytest.raises(ValueError):
        ewma_chart([1.0, 2.0, 3.0], lam=lam, L=L, mu0=2, sigma=1)


def test_bad_known_sigma_is_refused():
    with pytest.raises(ValueError):
        ewma_chart([1.0, 2.0], mu0=1, sigma=0)


# ---------------------------------------------------------------- 3. the simulated fleet (data/fleet)

def load(dataset: str = "fleet") -> pd.DataFrame:
    return add_derived(pd.read_csv(DATA / dataset / "flights.csv"))


def test_drone_series_unknown_drone_is_refused():
    with pytest.raises(ValueError, match="no flights"):
        drone_series(load(), "D-99", "temp_rise_c")


# ---------------------------------------------------------------- fleet status (go / watch / ground)

def synthetic_flights(n=60, spike_at=None, drone="D-01", spike=9.0):
    """A steady drone; optionally one vibration spike (to `spike` m/s²) at flight `spike_at`."""
    rng = np.random.default_rng(7)
    vib = 3 + rng.normal(0, 0.2, n)
    if spike_at:
        vib[spike_at - 1] = spike
    return pd.DataFrame({
        "flight_id": [f"F-01-{k:03d}" for k in range(1, n + 1)],
        "drone_id": drone,
        "datetime": pd.date_range("2026-09-01", periods=n, freq="h").strftime("%Y-%m-%dT%H:%M"),
        "flight_min": 20.0,
        "ambient_temp_c": 15 + rng.normal(0, 2, n),
        "motor_temp_max_c": 0.0,  # filled below
        "voltage_start_v": 25.15,
        "voltage_end_v": 25.15 - 20 * (0.17 + rng.normal(0, 0.008, n)),
        "vibration_rms": vib,
        "inflight_event": "none",
    }).assign(motor_temp_max_c=lambda d: d.ambient_temp_c + 18 + rng.normal(0, 1.2, n))


def test_fleet_status_go_when_nothing_signals():
    st = fleet_status(synthetic_flights()).set_index("drone_id")
    assert st.loc["D-01", "status"] == "go"


def test_fleet_status_ground_when_latest_flight_is_out():
    st = fleet_status(synthetic_flights(spike_at=60)).set_index("drone_id")
    assert st.loc["D-01", "status"] == "ground"
    assert "vibration" in st.loc["D-01", "reason"] and "flight 60" in st.loc["D-01", "reason"]


def test_fleet_status_watch_when_recent_signal_cleared():
    # a ~4.5 sigma spike 9 flights ago: its EWMA effect has decayed below the limit by now,
    # but the I-chart hit is within the last 10 flights and nobody logged an inspection
    st = fleet_status(synthetic_flights(spike_at=51, spike=3.9)).set_index("drone_id")
    assert st.loc["D-01", "status"] == "watch"
    assert "flight 51" in st.loc["D-01", "reason"] and "not yet inspected" in st.loc["D-01", "reason"]


def test_fleet_status_too_few_flights():
    st = fleet_status(synthetic_flights(n=10)).set_index("drone_id")
    assert st.loc["D-01", "status"] == "not enough data"


def test_check_flights_accepts_bundled_data():
    f = pd.read_csv(DATA / "fleet" / "flights.csv")
    assert check_flights(f) is f


def test_check_flights_names_missing_columns():
    f = pd.read_csv(DATA / "fleet" / "flights.csv").drop(columns=["vibration_rms"])
    with pytest.raises(ValueError, match="vibration_rms"):
        check_flights(f)


def test_check_flights_refuses_text_in_numbers():
    f = pd.read_csv(DATA / "fleet" / "flights.csv").astype({"vibration_rms": str})
    f.loc[0, "vibration_rms"] = "high"
    with pytest.raises(ValueError, match="numbers"):
        check_flights(f)


# ---------------------------------------------------------------- health (room left before a limit)

def test_chart_margin_known_answers():
    # center 10, limits 7 and 13: the room on each side is 3
    assert chart_margin(10, 10, 7, 13) == pytest.approx(1.0)     # at the center
    assert chart_margin(11.5, 10, 7, 13) == pytest.approx(0.5)   # halfway to the UCL
    assert chart_margin(7.75, 10, 7, 13) == pytest.approx(0.25)  # 3/4 of the way to the LCL
    assert chart_margin(13, 10, 7, 13) == pytest.approx(0.0)     # on the limit
    assert chart_margin(20, 10, 7, 13) == 0.0                    # beyond it: never negative


def test_chart_margin_refuses_zero_width_limits():
    with pytest.raises(ValueError):
        chart_margin(10, 10, 10, 10)


def test_health_is_zero_when_latest_reading_is_out():
    st = fleet_status(synthetic_flights(spike_at=60)).set_index("drone_id")
    assert st.loc["D-01", "health"] == 0.0
    assert st.loc["D-01", "health_driver"] == "vibration"


def test_health_is_high_for_a_steady_drone():
    st = fleet_status(synthetic_flights()).set_index("drone_id")
    assert 0.3 < st.loc["D-01", "health"] <= 1.0


def test_health_missing_when_not_enough_data():
    st = fleet_status(synthetic_flights(n=10)).set_index("drone_id")
    assert math.isnan(st.loc["D-01", "health"])


# ---------------------------------------------------------------- 4. 8 SPC rules & ground vs watch split

def test_spc_rules_known_answers_all_8_rules():
    # Center = 0, sigma = 1 so values are z-scores directly.
    assert len(SPC_RULES) == 8

    # Rule 1: 1 point beyond 3 sigma
    r1 = spc_rules([0.0, 2.9, 3.1, -3.2], center=0.0, sigma=1.0)
    assert list(r1["rule_1"]) == [False, False, True, True]
    assert list(r1["signal_ground"]) == [False, False, True, True]

    # Rule 2: 9 points in a row on the same side of center line
    r2 = spc_rules([0.2] * 8 + [0.2, -0.2], center=0.0, sigma=1.0)
    assert list(r2["rule_2"]) == [False] * 8 + [True, False]
    assert r2["signal_watch"].iloc[8] and not r2["signal_ground"].iloc[8]

    # Rule 3: 6 points in a row steadily increasing or decreasing
    r3 = spc_rules([0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.4], center=0.0, sigma=1.0)
    assert list(r3["rule_3"]) == [False] * 5 + [True, False]

    # Rule 4: 14 points in a row alternating up and down
    alt = [0.2 if i % 2 == 0 else -0.2 for i in range(15)]
    r4 = spc_rules(alt, center=0.0, sigma=1.0)
    assert list(r4["rule_4"]) == [False] * 13 + [True, True]

    # Rule 5: 2 of 3 points beyond 2 sigma on the same side
    r5 = spc_rules([0.0, 2.2, 0.5, 2.3, -2.5], center=0.0, sigma=1.0)
    assert list(r5["rule_5"]) == [False, False, False, True, False]

    # Rule 6: 4 of 5 points beyond 1 sigma on the same side
    r6 = spc_rules([1.2, 1.3, 0.2, 1.4, 1.5], center=0.0, sigma=1.0)
    assert list(r6["rule_6"]) == [False, False, False, False, True]

    # Rule 7: 15 points in a row within 1 sigma of center line
    r7 = spc_rules([0.1, -0.1] * 7 + [0.2, 1.5], center=0.0, sigma=1.0)
    assert list(r7["rule_7"]) == [False] * 14 + [True, False]

    # Rule 8: 8 points in a row beyond 1 sigma on either side
    r8 = spc_rules([1.5, -1.5] * 4 + [0.2], center=0.0, sigma=1.0)
    assert list(r8["rule_8"]) == [False] * 7 + [True, False]
    assert r8["rules_triggered"].iloc[7] == "8"


def test_spc_rules_refuses_bad_sigma():
    with pytest.raises(ValueError):
        spc_rules([1.0, 2.0], center=0.0, sigma=0.0)


def test_fleet_status_watch_on_spc_rules_2_to_8():
    # The last 14 readings alternate up and down around the center, well inside +/- 3 sigma
    # (no rule 1) and with no shift in the mean (no EWMA signal), but they trigger rule 4
    # (14 points in a row alternating) -> "watch", not "ground".
    df = synthetic_flights(n=65)
    center = df["vibration_rms"].iloc[:50].mean()
    df.loc[51:, "vibration_rms"] = [center + (0.15 if i % 2 else -0.15) for i in range(14)]
    st = fleet_status(df).set_index("drone_id")
    assert st.loc["D-01", "status"] == "watch"
    assert "rule 4" in st.loc["D-01", "reason"]
