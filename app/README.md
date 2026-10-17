# app/: Drone Fleet Health & Part Wear Monitor (FastAPI + React)

A dashboard for the **fleet maintenance technician** at a drone delivery startup. It shows whether each of
the 10 drones **can fly**, has a **warning** or must **not fly**, and why; which parts are due for
replacement; and how long motors, propellers and batteries last, so parts are replaced before they fail
in the air.

This folder is the one app Posit Connect runs:

| Path | What it serves |
|---|---|
| `/` | the **React dashboard** (built from [`../web/`](../web/) into `static/`) |
| `/api/...` | the **REST API** the dashboard reads (JSON), below |
| `/docs` | interactive API docs: try every route in the browser |

## Run it

```bash
cd app
python3 -m pip install -r requirements.txt   # Python 3.12
./testme.sh                                  # copies the test data in, then serves http://127.0.0.1:8000
```

`static/` (the React build) is committed, so this works without Node.js. After editing `../web/src/`,
rebuild it with `cd ../web && npm run build` (Node.js 20+), or work live with `npm run dev`
there (see [`../web/README.md`](../web/README.md)).

## Files

| File | Job |
|---|---|
| `qc.py` | **All the statistics.** Plain, tested functions (below). Tests: `tests/test_qc.py`, `tests/test_monitor.py`, `tests/test_reliability.py` |
| `api.py` | The FastAPI app: loads `data/fleet/`, calls `qc.py`, returns JSON, serves `static/`. No statistics of its own. Tests: `tests/test_api.py` (every route matches `qc.py` directly) |
| `static/` | The built React app. Never edit by hand: it is overwritten by `npm run build` in `../web/` |
| `data/` | A copy of the repo's `data/`, made by `sync_data.sh`, because Posit Connect only receives this folder. `tests/test_app.py` fails if the copy drifts |
| `testme.sh` / `manifestme.sh` / `deployme.sh` | Run locally / write `manifest.json` for Posit Connect / publish |

## API routes

Dashboard routes (`GET`, computed once from `data/fleet/`):

| Route | Returns |
|---|---|
| `/api/health` | `{"status": "ok"}` |
| `/api/fleet` | every drone's `status` and `reason` (`qc.fleet_status`), every installed part's countdown (`qc.replacement_plan`), the R / F / S `timeline` (`qc.maintenance_timeline`) and the activity counts |
| `/api/drones/{drone_id}` | one drone: status, parts, timeline, and its three restarting control charts (`qc.monitor_chart`), one row per flight with the limits, EWMA and every signal. 404 for an unknown drone |
| `/api/reliability` | Weibull fit per part type (`qc.fit_by_type`), the shop's replace-at ages, R(t) and Kaplan-Meier curves (`qc.reliability`, `qc.km_curve`) |
| `/api/guide` | the answer key's injected special causes, replacement counts and example rows for the guide page |

Statistics on **your own numbers** (`POST`, JSON body; 422 with a plain message on bad input):

| Route | Body | Returns |
|---|---|---|
| `/api/spc/imr` | `{"values": [...], "n_baseline": 50}` | I-MR limits (`qc.imr_limits`) |
| `/api/spc/monitor` | `{"values": [...], "n_baseline": 50}` | I chart with all 8 rules + EWMA, one row per reading (`qc.monitor_chart`) |
| `/api/weibull` | `{"life": [...], "status": [1, 0, ...]}` | β, η, 95% intervals, B10 (`qc.weibull_fit`) |

## Functions in `qc.py`

**Control charts and status**

| Function | Inputs | Returns |
|---|---|---|
| `add_derived(flights)` | flights table | a copy with `temp_rise_c = motor_temp_max_c − ambient_temp_c` and `sag_rate_v_per_min = (voltage_start_v − voltage_end_v) / flight_min` |
| `drone_series(flights, drone_id, column)` | table, drone, column | that drone's readings in flight order, blanks dropped |
| `imr_limits(x, n_baseline=50, min_baseline=20)` | numbers | `center`, `lcl`, `ucl`, `sigma_hat`, `mr_bar`, `mr_ucl`. Limits = baseline mean ± 3σ̂, σ̂ = MR̄ / 1.128, MR UCL = 3.267 × MR̄ |
| `spc_rules(x, center, sigma)` | numbers, limits | the 8 Nelson / Western Electric rules, one column each, plus `rules_triggered` |
| `ewma_chart(x, lam=0.2, L=3, ...)` | numbers | `z`, limits, `signal`. z_t = λx_t + (1−λ)z_(t−1); limits μ₀ ± Lσ·√(λ/(2−λ)·(1−(1−λ)^(2t))) |
| `monitor_chart(values, flight_no, resets, fleet=None)` | readings, flight numbers, repair flights | I chart (8 rules) + EWMA that restart after each logged repair; the baseline is checked against the fleet range (rule 1) |
| `fleet_status(flights, maintenance, fleet=...)` | flights, maintenance log | per drone: `status`, `reason`, `health`, `health_driver` |
| `maintenance_timeline(maintenance)` | maintenance log | every R / F / S marker with its trigger |
| `check_flights`, `check_maintenance`, `check_replace_at`, `fleet_reference` | tables | the table if usable, otherwise a ValueError naming the problem |

**Status rule.** *Do not fly* (`ground`): the latest reading is an open signal beyond 3σ (or the fleet range
during the baseline), or the EWMA is beyond its limit now. *Warning* (`watch`): an open signal within the last
10 readings. *Can fly* (`go`): no open signal. A signal is open until the technician logs an action on that chart.

**Reliability**

| Function | Inputs | Returns |
|---|---|---|
| `weibull_fit(life, status)` | lives (> 0) and 1 = failed / 0 = censored | `beta`, `eta` with 95% limits, `b10`, `mean_life`, `n`, `n_failed`. Maximum likelihood with right-censoring |
| `b_life(beta, eta, p=0.10)` | Weibull parameters | η(−ln(1−p))^(1/β). B10 when p = 0.10 |
| `reliability(t, beta, eta)` | ages | exp(−(t/η)^β) |
| `km_curve(life, status)` | lives, status | Kaplan-Meier survival from the data (the model check) |
| `fit_by_type(components)` | parts history | one Weibull fit per part type, with its unit |
| `compare_lots(components, "battery")` | parts history | one fit per supplier lot |
| `replacement_plan(components, flights, by_type)` | parts, flights, replace-at ages | per installed part: `pct_used`, `flights_left`, `days_left`, `overdue`, `due` |

Every function refuses bad input with a `ValueError` (the API turns it into a 422) instead of returning a
misleading number: constant data, fewer than 20 baseline points, blanks, fewer than 3 failures for a
Weibull fit, lives ≤ 0.

## Deploy (Posit Connect)

`manifestme.sh` writes `manifest.json` (`python-fastapi`, entrypoint `api:app`); commit it after any change to
the code, the data or the React build. `deployme.sh` publishes from your machine with `CONNECT_SERVER` and
`CONNECT_API_KEY` in a gitignored `app/.env`. Never put the key in a file that is committed.
