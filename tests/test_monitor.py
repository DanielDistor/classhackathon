"""Tests for monitoring with repairs: monitor_chart, fleet_status with a maintenance log,
and the W / R / F / S / N timeline (CONTRACT task H-03 rework).

Known answers by hand first, then the simulated fleet: run on the CSVs alone, the tool
must signal on exactly the flights where the simulated technician acted.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from app.qc import (MARKERS, MONITORED, add_derived, check_maintenance, drone_series, fleet_status,
                    flight_numbers, maintenance_timeline, monitor_chart, reset_flights)

FLEET = Path(__file__).resolve().parents[1] / "data" / "fleet"
BASE = [10, 12, 11, 13, 12]          # center 11.6, sigma 1.5 / 1.128 = 1.3298 (test_qc known answer)


def chart(values, resets=()):
    return monitor_chart(values, range(1, len(values) + 1), resets, n_baseline=5, min_baseline=2)


# ---------------------------------------------------------------- known answers

def test_ewma_known_answer_and_restart_after_a_reset():
    # z6 = 0.2*13 + 0.8*11.6 = 11.88; z7 = 0.2*13 + 0.8*11.88 = 12.104.
    # With a reset after flight 6, flight 7 starts again from the center: z7 = 11.88.
    plain = chart(BASE + [13, 13])
    assert plain["z"].iloc[5:].round(4).tolist() == [11.88, 12.104]
    reset = chart(BASE + [13, 13], resets=[6])
    assert reset["z"].iloc[5:].round(4).tolist() == [11.88, 11.88]
    assert reset["segment"].tolist() == [0] * 5 + [1, 2]


def test_baseline_rows_carry_no_signal():
    ch = chart(BASE + [11])
    assert ch["baseline"].tolist() == [True] * 5 + [False]
    assert ch.loc[ch["baseline"], "z"].isna().all()
    assert not ch.loc[ch["baseline"], "signal"].any()


def test_limits_are_kept_through_resets():
    a, b = chart(BASE + [12, 13, 11, 12]), chart(BASE + [12, 13, 11, 12], resets=[6, 7, 8])
    for col in ("center", "lcl", "ucl", "sigma"):
        assert a[col].equals(b[col])
    assert a["center"].iloc[0] == pytest.approx(11.6)
    assert a["ucl"].iloc[0] == pytest.approx(15.589, abs=1e-3)


def test_a_run_never_spans_a_repair():
    # 9 points just above the center: rule 2 fires on the 9th. A repair after the 5th
    # splits them into runs of 5 and 4, so rule 2 cannot fire.
    run = BASE + [11.8] * 9
    assert chart(run)["rule_2"].iloc[-1]
    split = chart(run, resets=[10])
    assert not split["rule_2"].any()


def test_a_reset_inside_the_baseline_changes_nothing():
    vals = BASE + [12, 14]
    pd.testing.assert_frame_equal(chart(vals), chart(vals, resets=[2, 4]))


def test_signal_and_what_columns():
    ch = chart(BASE + [16])                      # 16 > UCL 15.589 and pulls the EWMA up
    assert ch["signal"].iloc[-1] and ch["rule_1"].iloc[-1]
    assert ch["what"].iloc[-1].endswith("rule 1")


def test_degenerate_inputs_are_refused():
    with pytest.raises(ValueError, match="no variation"):
        monitor_chart([5.0] * 10, range(1, 11), n_baseline=5, min_baseline=2)
    with pytest.raises(ValueError, match="different lengths"):
        monitor_chart(BASE + [11], range(1, 4), n_baseline=5, min_baseline=2)
    with pytest.raises(ValueError, match="at least 2"):
        monitor_chart([1.0], [1])


def test_reset_flights_reads_the_chart_column():
    m = pd.DataFrame({"drone_id": ["D-01", "D-01", "D-02", "D-01"],
                      "flight_id": ["F-01-060", "F-01-055", "F-02-070", "F-01-060"],
                      "chart": ["vibration_rms", "vibration_rms", "vibration_rms", "temp_rise_c"]})
    assert reset_flights(m, "D-01", "vibration_rms") == [55, 60]
    assert reset_flights(None, "D-01", "vibration_rms") == []


# ---------------------------------------------------------------- the simulated fleet

@pytest.fixture(scope="module")
def fleet():
    return (add_derived(pd.read_csv(FLEET / "flights.csv")), pd.read_csv(FLEET / "maintenance.csv"),
            pd.read_csv(FLEET / "answer_key.csv"))


def test_tool_signals_on_exactly_the_flights_the_technician_acted_on(fleet):
    f, m, _ = fleet
    acted = m[m["action"].isin(["inspect", "repair"]) | m["reason"].str.startswith("special cause")]
    for drone in sorted(f["drone_id"].unique()):
        for col, _, _ in MONITORED:
            s = drone_series(f, drone, col)
            ch = monitor_chart(s["value"], s["flight_no"], reset_flights(m, drone, col))
            tool = set(ch.loc[ch["signal"], "flight_no"])
            tech = set(flight_numbers(acted.loc[(acted["drone_id"] == drone) & (acted["chart"] == col),
                                                "flight_id"]))
            assert tool == tech, (drone, col, sorted(tool ^ tech))


def test_every_special_cause_is_a_tool_signal(fleet):
    f, m, key = fleet
    for e in key.itertuples():
        s = drone_series(f, e.drone_id, e.chart)
        ch = monitor_chart(s["value"], s["flight_no"], reset_flights(m, e.drone_id, e.chart)).set_index("flight_no")
        assert ch.loc[e.detected_after_flight, "signal"], e.event_id
        assert ch.loc[e.detected_after_flight, "what"] == e.detected_by, e.event_id


def test_fleet_status_with_the_log_has_no_open_signals(fleet):
    f, m, _ = fleet
    with_log = fleet_status(f, m)
    assert (with_log["status"] == "go").all()            # the technician acted on every signal
    assert with_log["health"].between(0, 1).all()
    without = fleet_status(f)                            # nothing restarts: old signals stay open
    assert (without["status"] != "go").any()


def test_timeline_markers(fleet):
    f, m, key = fleet
    tl = maintenance_timeline(m)
    assert set(tl["marker"]) == set(MARKERS)
    # every in-flight failure is an F on the flight it happened
    failed = f.loc[f["inflight_event"] == "return_home", ["drone_id", "flight_id"]]
    fs = tl[tl["marker"] == "F"]
    assert sorted(zip(failed["drone_id"], flight_numbers(failed["flight_id"]))) == \
        sorted(zip(fs["drone_id"], fs["flight_no"]))
    # every planned replacement (R) has an earlier W in the same lane
    for r in tl[tl["marker"] == "R"].itertuples():
        w = tl[(tl["drone_id"] == r.drone_id) & (tl["lane"] == r.lane) & (tl["marker"] == "W")
               & (tl["flight_no"] < r.flight_no)]
        assert len(w), r
    # every special cause in the answer key is an S on the flight it was fixed
    s = set(zip(tl.loc[tl["marker"] == "S", "drone_id"], tl.loc[tl["marker"] == "S", "flight_no"]))
    assert {(e.drone_id, e.fixed_after_flight) for e in key.itertuples()} <= s


def test_check_maintenance_refuses_bad_logs(fleet):
    _, m, _ = fleet
    assert check_maintenance(m) is m
    with pytest.raises(ValueError, match="chart"):
        check_maintenance(m.drop(columns=["chart"]))
    bad = m.copy()
    bad.loc[0, "action"] = "polish"
    with pytest.raises(ValueError, match="action"):
        check_maintenance(bad)
