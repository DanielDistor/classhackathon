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
- **Method:** (1) For each drone and each of its three readings (`temp_rise_c`, `vibration_rms`, `sag_rate_v_per_min`), an I chart with all 8 Nelson / Western Electric tests to catch sudden damage, shifts and patterns, plus an EWMA (λ = 0.2, L = 3) on the same reading to catch slow wear (`qc.monitor_chart`). Limits come from that drone's first 50 flights (the Phase I baseline) and never move: σ̂ = MR̄ / 1.128, limits x̄ ± 3σ̂, MR UCL = 3.267 × MR̄. EWMA: z_t = λx_t + (1-λ)z_{t-1}, z_0 = baseline mean, limits μ₀ ± Lσ̂·sqrt(λ/(2-λ)·(1-(1-λ)^{2t})). During the baseline each reading is checked against the fleet's normal range from acceptance flights (rule 1 only). After any logged action (part replaced, repair, checked false alarm) the EWMA restarts at the center and the rules count afresh, so a run never spans a repair. (2) For each component type, a two-parameter Weibull fit by maximum likelihood with right-censoring (`lifelines.WeibullFitter`), reporting shape β and scale η with 95% CIs and the replace-at age B_p = η(-ln(1-p))^{1/β}; the default policy is B10 and the slider shows B1 to B30. (3) The cost of a policy: the age-replacement model (cp R(t) + cf F(t)) / ∫₀ᵗ R(u) du, compared with the simulated runs. Status rule (`qc.fleet_status`): **ground** (Do not fly) = the latest reading is an open signal beyond 3σ (or beyond the fleet range during the baseline), or the EWMA is beyond its limit now; **watch** (Warning) = an open signal in the last 10 flights; **go** (Can fly) = otherwise. A signal is open until an action is logged on that chart. Parts are replaced when they reach B_p or when a chart shows them worn, before the next flight. **Health bar** = parts health: each installed part's share of its replace-at life left, 100 − % used clipped to [0, 100], averaged over the drone's 10 parts (`qc.parts_health`). A Kaplan-Meier curve is drawn next to each Weibull fit as the goodness-of-fit check. Decisions and their dates: `docs/plan.md`.
- **Why it fits the use case:** wear shows up as small sustained shifts, which the EWMA catches flights earlier than a raw chart; sudden damage shows up as single large points (I-MR); and most parts never fail before removal, so life estimates must handle censoring.
- **Assumptions and how the tool checks them:** the baseline is in control (the charts shade the baseline window; fewer than 20 baseline flights gives no limits); flights are roughly independent; ambient temperature is the main confounder of motor temperature, so we chart the rise over ambient, not raw temperature; the Weibull model fits (the Kaplan-Meier curve from the same data is drawn next to it, and β has a 95% CI); censoring is independent of failure, and there is one wear mode per component type. With all 8 rules about 2% of in-control readings signal by chance; the simulated technician checks those and logs no fault.
- **Known-answer check:** I-MR on x = [10, 12, 11, 13, 12] gives center 11.6, MR̄ 1.5, σ̂ 1.3298, UCL 15.589, LCL 7.611, MR UCL 4.901. EWMA with λ = 0.2, μ₀ = 10, σ = 1, L = 3 on x = [11, 12] gives z = 10.2, 10.56 and limit half-widths 0.600, 0.7684 (1.000 asymptotically). Weibull B10 with η = 100, β = 2 is 32.459. A Weibull fit on 2,000 simulated lives (β = 2.5, η = 300, 30% censored) recovers β within ±0.15 and η within ±5%. Degenerate: constant data (MR̄ = 0) raises an error instead of returning zero-width limits; n = 1 and all-censored data raise errors.

Fixed for every team:
- The statistic lives in **one plain, tested function** (`app/qc.py` or `app/qc.R`). The API, app or
  package only calls it and displays the result. No statistics inside UI code.
- Every statistic has a test against a known answer and a degenerate case (constant data, n = 1, missing values).
- You can explain every number the tool prints. If you cannot, it is not done.

## 5. Delivery (rubric: working tool 25)
- **Stack:** React dashboard (Vite, `web/`) on a FastAPI REST API (`app/api.py`) over the statistics in `app/qc.py`. Changed from Shiny for Python on 2026-10-16 because the professor requires React; the statistics did not change.
- **Starting demo:** `web/` is copied from `demos/reactfront/` and `app/api.py` follows `demos/fastapi/` (the `fastapi-react-scaffold` skill). One Posit Connect app: `app/api.py` serves the JSON API under `/api/`, its docs at `/docs`, and the React build (`app/static/`) at `/`. The four scripts (`testme`, `manifestme`, `deployme`, `README.md`) live in `app/`, and `app/qc.py` follows the style of `demos/pypackage/src/demotool/qc.py`.

Fixed for every team:
- Start from **one** demo in `demos/`, copied to `app/`. Keep its four-script contract
  (`testme`, `manifestme`, `deployme`, `README.md`); `testme` starts the tool with one command.
- Deployed on the course **Posit Connect** server with a public URL (publisher key handed out at the
  event). Deploy early: copy one workflow from
  [`.claude/skills/connect-publish/workflows/`](.claude/skills/connect-publish/workflows/).
- A small tool that runs beats a large tool that does not.

## 6. Outputs
- **What the user sees:** a one-screen welcome page (the problem, what the dashboard does, how it works, the labelled drone, reference dropdowns), then three tabs. (1) **Fleet health & replacements:** counts of drones that Can fly, have a Warning or must Not fly; parts due soon; the 10 drones as cards (status colour and symbol, parts health bar, next part due, reason); the fleet maintenance timeline (R / F / S). Clicking a card opens the drone: status, parts health, its part-slot timeline, its installed parts with flights left, and its three control charts, one at a time from a dropdown. (2) **Weibull reliability & replace-at ages:** the replace-at age per part type, the Weibull curve against Kaplan-Meier, the fitted parameters with 95% CIs, every drone's schedule. (3) **Cost & savings:** cost per drone-flight with and without the charts. At the top, a dropdown picks Fleet A or Fleet B and a slider sets the replace-at policy (B1 to B30).

## 7. Test datasets and codebook (rubric: demo 10, datasets 5, codebook 5)
2-3 small CSVs in `data/`, invented but shaped like real field data, each showing one behavior.
`data/README.md` is the codebook: every file, every column with units, and what it would take to
collect this data for real.
- **Datasets:** two fleets, generated by the seeded `data/simulate.py` (same design, different seed, so
  independent part lives, problems and timing): **Fleet A** `data/fleet/` (seed 5300, 17 special causes) and
  **Fleet B** `data/fleet_b/` (seed 7100, 11 special causes). Each: 10 drones × 300 flights with wear on every
  part, random special causes in the 8 rule shapes, and a simulated technician acting on the tool, as
  `flights.csv`, `components.csv`, `maintenance.csv`, `replace_at.csv`, `fleet_reference.csv` and
  `answer_key.csv` (the injected problems, for the tests only), plus `runs/` (the same fleet under each
  retirement setting B1–B30). Team decisions 2026-10-16 (docs/plan.md): one active fleet replaced the old
  problem/healthy pair; Fleet B added for the 2-dataset rubric line.

## 8. Documentation and reproducibility (rubric: docs 10, public repo 5)
- `README.md` says what the tool does, for whom, every input and parameter, how to run it in one
  command, and walks through the demo on each test dataset.
- Public GitHub repo; a fresh clone runs `testme` and the tests pass with no extra steps.
- Submit on Devpost: the repo link plus a demo.

## 9. Out of scope
What we will NOT build, so nobody (human or agent) builds it by accident.
- Default: logins, databases, real customer data, a second statistic before the first one is tested.
- No machine-learning failure prediction; no live telemetry ingest or flight-log parsing; no Cp/Cpk (no manufacturer spec limits to compare against); no multi-fleet comparison; no competing-risks reliability model. The p-chart is a stretch goal only.
