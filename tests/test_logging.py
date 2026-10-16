"""Tests for logging a new flight (CONTRACT task H-09: the "help them log" part of the prompt)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from app.qc import append_flight, fleet_status, make_flight_record

DATA = Path(__file__).resolve().parents[1] / "data"


def flights(ds="motor_drift"):
    return pd.read_csv(DATA / ds / "flights.csv")


def entry(**over):
    """A normal flight for D-01, after its last logged flight (2026-09-30)."""
    e = dict(drone_id="D-01", datetime="2026-10-01T09:00", preflight_fail_item="none",
             battery_id="B-01-1-03", battery_cycles=12, voltage_start_v=25.15, payload_kg=1.2,
             ambient_temp_c=16.0, flight_min=21.0, vibration_rms=3.0, inflight_event="none",
             motor_temp_max_c=34.0, voltage_end_v=21.6)
    e.update(over)
    return e


def test_record_gets_next_flight_id_and_all_columns():
    f = flights()
    rec = make_flight_record(f, entry())
    last = f[f.drone_id == "D-01"]["flight_id"].iloc[-1]          # F-01-100
    assert rec["flight_id"] == "F-01-101" and last == "F-01-100"
    assert rec["preflight_pass"] == 1
    assert set(rec) == set(f.columns)


def test_failed_checklist_item_sets_preflight_pass_0():
    rec = make_flight_record(flights(), entry(preflight_fail_item="prop_chip"))
    assert rec["preflight_pass"] == 0


def test_append_adds_one_row_and_keeps_the_input_unchanged():
    f = flights()
    out = append_flight(f, make_flight_record(f, entry()))
    assert len(out) == len(f) + 1 and len(f) == 995
    assert out["flight_id"].iloc[-1] == "F-01-101"


@pytest.mark.parametrize("field, value, words", [
    ("motor_temp_max_c", 400, "motor_temp_max_c"),
    ("voltage_start_v", -3, "voltage_start_v"),
    ("flight_min", 0, "flight_min"),
    ("vibration_rms", 99, "vibration_rms"),
    ("payload_kg", 12, "payload_kg"),
    ("battery_cycles", -1, "battery_cycles"),
])
def test_impossible_values_are_refused_by_name(field, value, words):
    with pytest.raises(ValueError, match=words):
        make_flight_record(flights(), entry(**{field: value}))


def test_landing_voltage_must_be_below_takeoff():
    with pytest.raises(ValueError, match="landing"):
        make_flight_record(flights(), entry(voltage_end_v=25.5))


def test_flight_must_come_after_the_drones_last_flight():
    with pytest.raises(ValueError, match="after"):
        make_flight_record(flights(), entry(datetime="2026-09-15T09:00"))


def test_unknown_categories_and_bad_drone_ids_are_refused():
    with pytest.raises(ValueError, match="inflight_event"):
        make_flight_record(flights(), entry(inflight_event="explosion"))
    with pytest.raises(ValueError, match="drone"):
        make_flight_record(flights(), entry(drone_id="drone seven"))


def test_motor_temperature_may_be_blank_only_after_a_crash():
    with pytest.raises(ValueError, match="motor_temp_max_c"):
        make_flight_record(flights(), entry(motor_temp_max_c=None))
    rec = make_flight_record(flights(), entry(motor_temp_max_c=None, inflight_event="crash"))
    assert pd.isna(rec["motor_temp_max_c"])


def test_logging_a_hot_motor_flight_grounds_the_drone():
    # D-01 is "go" in the motor-drift fleet; one flight far above its temperature limit grounds it.
    f = flights()
    assert fleet_status(f).set_index("drone_id").loc["D-01", "status"] == "go"
    hot = append_flight(f, make_flight_record(f, entry(motor_temp_max_c=60.0)))
    row = fleet_status(hot).set_index("drone_id").loc["D-01"]
    assert row["status"] == "ground" and "flight 101" in row["reason"]
