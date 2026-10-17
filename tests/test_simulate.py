"""Tests for the fleet simulator data/simulate.py (CONTRACT task H-10).

The simulated fleet must contain only random causes (no scripted drone),
catch and fix every injected special cause, keep every drone flying through
replacements, and give part lives whose Weibull fit recovers the true shape
and scale.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd
import pytest

from app.qc import fit_by_type

DATA = Path(__file__).resolve().parents[1] / "data"
sys.path.insert(0, str(DATA))
import simulate as S  # noqa: E402

FLEET = DATA / "fleet"


@pytest.fixture(scope="module")
def built():
    return S.build_fleet()


def test_csvs_on_disk_match_a_fresh_build(built):
    # Same seed, same output: the committed CSVs are exactly what simulate.py makes.
    for name in ("flights", "components", "maintenance", "answer_key", "replace_at", "fleet_reference"):
        on_disk = pd.read_csv(FLEET / f"{name}.csv")
        fresh = pd.read_csv(pd.io.common.StringIO(built[name].to_csv(index=False)))
        pd.testing.assert_frame_equal(on_disk, fresh, check_dtype=False)


def test_drift_known_answer():
    sd = S.CHART_SD["vibration_rms"]
    pf = S.PARTS["propeller"]["pf"]
    assert S.drift("propeller", age=100 - pf, life=100) == 0.0          # start of the P-F interval
    assert S.drift("propeller", age=100 - pf / 2, life=100) == pytest.approx(2.0 * sd)
    assert S.drift("propeller", age=100, life=100) == pytest.approx(S.DRIFT_AT_FAILURE * sd)
    assert S.drift("propeller", age=150, life=100) == pytest.approx(S.DRIFT_AT_FAILURE * sd)  # capped


def test_no_drone_is_scripted():
    # Nothing in the simulator names a drone or a flight to break.
    src = (DATA / "simulate.py").read_text()
    assert not re.search(r"D-\d\d", src)
    assert "crash" not in src


def test_every_drone_keeps_flying(built):
    f = built["flights"]
    assert f.groupby("drone_id").size().to_dict() == {f"D-{i:02d}": 300 for i in range(1, 11)}
    for drone, g in f.groupby("drone_id"):
        nums = g["flight_id"].str.rsplit("-", n=1).str[-1].astype(int).sort_values()
        assert nums.tolist() == list(range(1, 301)), drone
    assert set(f["inflight_event"]) <= {"none", "return_home"}


def test_every_drone_ends_with_a_full_set_of_parts(built):
    live = built["components"][built["components"]["end_date"].isna()]
    sets = live.groupby(["drone_id", "component_type"]).size().unstack()
    assert (sets["motor"] == 4).all() and (sets["propeller"] == 4).all() and (sets["battery"] == 2).all()


def test_each_rule_shape_is_injected_at_least_once(built):
    assert set(built["answer_key"]["rule_shape"]) == set(S.SPECIAL_CAUSES)


def test_every_special_cause_is_detected_and_fixed(built):
    k = built["answer_key"]
    assert k["detected_after_flight"].notna().all(), k[k["detected_after_flight"].isna()]
    assert k["fixed_after_flight"].notna().all()
    delay = k["detected_after_flight"] - k["start_flight"]
    assert (delay >= 0).all()
    assert delay.max() <= 20


def test_every_in_flight_failure_is_replaced_before_the_next_flight(built):
    f, m = built["flights"], built["maintenance"]
    failed = set(f.loc[f["inflight_event"] == "return_home", "flight_id"])
    replaced = set(m.loc[m["reason"] == "failed in flight", "flight_id"])
    assert failed == replaced


def test_a_warned_part_is_replaced_before_the_next_flight(built):
    # A warning (replace-at age reached, or a chart showed the part worn) means replace now.
    m = built["maintenance"]
    flight_no = m["flight_id"].str.rsplit("-", n=1).str[-1].astype(int)
    planned = (m["reason"] == "reached replace-at age (B10)") | m["reason"].str.startswith("worn")
    assert planned.sum() > 50
    assert (m.loc[planned, "warned_after_flight"] == flight_no[planned]).all()


def test_false_alarms_change_nothing(built):
    m = built["maintenance"]
    fa = m[m["action"] == "no_fault"]
    assert len(fa) > 0
    assert (fa["removed_id"].fillna("") == "").all() and (fa["installed_id"].fillna("") == "").all()


def test_replace_at_policy_is_the_schedule(built):
    policy = built["replace_at"].set_index("component_type")["b10"]
    assert policy.to_dict() == pytest.approx(built["b10"].to_dict(), abs=0.05)


def test_no_part_in_service_is_past_its_replace_at_age(built):
    c, b10 = built["components"], built["b10"]
    live = c[c["end_date"].isna()]
    one_flight = {"motor": 35 / 60, "propeller": 35 / 60, "battery": 1}   # longest flight / one charge
    limit = live["component_type"].map(b10) + live["component_type"].map(one_flight)
    assert (live["life_value"] <= limit).all()


#: Six intervals are checked at once (shape and scale for 3 part types). Each 95% interval
#: misses 5% of the time, so all six cover only ~0.95^6 = 74% of the time even for a perfect
#: estimator. Bonferroni: widen each to 1 - 0.05/6 (z = 2.638 instead of 1.960). Over seeds
#: 1-20 the plain 95% intervals covered the truth 17-20 times out of 20 per parameter.
Z_95 = 1.959964
Z_BONF = 2.638257


def widened(est: float, lo: float, hi: float) -> tuple[float, float]:
    """lifelines' intervals are est +/- z * se; rescale them from z = 1.96 to the Bonferroni z."""
    return est - (est - lo) * Z_BONF / Z_95, est + (hi - est) * Z_BONF / Z_95


@pytest.mark.parametrize("ctype", list(S.PARTS))
def test_weibull_fit_recovers_the_true_life(built, ctype):
    fit = fit_by_type(built["components"]).set_index("component_type").loc[ctype]
    true = S.PARTS[ctype]
    b_lo, b_hi = widened(fit["beta"], fit["beta_lo"], fit["beta_hi"])
    e_lo, e_hi = widened(fit["eta"], fit["eta_lo"], fit["eta_hi"])
    assert b_lo <= true["beta"] <= b_hi
    assert e_lo <= true["eta"] <= e_hi
