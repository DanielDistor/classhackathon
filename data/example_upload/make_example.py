"""Write the example Excel logbook for the dashboard's "Upload your logbook" tab.

    python data/example_upload/make_example.py

Writes data/example_upload/example_logbook.xlsx (and a copy in web/public/, so the dashboard can offer
it as a download). Invented data, seeded, identical every run. 3 drones x 70 flights, Oct 1-18, 2026:

  D-01  healthy readings; propeller 1 is close to its replace-at age
  D-02  prop strike on flight 64: vibration +6 sd on that flight, then +1.5 sd (chipped prop), not yet fixed
  D-03  motor wearing out: temperature rise climbs 0.25 degC per flight from flight 50, not yet fixed

Sheets: README (what to fill in), flights (required), maintenance and components (optional). The columns
are the same as data/fleet/ (see data/README.md).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
OUT = HERE / "example_logbook.xlsx"
WEB_COPY = HERE.parents[1] / "web" / "public" / "example_logbook.xlsx"
SEED = 2031
DRONES = ["D-01", "D-02", "D-03"]
N_FLIGHTS = 70
START = pd.Timestamp("2026-10-01 08:00")

README = [
    ("What this file is", "An example flight logbook for the Drone Fleet Reliability Monitor. Invented data: 3 drones x 70 flights."),
    ("How to use it", "Open the dashboard, go to 'Upload your logbook', and upload this file (or your own file with the same sheets and columns)."),
    ("flights (required)", "One row per flight, filled in at launch and right after landing."),
    ("maintenance (optional)", "One row per part replaced, repair made or signal checked. The charts restart after each one."),
    ("components (optional)", "One row per part from install to removal (or today). Needed for the Weibull replace-at ages."),
    ("flight_id", "F-<drone number>-<flight number>, e.g. F-02-064. Must end in the flight number."),
    ("drone_id", "D-01, D-02, ..."),
    ("datetime", "Launch time."),
    ("flight_min", "Minutes from takeoff to landing (flight controller log)."),
    ("ambient_temp_c", "Air temperature at the launch pad, deg C."),
    ("voltage_start_v / voltage_end_v", "Battery voltage at takeoff and at landing, V."),
    ("motor_temp_max_c", "Hottest motor within a minute of landing, deg C (infrared thermometer)."),
    ("vibration_rms", "RMS vibration over the flight, m/s2 (flight controller log)."),
    ("inflight_event", "none, warning, return_home or crash."),
    ("Planted in this example", "D-02: prop strike on flight 64. D-03: motor wearing out from flight 50. D-01: healthy, but propeller 1 is nearly due."),
]


def flights(rng: np.random.Generator) -> pd.DataFrame:
    rows = []
    for d_i, drone in enumerate(DRONES):
        level = 18.0 + rng.normal(0, 0.6)          # each drone runs a little differently
        vib0 = 3.0 + rng.normal(0, 0.15)
        for k in range(1, N_FLIGHTS + 1):
            t = START + pd.to_timedelta(6 * (k - 1) + 2 * d_i, unit="h")
            minutes = float(np.clip(rng.normal(22, 3), 12, 32))
            ambient = 17 + 3 * np.sin(k / 9) + rng.normal(0, 1.5)
            rise = level + rng.normal(0, 1.2)
            vib = vib0 + rng.normal(0, 0.25)
            sag = 0.17 + rng.normal(0, 0.008)
            if drone == "D-02" and k == 64:
                vib += 6 * 0.25                    # the strike
            elif drone == "D-02" and k > 64:
                vib += 1.5 * 0.25                  # chipped prop afterwards
            if drone == "D-03" and k >= 50:
                rise += 0.25 * (k - 49)            # bearing wear
            v0 = 25.1 + rng.normal(0, 0.05)
            rows.append(dict(flight_id=f"F-{d_i + 1:02d}-{k:03d}", drone_id=drone, datetime=t,
                             flight_min=round(minutes, 1), ambient_temp_c=round(ambient, 1),
                             voltage_start_v=round(v0, 2), voltage_end_v=round(v0 - sag * minutes, 2),
                             motor_temp_max_c=round(ambient + rise, 1), vibration_rms=round(vib, 2),
                             inflight_event="none"))
    return pd.DataFrame(rows)


def components(rng: np.random.Generator) -> pd.DataFrame:
    """A parts history: past parts (failed or removed) plus the parts installed now."""
    life = {"motor": (2.5, 500.0), "propeller": (1.8, 150.0), "battery": (3.0, 400.0)}
    slots = {"motor": 4, "propeller": 4, "battery": 2}
    code = {"motor": "M", "propeller": "P", "battery": "B"}
    rows = []
    for d_i, drone in enumerate(DRONES):
        for part, n_slots in slots.items():
            beta, eta = life[part]
            for slot in range(1, n_slots + 1):
                for gen in (1, 2):                 # one past part, then the one installed now
                    if gen == 1:
                        age = float(eta * rng.weibull(beta))
                        censor = float(rng.uniform(0.3, 1.4) * eta)
                        failed = age <= censor
                        life_value, status = (age, 1) if failed else (censor, 0)
                        mode = "worn" if failed else "removed_other"
                        end = "2026-09-20"
                    else:
                        life_value, status, mode, end = float(rng.uniform(0.05, 0.25) * eta), 0, "in_service", None
                        if drone == "D-01" and part == "propeller" and slot == 1:
                            life_value = 0.39 * eta        # nearly at its replace-at age: shows as due soon
                    rows.append(dict(component_id=f"{code[part]}-{d_i + 1:02d}-{slot}-{gen:02d}", drone_id=drone,
                                     component_type=part, lot="2026H1", install_date="2026-03-01" if gen == 1 else "2026-09-20",
                                     end_date=end, life_value=round(life_value, 1 if part != "battery" else 0),
                                     status=status, failure_mode=mode))
    return pd.DataFrame(rows)


def maintenance() -> pd.DataFrame:
    return pd.DataFrame([dict(drone_id="D-01", flight_id="F-01-040", datetime=START + pd.to_timedelta(6 * 39 + 1, unit="h"),
                              action="replace", chart="vibration_rms", component_type="propeller", position=2,
                              removed_id="P-01-2-01", installed_id="P-01-2-02", warned_after_flight=40,
                              reason="reached replace-at age (B10)")])


def main() -> None:
    rng = np.random.default_rng(SEED)
    f, c = flights(rng), components(rng)
    with pd.ExcelWriter(OUT, engine="openpyxl") as xl:
        pd.DataFrame(README, columns=["item", "explanation"]).to_excel(xl, sheet_name="README", index=False)
        f.to_excel(xl, sheet_name="flights", index=False)
        maintenance().to_excel(xl, sheet_name="maintenance", index=False)
        c.to_excel(xl, sheet_name="components", index=False)
    WEB_COPY.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(OUT, WEB_COPY)
    print(f"wrote {OUT.relative_to(HERE.parents[1])} ({len(f)} flights, {len(c)} parts) and {WEB_COPY.relative_to(HERE.parents[1])}")


if __name__ == "__main__":
    main()
