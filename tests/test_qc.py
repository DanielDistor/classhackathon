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

from app.qc import add_derived, drone_series, ewma_chart, imr_chart, imr_limits

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


# ---------------------------------------------------------------- 3. planted signals in data/

def load(dataset: str) -> pd.DataFrame:
    return add_derived(pd.read_csv(DATA / dataset / "flights.csv"))


def first_flight(series: pd.DataFrame, signal: pd.Series):
    hits = series.loc[signal.to_numpy(), "flight_no"]
    return int(hits.iloc[0]) if len(hits) else None


def test_motor_drift_ewma_catches_d07_before_crash():
    s = drone_series(load("motor_drift"), "D-07", "temp_rise_c")
    ewma = ewma_chart(s["value"])
    imr = imr_chart(s["value"])
    assert first_flight(s, ewma["signal"]) == 74          # drift starts after 60, crash at 95
    assert first_flight(s, imr["signal_i"]) == 83         # a raw chart is 9 flights later
    assert s["flight_no"].max() == 94                     # crash flight has no temperature


def test_motor_drift_i_chart_catches_d03_prop_strike():
    s = drone_series(load("motor_drift"), "D-03", "vibration_rms")
    imr = imr_chart(s["value"])
    assert list(s.loc[imr["signal_i"].to_numpy(), "flight_no"]) == [80]


def test_healthy_d07_stays_in_control():
    s = drone_series(load("healthy"), "D-07", "temp_rise_c")
    assert not ewma_chart(s["value"])["signal"].any()


def test_drone_series_unknown_drone_is_refused():
    with pytest.raises(ValueError, match="no flights"):
        drone_series(load("healthy"), "D-99", "temp_rise_c")
