# Flight Control — Hackathon Build Plan

We are building a **drone fleet reliability dashboard** in **Python + Shiny**, deployed to the
course Posit Connect server.

**Deadline: Sat Oct 17, 1:00 PM ET sharp** (Devpost + Canvas). Showcase 2–3 PM, attendance required.

| | |
|---|---|
| **Team** | Flight Control (on-campus track) |
| **Prompt** | Industrial Systems — Drone Delivery Fleet Maintenance |
| **User** | The fleet maintenance technician at a drone delivery startup |
| **Decision** | Before each flight: mark every drone **go / watch / ground**, and know when to replace motors and batteries before they fail |
| **Spec** | [`SPEC.md`](../SPEC.md): what the tool is |
| **Task ledger** | [`CONTRACT.yaml`](../CONTRACT.yaml): who is doing what (H-01 … H-08) |

Grading: working tool 25 · valid QC statistics 25 · design for a real user 25 · documentation 25.
**Correct statistics beat polish.**

---

## Build stages

Data comes before charts, statistics before the app, and the first deploy happens before midnight.
Before starting a task, check it out in `CONTRACT.yaml` (`status: in_progress`, your name, the time).
When it's finished, check it in (`status: done` plus a one-line result) in the same commit as the work.

### Stage 0 — Setup and spec · Fri 4:00–5:00 PM · H-01
- [x] Copy the starter bundle into our repo
- [ ] Fill in every `FILL IN` line of `SPEC.md`
- **Done when:** everyone can say the method sentence in SPEC section 4 without reading it.

### Stage 1 — Make the data · 5:00–7:00 PM · H-02
- [ ] `data/simulate.py` with a fixed random seed generates three datasets. Each is a folder holding `flights.csv` and `components.csv`:
  - `data/healthy/`: stable fleet; charts should stay in control
  - `data/motor_drift/`: drone D-07's motor temperature rise drifts up after flight 60 and it crashes at flight 95; D-03 has a one-off vibration spike (prop strike)
  - `data/bad_battery_lot/`: batteries from lot B wear out about 40% sooner
- [ ] `data/README.md` codebook: every file and column, units, and how a technician measures it
- **Done when:** the CSVs load and a quick plot shows D-07 drifting.

### Stage 2 — Control charts, tested · 7:00–10:00 PM · H-03
- [ ] `app/qc.py`: derived columns, I-MR chart, EWMA chart (plain functions, with no plotting or UI code inside)
- [ ] `tests/`: the known answers in SPEC section 4, a constant-data case, and D-07 flagged before its crash
- **Done when:** `pytest` passes.

### Stage 3 — Bare app and first deploy · 10:00 PM–12:00 AM · H-04, H-06
- [ ] Minimal Shiny app: pick a dataset and a drone, see the charts and its go / watch / ground status
- [ ] Deploy to Posit Connect while it's still ugly. Credentials go in GitHub repo secrets, **never in a file**
- **Done when:** the public URL loads in a logged-out browser.

### Stage 4 — Weibull reliability, tested · 12:00–2:00 AM · H-03
- [ ] Weibull fit for each part type with right-censoring, reporting shape β, scale η, B10 life and a replacement interval; compare battery lots
- **Done when:** the tests recover the simulated β and show lot B is shorter-lived.

### Sleep in shifts · 2:00–7:00 AM
One person stays on light work: drafting the README or styling.

### Stage 5 — Integrate and explain · Sat 7:00–10:00 AM · H-04
- [ ] Reliability tab, a plain-English sentence next to every number, redeploy
- [ ] p-chart of before-flight check failures, **only if time allows**

### Stage 6 — Docs and demo · 10:00 AM–12:00 PM · H-05, H-07
- [ ] Tool `README.md` plus function docs (inputs, parameters, outputs)
- [ ] `demo/README.md` walks through each dataset with the numbers the tool shows
- [ ] Record the demo: the tool catches D-07 before it crashes

### Stage 7 — Freeze and submit · 12:00–1:00 PM · H-08
- [ ] A fresh clone runs and its tests pass, with no extra steps
- [ ] Final deploy, then click through the live app
- [ ] Submit on Devpost, then put the repo link and Devpost link on Canvas

---

## Roles

Put your name next to a role.

| Role | Owns | Tasks | Name |
|---|---|---|---|
| Data | `data/`, simulation script, codebook | H-02 | |
| Stats (1–2 people) | `app/qc.py`, `tests/` | H-03 | |
| App and deploy | `app/` (Shiny UI), `.github/workflows/` | H-04, H-06 | |
| Docs and demo | `README.md`, `demo/`, Devpost page | H-05, H-07, H-08 | |

---

## Data at a glance

Full details are in [`data/README.md`](../data/README.md) once Stage 1 is done.

- **`flights.csv`**: one row per flight. Columns: drone, time, flight minutes, payload, ambient
  temperature, battery ID and cycle count, start and end voltage, post-flight max motor temperature
  (infrared thermometer), vibration RMS (exported from the flight controller log), before-flight
  check pass/fail, any in-flight event.
- **`components.csv`**: one row per motor, battery or propeller life. Columns: type, supplier lot,
  install and end dates, life in flight hours (motors, props) or cycles (batteries), and status
  (1 = failed, 0 = censored, i.e. still flying or removed before it failed).
- We deliberately do **not** ask for anything a technician can't measure (winding resistance,
  bearing clearance, internal battery resistance).

## Statistics at a glance

| Method | On what | Catches |
|---|---|---|
| **EWMA chart** (λ = 0.2, L = 3) | Motor temperature rise = max motor temp − ambient | Slow wear, e.g. a bearing going bad |
| **I-MR chart** | Vibration RMS, voltage sag per minute | Sudden damage, e.g. a prop strike |
| **Weibull with right-censoring** | Component lives | When each part type wears out; B10 life (the age by which 10% fail) |
| p-chart (optional) | Before-flight check failure rate | Inspection problems across the fleet |

Each drone's limits come from its **first 30 flights** (the baseline period), never from the whole series.

---

## Rules

- **No secrets in files or commits.** The Posit Connect key goes only in GitHub repo secrets.
- Before trusting any statistic, test it against a known answer, and be able to explain every number the tool prints.
- One task per person at a time. Stage explicit files (`git add <file>`, never `git add .`).
- Pull before you push. Keep commits small.

## If we fall behind, cut in this order

1. Styling
2. p-chart
3. Battery lot comparison
4. Weibull tab (keep the control charts)

**Never cut the tests, the docs or the deploy.** Together they're worth more points than features.
