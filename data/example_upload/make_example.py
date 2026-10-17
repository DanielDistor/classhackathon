"""Write the example Excel logbook for the dashboard's upload box.

    python data/example_upload/make_example.py

It is a third fleet from the same simulator as data/fleet/ and data/fleet_b/ (data/simulate.py), with its
own seed, so it has exactly the same format: 10 drones x 300 flights, Jul 1 - Sep 29, 2026, parts retired
at B10. Writes data/example_upload/example_logbook.xlsx and a copy in web/public/ (the dashboard offers it
as a download). Identical every run.

Sheets (the same tables as a data/ folder, see data/README.md):
  README           what each sheet holds
  flights          required: one row per flight
  components       required: one row per part, install to removal or today
  maintenance      optional: every replacement, repair and checked signal (charts restart after each)
  replace_at       optional: the replace-at age per part type (fitted from components if left out)
  fleet_reference  optional: the fleet's normal range for each reading (worked out if left out)
The answer key (which problems were planted) is left out: a technician's logbook would not have one.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "data"))
import simulate  # noqa: E402

SEED = 9101
OUT = HERE / "example_logbook.xlsx"
WEB_COPY = ROOT / "web" / "public" / "example_logbook.xlsx"

README = [
    ("What this file is", "An example logbook for the Drone Fleet Reliability Monitor: invented data for 10 drones x 300 "
                          "flights (Jul-Sep 2026), from the same simulator as the dashboard's test fleets (seed 9101)."),
    ("How to use it", "In the dashboard, click 'Upload a file' and pick this workbook. Every tab then shows this fleet. "
                      "Your own workbook needs the same sheet names and columns."),
    ("flights (required)", "One row per flight, filled in at launch and right after landing."),
    ("components (required)", "One row per motor, propeller or battery, from install to failure, removal or today."),
    ("maintenance (optional)", "One row per part replaced, repair made or signal checked. The charts restart after each."),
    ("replace_at (optional)", "The replace-at age per part type. Left out, it is the B10 fitted from components."),
    ("fleet_reference (optional)", "Each reading's normal range across the fleet. Left out, it is taken from every drone's "
                                   "first 20 flights."),
    ("Columns", "The columns of each sheet are listed, with units and how to collect them, in data/README.md."),
]


def main() -> None:
    simulate.SEED = SEED          # a new fleet: every random stream follows from the seed
    t = simulate.build_fleet(simulate.DEFAULT_RETIRE_PCT)
    sheets = {name: t[name] for name in ("flights", "components", "maintenance", "replace_at", "fleet_reference")}
    with pd.ExcelWriter(OUT, engine="openpyxl") as xl:
        pd.DataFrame(README, columns=["item", "explanation"]).to_excel(xl, sheet_name="README", index=False)
        for name, df in sheets.items():
            df.to_excel(xl, sheet_name=name, index=False)
    WEB_COPY.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(OUT, WEB_COPY)
    print(f"wrote {OUT.relative_to(ROOT)} (" + ", ".join(f"{k} {len(v)}" for k, v in sheets.items())
          + f") and {WEB_COPY.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
