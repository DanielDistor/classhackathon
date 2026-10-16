# SPEC: Six Sigma Hackathon team project

What your tool IS. Your agent reads this before every task. Where the code and this file
disagree, the code is the bug: change this file first, then the code.

Most of this page is already decided by the event and the [rubric](docs/criteria.md).
**Only the `FILL IN` lines change, and you do not have to write them by hand:** describe your app and ask your agent to update them. They depend on the prompt your team picks at kickoff
(prompts are secret until then, see [`docs/prompts.md`](docs/prompts.md)) and on your team.
The examples after each `FILL IN` show the shape of an answer. They are not hints about the prompts.

## 1. Team and prompt
- **Team name:** Flight Control
- **Track:** on-campus (24 hours). Submissions due Sat Oct 17, 1 PM ET.
- **Prompt we chose:** Industrial Systems: Drone Delivery Fleet Maintenance. "A drone startup is experiencing mid-air failures, but they only investigate after a crash. Design a tracking tool for technicians to help them log wear-and-tear before and during flight, and manage and improve system performance and/or reliability."
- **Our public repo:** github.com/DanielDistor/classhackathon

## 2. User and use case (rubric: scope 5, user and use case 5)
- **User:** the fleet maintenance technician at a drone delivery startup, who inspects each drone between flights.
- **Decision the tool helps them make, and when:** before each drone's next flight, mark it go, watch or ground (inspect or replace a part first). Each week, decide when to replace motors and batteries before they fail.
- **Why this matches the prompt:** it replaces after-the-crash investigation with logging wear before and after every flight, and it flags degradation while the drone is still on the ground.

## 3. Inputs (rubric: minimal inputs 5)
Only what this user can actually measure or already knows. Fewer is better; every input a user
cannot measure costs points.

| Input | Type and units | Where the user gets it |
|---|---|---|
| `flights.csv`, one row per flight | table | the technician's flight log (an app form or a spreadsheet) |
| `drone_id`, `flight_id`, `datetime` | text, text, ISO timestamp | airframe label; automatic |
| `flight_min` | numeric, minutes | flight controller log |
| `payload_kg` | numeric, kg | package scale |
| `ambient_temp_c` | numeric, °C | thermometer or weather app at launch |
| `battery_id`, `battery_cycles` | text; integer count | battery label; battery management system (BMS) readout |
| `voltage_start_v`, `voltage_end_v` | numeric, V | BMS / ground station at takeoff and landing |
| `motor_temp_max_c` | numeric, °C | handheld infrared thermometer on the hottest motor, within 1 minute of landing |
| `vibration_rms` | numeric, m/s² | flight controller log export (PX4 / ArduPilot record it) |
| `preflight_pass`, `preflight_fail_item` | 0/1; category (`prop_chip`, `loose_arm`, `connector`, `none`) | before-flight checklist |
| `inflight_event` | category (`none`, `warning`, `return_home`, `crash`) | flight log / pilot report |
| `components.csv`, one row per installed part | table | the maintenance log |
| `component_id`, `drone_id`, `component_type`, `lot` | text; `motor` / `battery` / `propeller`; supplier batch | part label and packing slip |
| `install_date`, `end_date` | date; date or blank (still in service) | maintenance log |
| `life_value` | numeric: flight hours (motors, propellers), charge cycles (batteries) | summed from flights / BMS |
| `status`, `failure_mode` | 1 = failed, 0 = censored (still flying, or removed before failure); category | maintenance log |

Derived by the tool, never typed by the user: `temp_rise_c = motor_temp_max_c - ambient_temp_c` and
`sag_rate_v_per_min = (voltage_start_v - voltage_end_v) / flight_min`.

## 4. The statistics, and why (rubric: valid QC analysis 25)
Say the method in words before any code exists. Load the `stats-first-steering` skill first.
- **Method:** (1) For each drone, an EWMA chart (λ = 0.2, L = 3) on `temp_rise_c` to catch slow wear. (2) For each drone, I-MR charts on `vibration_rms` and `sag_rate_v_per_min` to catch sudden damage. Limits come from that drone's first 30 flights (the Phase I baseline): σ̂ = MR̄ / 1.128. The I chart has limits x̄ ± 3σ̂ and the MR chart has UCL = 3.267 × MR̄, with run rule 1 only (a point beyond 3σ). EWMA: z_t = λx_t + (1-λ)z_{t-1}, z_0 = baseline mean, limits μ₀ ± Lσ̂·sqrt(λ/(2-λ)·(1-(1-λ)^{2t})). (3) For each component type, a two-parameter Weibull fit by maximum likelihood with right-censoring (`lifelines.WeibullFitter`), reporting shape β, scale η, B10 = η(-ln 0.9)^{1/β}, and a replacement interval at B10. Status rule: **ground** = the latest flight was a crash, or the latest reading is beyond an I-chart limit, or the EWMA is currently beyond its limit; **watch** = any signal in the last 10 flights; **go** = otherwise. Parts older than their type's B10 life are listed separately on the Part reliability tab, not folded into the status (team decision 2026-10-16: this fleet runs parts to failure, so 51 parts are past B10 and would put nearly every drone on watch, hiding the chart signals). **Health bar** = the room left before the nearest control limit on the drone's most-stretched chart: for the latest point (EWMA z, or I-chart value), room = (UCL − x)/(UCL − center) above the center or (x − LCL)/(center − LCL) below it, clipped to [0, 1]; the drone's health is the minimum over its four charts, and 0 after a crash. A Kaplan-Meier curve is drawn next to each Weibull fit as the goodness-of-fit check.
- **Why it fits the use case:** wear shows up as small sustained shifts, which the EWMA catches flights earlier than a raw chart; sudden damage shows up as single large points (I-MR); and most parts never fail before removal, so life estimates must handle censoring.
- **Assumptions and how the tool checks them:** the baseline is in control (the app shows the baseline window and refuses fewer than 20 baseline flights); flights are roughly independent (the demo shows lag-1 autocorrelation of `temp_rise_c`); ambient temperature is the main confounder of motor temperature, so we chart the rise over ambient, not raw temperature; Weibull fit (a Weibull probability plot in the reliability tab, β with a 95% CI); censoring is independent of failure, and there is one failure mode per component type (stated in the README).
- **Known-answer check:** I-MR on x = [10, 12, 11, 13, 12] gives center 11.6, MR̄ 1.5, σ̂ 1.3298, UCL 15.589, LCL 7.611, MR UCL 4.901. EWMA with λ = 0.2, μ₀ = 10, σ = 1, L = 3 on x = [11, 12] gives z = 10.2, 10.56 and limit half-widths 0.600, 0.7684 (1.000 asymptotically). Weibull B10 with η = 100, β = 2 is 32.459. A Weibull fit on 2,000 simulated lives (β = 2.5, η = 300, 30% censored) recovers β within ±0.15 and η within ±5%. Degenerate: constant data (MR̄ = 0) raises an error instead of returning zero-width limits; n = 1 and all-censored data raise errors.

Fixed for every team:
- The statistic lives in **one plain, tested function** (`app/qc.py` or `app/qc.R`). The API, app or
  package only calls it and displays the result. No statistics inside UI code.
- Every statistic has a test against a known answer and a degenerate case (constant data, n = 1, missing values).
- You can explain every number the tool prints. If you cannot, it is not done.

## 5. Delivery (rubric: working tool 25)
- **Stack:** dashboard (Shiny for Python).
- **Starting demo:** no Python Shiny folder exists in `demos/`, so `app/` is scaffolded to the layout `.claude/skills/connect-publish/workflows/deploy-shiny-py.yml` expects (`app.py`, pinned `requirements.txt`, `manifest.json`, `.python-version`). The four scripts (`testme`, `manifestme`, `deployme`, `README.md`) are adapted from `demos/fastapi/`, and `app/qc.py` follows the style of `demos/pypackage/src/demotool/qc.py`.

Fixed for every team:
- Start from **one** demo in `demos/`, copied to `app/`. Keep its four-script contract
  (`testme`, `manifestme`, `deployme`, `README.md`); `testme` starts the tool with one command.
- Deployed on the course **Posit Connect** server with a public URL (publisher key handed out at the
  event). Deploy early: copy one workflow from
  [`.claude/skills/connect-publish/workflows/`](.claude/skills/connect-publish/workflows/).
- A small tool that runs beats a large tool that does not.

## 6. Outputs
- **What the user sees:** (1) Fleet health tab: one row per drone with a health bar, go / watch / ground and the reason, e.g. "D-07: crashed on flight 95; motor temperature rise EWMA above its upper limit since flight 79 (first crossed on flight 74)". (2) Drone tab: EWMA and I-MR charts in °C, m/s² and V/min, with the baseline window shaded, limits drawn and out-of-control points in red, plus a one-line "how to read this". (2b) Log a flight tab: a three-part form (before / during / after) whose entry is checked against physically possible ranges, added to the fleet on screen with the drone's new status shown at once, and downloadable as flights.csv. (3) Part reliability tab: β, η and B10 for each part type, with 95% CIs, reliability curves with the Kaplan-Meier estimate overlaid, a battery lot comparison (η with 95% intervals, and a sentence saying whether the difference is beyond chance), and the parts past their B10 age, e.g. "10% of motors fail by 242 flight hours (B10)".

## 7. Test datasets and codebook (rubric: demo 10, datasets 5, codebook 5)
2-3 small CSVs in `data/`, invented but shaped like real field data, each showing one behavior.
`data/README.md` is the codebook: every file, every column with units, and what it would take to
collect this data for real.
- **Datasets:** three folders, each holding `flights.csv` and `components.csv`, generated by the seeded `data/simulate.py`: `data/healthy/` (10 drones × ~100 flights, all in control); `data/motor_drift/` (D-07's `temp_rise_c` climbs +0.20 °C per flight after flight 60 and it crashes at flight 95 (EWMA first signals at flight 74, the I chart at 83); D-03 has a one-off vibration spike at flight 80); `data/bad_battery_lot/` (lot B batteries have about 40% shorter Weibull scale).

## 8. Documentation and reproducibility (rubric: docs 10, public repo 5)
- `README.md` says what the tool does, for whom, every input and parameter, how to run it in one
  command, and walks through the demo on each test dataset.
- Public GitHub repo; a fresh clone runs `testme` and the tests pass with no extra steps.
- Submit on Devpost: the repo link plus a demo.

## 9. Out of scope
What we will NOT build, so nobody (human or agent) builds it by accident.
- Default: logins, databases, real customer data, a second statistic before the first one is tested.
- No machine-learning failure prediction; no live telemetry ingest or flight-log parsing; no Cp/Cpk (no manufacturer spec limits to compare against); no multi-fleet comparison; no competing-risks reliability model. The p-chart is a stretch goal only.
