# Flight Control — Hackathon Build Plan

We are building a **drone fleet reliability dashboard** in **Python (FastAPI + the statistics) + React**, deployed to the
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

**Status:** Stage 0 ✅ (waiting on everyone reading SPEC section 4) · Stages 1–4 ✅ (deployed: live link in the README) · Stage 5 ✅ · Stage 6: docs ✅, demo walkthrough ✅, recording to do · **next: Stage 7** (freeze and submit)

### See the dashboard

```bash
git pull
./run.sh          # then open http://127.0.0.1:8000  (Ctrl+C to stop)
```

That's all. It installs anything missing and rebuilds the React app if someone changed it. If you
edit the dashboard (`web/src/`), just run `./run.sh` again and commit everything git shows as changed.

### How to run a stage yourself

**1. One-time setup** (Python 3.12):

```bash
git clone https://github.com/DanielDistor/classhackathon.git   # or: git pull, if you already have it
cd classhackathon
python3 -m pip install -r app/requirements.txt pytest httpx
python3 data/simulate.py      # optional: rebuilds the test data (identical output every time)
```

**2. Claim the task.** Open `CONTRACT.yaml`, find the stage's task (e.g. `H-03`), and set
`status: in_progress`, `owner: "<your name>"` and `started_at: "<YYYY-MM-DD HH:MM>"`.
Commit and push that one change right away so nobody else picks the same task.

**3. Build it with your agent.** Open your coding agent (Claude Code, Cursor, Copilot…) **inside the repo
folder**. It reads `CLAUDE.md` / `AGENTS.md` and then `SPEC.md` on its own. Give it **one** task:

```text
Do CONTRACT task H-03 only. Read SPEC.md section 4 and data/README.md first.
Write plain Python functions in app/qc.py: derived columns (temp_rise_c, sag_rate_v_per_min),
I-MR limits from a baseline of the first 30 flights (sigma = MRbar / 1.128), and an EWMA chart
(lambda 0.2, L 3, time-varying limits). No plotting, no Shiny. Write tests in tests/ FIRST:
the SPEC section 4 known answers, constant data raises an error, n = 1 raises an error,
and on data/problem_fleet D-07's EWMA on temp_rise_c first signals at flight 74.
Run pytest and paste the output. Do not commit.
```

In Claude Code you can also type `/superagent do H-03`.

**4. Check it before you trust it.** Run the task's `definition_of_done` from `CONTRACT.yaml`
yourself, e.g.:

```bash
python3 -m pytest tests -q
```

If a number looks off, ask the agent: *"Show me this calculation by hand on the known-answer data."*
Someone on the team must be able to explain every number.

**5. Check it in and push.** In `CONTRACT.yaml`, set `status: done` and write a one-line
`result` with what the test printed. Then:

```bash
git add <the files you changed> CONTRACT.yaml    # name them; never `git add .`
git commit -m "H-03: <title>; check in"
git pull --rebase && git push
```

Tell the group chat which stage is finished.

### Stage 0 — Setup and spec · Fri 4:00–5:00 PM · H-01 ✅
- [x] Copy the starter bundle into our repo
- [x] Fill in every `FILL IN` line of `SPEC.md`
- [ ] **Everyone:** read SPEC section 4 and be able to explain the method without reading it

### Stage 1 — Make the data · 5:00–7:00 PM · H-02 ✅
- [x] `data/simulate.py` with a fixed random seed generates three datasets. Each is a folder holding `flights.csv` and `components.csv`:
  - `data/problem_fleet/` (the main demo): D-07's motor temperature rise drifts up 0.20 °C per flight after flight 60 and it crashes at flight 95 (EWMA flags flight 74); D-03 has a one-off vibration spike (prop strike) on flight 80; batteries from lot B wear out about 40% sooner
  - `data/healthy/`: the same fleet with nothing planted, for comparison (changed from three datasets to two on 2026-10-16)
- [x] `data/README.md` codebook: every file and column, units, and how a technician measures it
- **Done:** CSVs load; a check found the EWMA flags D-07 at flight 74 and the I chart flags D-03 at flight 80.

### Stage 2 — Control charts, tested · 7:00–10:00 PM · H-03 ✅
- [x] **Decided: keep 30.** D-06 raises a false alarm on the healthy fleet because its first 30 flights ran
  cool by chance (see `data/README.md`, Known quirks). Keep the 30-flight baseline and explain it in
  the demo (recommended), or use 50 flights.
- [x] `app/qc.py`: derived columns, I-MR chart, EWMA chart (plain functions, with no plotting or UI code inside)
- [x] `tests/`: the known answers in SPEC section 4, a constant-data case, and D-07 flagged before its crash
- **Done:** 20 tests pass, and R's `qcc` package reproduces the same limits and signals (D-07 EWMA at flight 74, I chart at 83; D-03 at 80).

### Stage 3 — Bare app and first deploy · 10:00 PM–12:00 AM · H-04 ✅, H-06 ✅
- [x] Minimal Shiny app: pick a dataset and a drone, see the charts and its go / watch / ground status (since replaced by the React dashboard on a FastAPI API; run it with `./run.sh`)
- [x] Deploy to Posit Connect (live link in the README; redeploy with `app/deployme.sh` after `app/manifestme.sh`). **Blocked until we get the publisher key from the organizers.** Credentials never go in a committed file.
  1. Put the two values in `app/.env` (gitignored, so check with `git status` that it doesn't show up):
     `CONNECT_SERVER=...` and `CONNECT_API_KEY=...`
  2. First deploy, from a laptop: `cd app && ./deployme.sh`, then open the URL it prints in a logged-out browser.
  3. Auto-deploy on every push: add repo secrets `CONNECT_SERVER` and `CONNECT_API_KEY` (GitHub → Settings → Secrets and variables → Actions), then ask the agent: *"copy the FastAPI deploy workflow for H-06 with APP_DIR app, entrypoint api:app"*.
  4. After **any** change to `app/` or `data/`: run `app/manifestme.sh` and commit `app/manifest.json`.
- **Done when:** the public URL loads in a logged-out browser and the Fleet tab grounds D-07 on the motor-drift dataset.

### Stage 4 — Weibull reliability, tested · 12:00–2:00 AM · H-03 ✅
- [x] Weibull fit for each part type with right-censoring, reporting shape β, scale η, B10 life and a replacement interval; compare battery lots
- **Done:** 56 tests pass; the fits recover the planted lives (motors η 506 vs 500, lot B 244 vs 240) and match R's `survreg` to 4 decimals. The Part reliability tab shows it.

### Sleep in shifts · 2:00–7:00 AM
One person stays on light work: drafting the README or styling.

### Stage 5 — Integrate and explain · Sat 7:00–10:00 AM · H-04 ✅
- [x] Reliability tab, a plain-English sentence next to every number, redeploy (plus the retirement slider, Fleet B, the Cost & savings tab and the logbook upload: H-16 to H-25)
- [ ] p-chart of before-flight check failures, **only if time allows** (not done)

### Stage 6 — Docs and demo · 10:00 AM–12:00 PM · H-05, H-07
- [x] Tool `README.md` plus function docs (inputs, parameters, outputs); plain-language guide in `docs/how-it-works.md`
- [x] `demo/README.md` walks through each dataset with the numbers the tool shows
- [ ] Record the demo: a special cause caught on the chart, a worn part replaced before it fails, and the Cost & savings tab

### Stage 7 — Freeze and submit · 12:00–1:00 PM · H-08 ← **next**
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
| App and deploy | `web/` (React UI), `app/api.py` (API), `.github/workflows/` | H-04, H-06 | |
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
