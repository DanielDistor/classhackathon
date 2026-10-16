"""Generate the three invented test datasets for the drone fleet reliability tool.

Run from the repo root:

    python data/simulate.py

It writes one folder per dataset, each holding two tables:

    data/healthy/          flights.csv  components.csv
    data/motor_drift/      flights.csv  components.csv
    data/bad_battery_lot/  flights.csv  components.csv

Every number is invented. The data are shaped like a real maintenance log
(see data/README.md, the codebook) but describe no real fleet.

Design: all three datasets are built from the SAME random draws. Each
random stream is keyed by (seed, purpose, drone, slot), so a planted problem
in one dataset never shifts the draws anywhere else. The datasets therefore
differ ONLY by their planted signals:

    healthy          nothing planted; every chart should be in control
    motor_drift      D-07: temp_rise_c climbs 0.20 C per flight after flight 60
                     and motor 3 fails (crash) on flight 95.
                     D-03: a prop strike on flight 80 (one vibration spike).
    bad_battery_lot  batteries from lot B have a Weibull scale 40% shorter.

Only numpy and pandas are needed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 5300
OUT_DIR = Path(__file__).resolve().parent

N_DRONES = 10
FLIGHTS_PER_DRONE = 100
WINDOW_START = pd.Timestamp("2026-09-01")  # first day of the flight log
WINDOW_DAYS = 30                           # flights.csv covers 30 days
HISTORY_FLIGHTS_PER_DAY = 3.3              # usage before the flight log starts
MEAN_FLIGHT_MIN = 22.0

# True life distributions (Weibull shape beta, scale eta). Units: flight hours
# for motors and propellers, charge cycles for batteries.
MOTOR = dict(beta=2.5, eta=500.0)
PROP = dict(beta=1.8, eta=150.0)
BATTERY = dict(beta=3.0, eta=400.0)
BAD_LOT_SCALE = 0.60          # lot B battery eta multiplier in bad_battery_lot
P_REMOVED_EARLY = 0.08        # chance a part is pulled before it fails (censored)

# Planted signals (motor_drift).
DRIFT_DRONE, DRIFT_START, DRIFT_PER_FLIGHT, CRASH_FLIGHT, CRASH_MOTOR = "D-07", 60, 0.20, 95, 3
STRIKE_DRONE, STRIKE_FLIGHT, STRIKE_PROP, STRIKE_VIBRATION = "D-03", 80, 1, 7.0

FAILURE_MODES = {
    "motor": (["bearing", "winding"], [0.7, 0.3]),
    "propeller": (["chip", "crack"], [0.6, 0.4]),
    "battery": (["capacity_fade", "swelling"], [0.8, 0.2]),
}
PREFIX = {"motor": "M", "propeller": "P", "battery": "B"}


def rng_for(*key: int) -> np.random.Generator:
    """One independent random stream per (seed, purpose, drone, slot) key."""
    return np.random.default_rng([SEED, *key])


def battery_lot(install: pd.Timestamp) -> str:
    """Supplier lot by purchase period: A before Oct 2025, B to Mar 2026, C after."""
    if install < pd.Timestamp("2025-10-01"):
        return "A"
    if install < pd.Timestamp("2026-04-01"):
        return "B"
    return "C"


def part_lot(install: pd.Timestamp) -> str:
    """Motors and propellers: lot = install half-year, e.g. 2026H1."""
    return f"{install.year}H{1 if install.month <= 6 else 2}"


# --------------------------------------------------------------------------
# Flights: one row per flight, before components are attached
# --------------------------------------------------------------------------

def simulate_flight_base(d: int) -> pd.DataFrame:
    """Schedule and baseline measurements for drone index d (no planted signals)."""
    rng = rng_for(1, d)
    n = FLIGHTS_PER_DRONE
    # Launch times: spread over the 30 days, between 07:00 and 19:00.
    days = np.sort(rng.integers(0, WINDOW_DAYS, n))
    minutes_of_day = rng.integers(7 * 60, 19 * 60, n)
    order = np.lexsort((minutes_of_day, days))
    days, minutes_of_day = days[order], minutes_of_day[order]
    dt = WINDOW_START + pd.to_timedelta(days, "D") + pd.to_timedelta(minutes_of_day, "min")

    flight_min = np.clip(rng.normal(MEAN_FLIGHT_MIN, 4.0, n), 8, 35).round(1)
    payload = rng.uniform(0.5, 2.5, n).round(2)

    # Ambient temperature: a shared daily level (same city) plus a midday bump.
    day_level = rng_for(2).normal(17.0, 4.0, WINDOW_DAYS)
    hour = minutes_of_day / 60
    ambient = day_level[days] + 3.0 * np.sin((hour - 7) / 12 * math.pi) + rng.normal(0, 0.8, n)

    # Motor temperature rise over ambient: drone-specific level, payload and
    # flight length effects, measurement noise. Total sd is about 1.4 C.
    drone_level = 18.0 + rng.normal(0, 1.0)
    temp_rise = (drone_level + 1.2 * (payload - 1.5) + 0.1 * (flight_min - MEAN_FLIGHT_MIN)
                 + rng.normal(0, 1.2, n))

    vibration = 3.0 + rng.normal(0, 0.2) + rng.normal(0, 0.25, n)
    sag_rate = 0.17 + 0.02 * (payload - 1.5) + rng.normal(0, 0.008, n)  # V per minute
    voltage_start = rng.normal(25.15, 0.04, n)

    # Before-flight checklist: random 2% fails on arms or connectors
    # (propeller chips are added later, from the propeller life simulation).
    pre_u = rng.uniform(size=n)
    fail_item = np.where(pre_u < 0.01, "loose_arm", np.where(pre_u < 0.02, "connector", "none"))

    return pd.DataFrame({
        "flight_seq": np.arange(1, n + 1),
        "datetime": dt,
        "flight_min": flight_min,
        "payload_kg": payload,
        "ambient_temp_c": ambient.round(1),
        "_temp_rise": temp_rise,
        "_sag_rate": sag_rate,
        "voltage_start_v": voltage_start.round(2),
        "vibration_rms": vibration,
        "preflight_fail_item": fail_item,
        "inflight_event": "none",
    })


# --------------------------------------------------------------------------
# Components: a renewal process per slot (motor position, prop position,
# battery slot). Each part lives until it fails, is pulled early (censored),
# or the log ends (censored, still in service).
# --------------------------------------------------------------------------

@dataclass
class Life:
    start: float          # on the slot's usage axis (hours or cycles)
    end: float
    status: int           # 1 = failed, 0 = censored
    mode: str


def simulate_slot(rng: np.random.Generator, beta: float, eta_of, total: float,
                  forced: tuple[float, str] | None, end_mode: str, integer: bool) -> list[Life]:
    """Lives laid end to end on one slot's usage axis, up to `total`.

    eta_of(start) gives the scale for a part installed at usage `start`
    (this is how a bad supplier lot shortens some lives). Lives are drawn by
    inverse transform from uniforms, so changing eta never shifts the stream.
    `forced` = (usage, mode): the part in service at that usage fails there.
    """
    lives, t = [], 0.0
    while t < total:
        u_life, u_pull, u_frac = rng.uniform(size=3)
        life = eta_of(t) * (-math.log(1 - u_life)) ** (1 / beta)
        if integer:
            life = max(1.0, round(life))
        end, status, mode = t + life, 1, "failure"
        if u_pull < P_REMOVED_EARLY:
            end, status, mode = t + max(1.0, round(u_frac * life) if integer else u_frac * life), 0, "removed_other"
        if forced and t < forced[0] <= end:
            end, status, mode = forced[0], 1, forced[1]
        if end >= total and not (forced and end == forced[0]):
            end, status, mode = total, 0, end_mode
        lives.append(Life(t, end, status, mode))
        t = end
        if forced and end == forced[0] and total == forced[0]:
            break
    return lives


def usage_to_time(usage, hist_usage, commission, cum_window, flight_times):
    """Map a point on a slot's usage axis to a calendar timestamp.

    Before the flight log: linear between commissioning and the log start.
    During the log: the launch time of the flight in which that usage is reached.
    """
    if usage <= hist_usage:
        span = WINDOW_START - commission
        return commission + span * (usage / hist_usage)
    k = int(np.searchsorted(cum_window, usage - hist_usage, side="left"))
    return flight_times[min(k, len(flight_times) - 1)]


def build_dataset(scenario: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    flights_all, comps_all = [], []
    for d in range(N_DRONES):
        drone = f"D-{d + 1:02d}"
        f = simulate_flight_base(d)
        crashed = scenario == "motor_drift" and drone == DRIFT_DRONE

        # ---- planted flight-level signals ----
        if crashed:
            k = f["flight_seq"]
            f["_temp_rise"] += np.where(k > DRIFT_START, DRIFT_PER_FLIGHT * (k - DRIFT_START), 0.0)
            f = f[f["flight_seq"] <= CRASH_FLIGHT].copy()
            f.loc[f["flight_seq"] > 85, "inflight_event"] = "warning"
            f.loc[f["flight_seq"] == CRASH_FLIGHT, "inflight_event"] = "crash"
        strike = scenario == "motor_drift" and drone == STRIKE_DRONE
        if strike:
            f.loc[f["flight_seq"] == STRIKE_FLIGHT, "vibration_rms"] = STRIKE_VIBRATION
            f.loc[f["flight_seq"] == STRIKE_FLIGHT, "inflight_event"] = "warning"

        times = list(f["datetime"])
        hours_window = np.cumsum(f["flight_min"].to_numpy() / 60)
        commission = pd.Timestamp("2025-04-01") + pd.Timedelta(days=int(rng_for(3, d).integers(0, 180)))
        hist_days = (WINDOW_START - commission).days
        hist_hours = hist_days * HISTORY_FLIGHTS_PER_DAY * MEAN_FLIGHT_MIN / 60
        total_hours = hist_hours + hours_window[-1]
        end_mode = "crash_loss" if crashed else "in_service"

        # ---- motors (4) and propellers (4), on the drone's flight-hour axis ----
        crash_hours = hist_hours + hours_window[-1]  # crash happens at end of last flight
        strike_hours = None
        if strike:
            strike_hours = hist_hours + hours_window[STRIKE_FLIGHT - 1]
        for ctype, spec, n_slots, key in (("motor", MOTOR, 4, 10), ("propeller", PROP, 4, 20)):
            for pos in range(1, n_slots + 1):
                forced = None
                if crashed and ctype == "motor" and pos == CRASH_MOTOR:
                    forced = (crash_hours, "bearing")
                if strike and ctype == "propeller" and pos == STRIKE_PROP:
                    forced = (strike_hours, "strike")
                rng = rng_for(key, d, pos)
                lives = simulate_slot(rng, spec["beta"], lambda t, e=spec["eta"]: e, total_hours,
                                      forced, end_mode, integer=False)
                for g, life in enumerate(lives, 1):
                    install = usage_to_time(life.start, hist_hours, commission, hours_window, times)
                    end = usage_to_time(life.end, hist_hours, commission, hours_window, times)
                    mode = life.mode
                    if mode == "failure":
                        names, probs = FAILURE_MODES[ctype]
                        mode = names[int(rng_for(30, d, pos, g, key).choice(len(names), p=probs))]
                    comps_all.append(dict(
                        component_id=f"{PREFIX[ctype]}-{drone[2:]}-{pos}-{g:02d}", drone_id=drone,
                        component_type=ctype, lot=part_lot(install), install_date=install.date(),
                        end_date=end.date() if mode != "in_service" else None,
                        life_value=round(life.end - life.start, 1), status=life.status,
                        failure_mode=mode))
                    # A random failure during the flight log shows up in the log
                    # itself. (The planted crash and prop strike are already marked.)
                    planted = forced is not None and life.end == forced[0]
                    if life.status == 1 and life.end > hist_hours and not planted:
                        k = int(np.searchsorted(hours_window, life.end - hist_hours, side="left"))
                        k = min(k, len(f) - 1)
                        if ctype == "propeller":
                            # Prop damage is found at the next before-flight check.
                            k2 = min(k + 1, len(f) - 1)
                            f.iloc[k2, f.columns.get_loc("preflight_fail_item")] = "prop_chip"
                        elif f.iloc[k]["inflight_event"] == "none":
                            f.iloc[k, f.columns.get_loc("inflight_event")] = "return_home"

        # ---- batteries: 2 slots used alternately, on a charge-cycle axis ----
        slot_of_flight = (f["flight_seq"].to_numpy() - 1) % 2 + 1
        f["battery_id"], f["battery_cycles"] = "", 0
        hist_cycles = round(hist_days * HISTORY_FLIGHTS_PER_DAY / 2)
        for slot in (1, 2):
            idx = np.flatnonzero(slot_of_flight == slot)
            cyc_window = np.arange(1, len(idx) + 1, dtype=float)       # cycles reached per use
            total_cycles = hist_cycles + len(idx)

            def eta_of(t, slot=slot):
                install = usage_to_time(t, hist_cycles, commission, cyc_window, [times[i] for i in idx])
                bad = scenario == "bad_battery_lot" and battery_lot(install) == "B"
                return BATTERY["eta"] * (BAD_LOT_SCALE if bad else 1.0)

            lives = simulate_slot(rng_for(40, d, slot), BATTERY["beta"], eta_of, total_cycles,
                                  None, end_mode, integer=True)
            slot_times = [times[i] for i in idx]
            for g, life in enumerate(lives, 1):
                bid = f"B-{drone[2:]}-{slot}-{g:02d}"
                install = usage_to_time(life.start, hist_cycles, commission, cyc_window, slot_times)
                end = usage_to_time(life.end, hist_cycles, commission, cyc_window, slot_times)
                mode = life.mode
                if mode == "failure":
                    names, probs = FAILURE_MODES["battery"]
                    mode = names[int(rng_for(41, d, slot, g).choice(len(names), p=probs))]
                comps_all.append(dict(
                    component_id=bid, drone_id=drone, component_type="battery",
                    lot=battery_lot(install), install_date=install.date(),
                    end_date=end.date() if mode != "in_service" else None,
                    life_value=int(life.end - life.start), status=life.status, failure_mode=mode))
                # Attach this battery to the flights it powered (cycle c is
                # flown by the battery installed at cycle < c <= its end).
                for j, i in enumerate(idx):
                    c = hist_cycles + j + 1
                    if life.start < c <= life.end:
                        f.iloc[i, f.columns.get_loc("battery_id")] = bid
                        f.iloc[i, f.columns.get_loc("battery_cycles")] = int(c - life.start)
                        if life.status == 1 and c == life.end and f.iloc[i]["inflight_event"] == "none":
                            f.iloc[i, f.columns.get_loc("inflight_event")] = "return_home"

        # ---- finish measured columns ----
        motor_temp = (f["ambient_temp_c"] + f["_temp_rise"]).round(1)
        f["motor_temp_max_c"] = motor_temp.where(f["inflight_event"] != "crash")  # wreck: no reading
        f["voltage_end_v"] = (f["voltage_start_v"] - f["_sag_rate"] * f["flight_min"]).round(2)
        f["vibration_rms"] = f["vibration_rms"].round(2)
        f["preflight_pass"] = (f["preflight_fail_item"] == "none").astype(int)
        f["drone_id"] = drone
        f["flight_id"] = [f"F-{drone[2:]}-{k:03d}" for k in f["flight_seq"]]
        flights_all.append(f)

    flights = pd.concat(flights_all, ignore_index=True).sort_values(["datetime", "drone_id"])
    flights["datetime"] = flights["datetime"].dt.strftime("%Y-%m-%dT%H:%M")
    flights = flights[[
        "flight_id", "drone_id", "datetime", "flight_min", "payload_kg", "ambient_temp_c",
        "battery_id", "battery_cycles", "voltage_start_v", "voltage_end_v", "motor_temp_max_c",
        "vibration_rms", "preflight_pass", "preflight_fail_item", "inflight_event"]]
    comps = pd.DataFrame(comps_all).sort_values(["drone_id", "component_id"])
    return flights.reset_index(drop=True), comps.reset_index(drop=True)


def main() -> None:
    for scenario in ("healthy", "motor_drift", "bad_battery_lot"):
        flights, comps = build_dataset(scenario)
        folder = OUT_DIR / scenario
        folder.mkdir(exist_ok=True)
        flights.to_csv(folder / "flights.csv", index=False, lineterminator="\n")
        comps.to_csv(folder / "components.csv", index=False, lineterminator="\n")
        print(f"{scenario:16s} flights={len(flights):4d}  components={len(comps):4d}  "
              f"failed={int(comps['status'].sum()):3d}")


if __name__ == "__main__":
    main()
