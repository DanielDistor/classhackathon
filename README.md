# Drone Fleet Reliability Monitor

**Team Flight Control** · Cornell Six Sigma Hackathon 2026 · prompt: *Drone Delivery Fleet Maintenance*

A maintenance tool for a delivery drone fleet. Before each flight it tells the technician which drones can
fly, which need a check and which should not fly, and why. It also tells them which motors, propellers
and batteries to replace before they fail.

> **The problem (from the prompt).** A drone delivery startup is experiencing mid-air failures, but it only
> investigates after a crash. Technicians need a way to log wear and tear before and during each flight,
> and to use it to manage and improve the fleet's reliability.

**Live app:** <https://connect.systems-apps.com/content/60eb66a4-d370-4e6b-81e6-ae992820bd4e/> (Posit Connect; API docs at [`/docs`](https://connect.systems-apps.com/content/60eb66a4-d370-4e6b-81e6-ae992820bd4e/docs)). **Walkthrough with every number:** [`demo/README.md`](demo/README.md).

## Run it

```bash
git clone https://github.com/DanielDistor/classhackathon.git
cd classhackathon
./run.sh            # then open http://127.0.0.1:8000
```

`run.sh` installs the Python packages if they are missing (Python 3.12, `app/requirements.txt`), copies the
test data into `app/`, rebuilds the React app if its code changed, and starts the server. Node.js is only
needed if you edit `web/`. Run the tests with:

```bash
python3 -m pip install pytest httpx
python3 -m pytest -q          # statistics, API and data tests
cd web && npm ci && npm test  # front-end formatting and chart-scale tests
```

## Who it is for and what they do

The user is the **fleet maintenance technician**. Their only inputs are the readings they already take:

| When | What they record | Column |
|---|---|---|
| Before take-off | battery voltage, air temperature | `voltage_start_v`, `ambient_temp_c` |
| During the flight (from the flight controller log) | flight time, vibration, any alert | `flight_min`, `vibration_rms`, `inflight_event` |
| Right after landing | hottest motor temperature, battery voltage | `motor_temp_max_c`, `voltage_end_v` |
| Whenever a part changes | which part, and why | `maintenance.csv`, `components.csv` |

The tool turns these into three views:

1. **Fleet health & replacements.** Every drone marked *Can fly*, *Warning* or *Do not fly* with the reason,
   a parts health bar, the parts due soon, and a timeline of every replacement and repair. Clicking a
   drone opens its parts, its timeline and its three control charts (one at a time, picked from a dropdown).
2. **Weibull reliability & replace-at ages.** How long each part type lasts and the age to replace it at.
3. **Cost & savings.** What the replacement policy costs per flight, with and without the control charts.
4. **Combined (after an upload).** The box at the top of the dashboard takes the technician's own Excel
   workbook (`flights` and `components` sheets, optional `maintenance`). It is combined with Fleet A and Fleet B
   into one fleet on a new **Combined** tab: drones renamed by source (A01–A10, B01–B10, U01…), the fleet
   cards and drone pop-ups, and the Weibull fits on all the parts together. The three tabs above keep showing
   the test fleets unchanged. An example workbook,
   [`data/example_upload/example_logbook.xlsx`](data/example_upload/example_logbook.xlsx) (a third simulated
   fleet), can be downloaded from the same box.

A slider sets the replacement policy (replace parts at B1 to B30, below), and a dropdown switches between the
two test fleets.

## The statistics

All the statistics are plain, tested functions in [`app/qc.py`](app/qc.py). The API and the dashboard only
call them. They are checked against hand-worked answers, degenerate inputs (constant data, too few points,
no failures) and the simulator's answer key, in [`tests/`](tests/).

**1. Control charts, one per reading per drone.** Three readings are charted:
`temp_rise_c = motor_temp_max_c − ambient_temp_c` (motor wear), `vibration_rms` (propeller damage) and
`sag_rate_v_per_min = (voltage_start_v − voltage_end_v) / flight_min` (battery wear).

- **Baseline:** each drone's first 50 flights set its limits, which never move. During those flights each
  reading is checked against the fleet's normal range from acceptance flights (rule 1 only).
- **I chart:** center x̄, limits x̄ ± 3σ̂, with σ̂ = MR̄ / 1.128 (MR̄ = average moving range).
- **All 8 Nelson / Western Electric rules** (one point beyond 3σ, 9 on one side, 6 trending, 14 alternating,
  2 of 3 beyond 2σ, 4 of 5 beyond 1σ, 15 within 1σ, 8 beyond 1σ on both sides).
- **EWMA** for slow wear: z_t = λx_t + (1 − λ)z_{t−1}, λ = 0.2, limits μ₀ ± 3σ̂·√(λ/(2−λ)·(1−(1−λ)^{2t})).
- **Restart after a repair:** after any logged action the EWMA and the rules start again; the limits stay.

**2. Drone status.** *Do not fly*: the latest reading is beyond 3σ, or the EWMA is beyond its limit now.
*Warning*: an open signal (not yet acted on) in the last 10 flights. *Can fly*: no open signal.

**3. Weibull life per part type.** Two-parameter Weibull fitted by maximum likelihood with right-censoring
(parts still flying or removed for another reason count as "lasted at least this long"), with 95%
intervals. R(t) = exp(−(t/η)^β). The replace-at age is **B_p** = η(−ln(1 − p))^{1/β}, the age by which p% of
parts fail; the default is B10. A Kaplan-Meier curve from the same data checks the fit.

**4. Parts health and countdown.** Each installed part's life left = 100 − % of its B_p used (0 to 100); the
drone's bar is the average over its 10 parts. Flights left = (B_p − age) ÷ the drone's mean flight length
(batteries: charges left × 2, since the drone alternates two packs).

**5. Cost of the policy.** The age-replacement model (Barlow & Proschan): cost per unit of use =
(c_p R(t) + c_f F(t)) / ∫₀ᵗ R(u) du, where c_p is a planned replacement and c_f a failure in flight. It is
compared with the simulated runs, where the control charts warn before a failure.

## Test data

Two invented fleets from the same seeded simulator ([`data/simulate.py`](data/simulate.py)), each 10 drones
× 300 flights (Jul 1 – Sep 29, 2026). The codebook, with every column and how the data were generated, is
[`data/README.md`](data/README.md).

| Folder | Name | Seed | Planted problems | At B10: parts replaced (caught worn by a chart) | Failed in flight |
|---|---|---|---|---|---|
| [`data/fleet/`](data/fleet/) | Fleet A (main demo) | 5300 | 17 | 99 (15) | 0 |
| [`data/fleet_b/`](data/fleet_b/) | Fleet B | 7100 | 11 | 119 (15) | 0 |

Each part wears out at its own random Weibull life and pushes one reading up near the end. On top of that,
special causes (prop strikes, hard landings, bad battery cells, loose connectors and mounts) are planted at
random. The answer key (`answer_key.csv`) lists every one, and the tests check the tool catches all of them.

## API

The dashboard reads everything from a REST API ([`app/api.py`](app/api.py), FastAPI). Interactive docs are at
<http://127.0.0.1:8000/docs>. Every dashboard route takes `?dataset=fleet|fleet_b` and `?retire=` (the B_p
setting: 1, 2, 5, 10, 15, 20 or 30).

| Route | Returns |
|---|---|
| `GET /api/fleet` | every drone's status and reason, parts health, every installed part's countdown, the timeline |
| `GET /api/drones/{id}` | one drone: its three control charts (one row per flight, with limits, EWMA and signals), parts, timeline |
| `GET /api/reliability` | Weibull fit per part type with 95% intervals, replace-at ages, R(t) and Kaplan-Meier curves |
| `GET /api/cost` | cost per flight of each policy, from the cost model and from the simulated runs |
| `GET /api/runs`, `GET /api/guide` | the slider's runs; the answer key and example rows for the welcome page |
| `POST /api/spc/imr` | I-MR limits for your own readings: `{"values": [...], "n_baseline": 50}` |
| `POST /api/spc/monitor` | I chart with all 8 rules + EWMA for your own readings |
| `POST /api/weibull` | Weibull fit for your own part lives: `{"life": [...], "status": [1, 0, ...]}` |
| `POST /api/upload` | combines your logbook (`.xlsx`) with Fleet A and Fleet B and returns the combined dataset's id; the routes above serve it with `?dataset=<id>` |

Bad input gets a 422 with a plain message instead of a misleading number. The functions behind each route
are listed in [`app/README.md`](app/README.md).

## Repository

| Path | What is in it |
|---|---|
| `app/` | `qc.py` (statistics), `api.py` (API, also serves the dashboard), `static/` (built dashboard), deploy scripts |
| `web/` | the React dashboard source ([`web/README.md`](web/README.md)) |
| `data/` | the two test fleets, the simulator and the codebook |
| `tests/` | pytest: known answers, degenerate cases, the answer key, API matches `qc.py` |
| `demo/` | the walkthrough of both fleets |
| `docs/` | [how it works](docs/how-it-works.md), [plan](docs/plan.md), [build plan](docs/build-plan.md); the event pages ([rubric](docs/criteria.md), [schedule](docs/schedule.md)) |
| `SPEC.md`, `CONTRACT.yaml` | what the tool is, and the team's task ledger |

## Deploy

Posit Connect runs `app/` as one FastAPI app (entrypoint `api:app`), which serves the API and the dashboard.
`app/manifestme.sh` writes `manifest.json`; `app/deployme.sh` publishes with `CONNECT_SERVER` and
`CONNECT_API_KEY` in a gitignored `app/.env`. No key is stored in this repo.

## Credits

Built with Python (pandas, NumPy, SciPy, lifelines, FastAPI) and React (Vite). Starter code, skills and
deploy scripts from the course's hackathon template; the age-replacement cost model follows Barlow &
Proschan, *Mathematical Theory of Reliability* (1965). All data are simulated.
