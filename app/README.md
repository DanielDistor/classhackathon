# app/: the statistics, the API and the deployable app

This folder is the one app Posit Connect runs. It holds every statistic (`qc.py`), the REST API that serves
them (`api.py`), and the built React dashboard (`static/`, built from [`../web/`](../web/)).

| Path | What it serves |
|---|---|
| `/` | the React dashboard |
| `/api/...` | the JSON API the dashboard reads (below) |
| `/docs` | interactive API docs: try every route in the browser |

## Run it

```bash
./run.sh      # from the repo folder (or ./testme.sh from app/), then open http://127.0.0.1:8000
```

It installs missing Python packages (Python 3.12, `requirements.txt`), copies the test data in, rebuilds the
React app if anything in `../web/` changed (when Node.js is installed; otherwise it uses the committed
`static/`), and starts the server.

## Files

| File | Job |
|---|---|
| `qc.py` | **All the statistics.** Plain functions on pandas / NumPy inputs, no web code. Tests: `tests/test_qc.py`, `tests/test_monitor.py`, `tests/test_reliability.py` |
| `api.py` | FastAPI: loads a dataset, calls `qc.py`, returns JSON, serves `static/`. No statistics of its own. Tests: `tests/test_api.py` |
| `static/` | the built dashboard. Never edit by hand; `npm run build` in `../web/` overwrites it |
| `data/` | a copy of the repo's `data/` (made by `sync_data.sh`), because Connect only receives this folder. `tests/test_app.py` fails if it drifts |
| `testme.sh`, `manifestme.sh`, `deployme.sh` | run locally; write `manifest.json` for Posit Connect; publish |

## Settings used everywhere (`qc.py` constants)

| Name | Value | Meaning |
|---|---|---|
| `N_BASELINE` | 50 | a drone's first 50 readings set its control limits |
| `MIN_BASELINE` | 20 | fewer baseline readings than this: no limits, the drone is "not enough data" |
| `D2_N2`, `D4_N2` | 1.128, 3.267 | moving-range constants for n = 2: σ̂ = MR̄ / 1.128, MR UCL = 3.267 × MR̄ |
| `RECENT_FLIGHTS` | 10 | a signal in the last 10 readings that nobody acted on makes a Warning |
| `WARN_FLIGHTS` | 10 | a part within 10 flights of its replace-at age is "due soon" |
| `MIN_FAILURES` | 3 | a Weibull fit needs at least 3 failures |
| `BATTERIES_PER_DRONE` | 2 | each drone alternates two packs, so one charge = two drone flights |
| `MONITORED` | temp_rise_c, vibration_rms, sag_rate_v_per_min | the three readings charted for every drone |

Every function refuses bad input with a `ValueError` (the API turns it into a 422) instead of returning a
misleading number: blanks, constant data, too few baseline points, fewer than 3 failures, lives ≤ 0.

## Functions in `qc.py`

### Readings and control charts

| Function | Inputs and parameters | Returns |
|---|---|---|
| `add_derived(flights)` | the flights table | a copy with `temp_rise_c = motor_temp_max_c − ambient_temp_c` and `sag_rate_v_per_min = (voltage_start_v − voltage_end_v) / flight_min` |
| `drone_series(flights, drone_id, column)` | table, a drone, a column | that drone's readings in flight order (`flight_id`, `flight_no`, `datetime`, `value`), blanks dropped |
| `flight_numbers(flight_ids)` | flight ids like `F-07-074` | the sequence numbers (74) |
| `imr_limits(values, n_baseline=50, min_baseline=20)` | readings in time order | `center`, `lcl`, `ucl`, `sigma_hat`, `mr_bar`, `mr_ucl`, `n_baseline`. Limits = baseline mean ± 3σ̂, σ̂ = MR̄ / 1.128, MR UCL = 3.267 × MR̄. Later points never move the limits |
| `spc_rules(values, center, sigma)` | readings, the center and σ | one row per point: `rule_1` … `rule_8` (Nelson / Western Electric: beyond 3σ; 9 on one side; 6 trending; 14 alternating; 2 of 3 beyond 2σ; 4 of 5 beyond 1σ; 15 within 1σ; 8 beyond 1σ on both sides), `signal_ground` (rule 1), `signal_watch` (rules 2–8), `signal_any`, `rules_triggered` (e.g. "1, 5") |
| `imr_chart(values, n_baseline=50, min_baseline=20)` | readings | one row per point: `value`, `mr`, limits, `mr_ucl`, `baseline`, `signal_i`, `signal_mr` and every column of `spc_rules` |
| `ewma_chart(values, lam=0.2, L=3, mu0=None, sigma=None, ...)` | readings; `lam` = weight on the newest point (0 < λ ≤ 1); `L` = limit width; `mu0`, `sigma` = a known standard (left out, they come from the baseline) | one row per point: `z` = λx_t + (1 − λ)z_{t−1} with z_0 = μ₀, `center`, `lcl`, `ucl` = μ₀ ± Lσ·√(λ/(2−λ)·(1−(1−λ)^{2t})), `baseline`, `signal` |
| `reset_flights(maintenance, drone_id, column)` | the maintenance log, a drone, a chart column | the flights after which the technician acted on that chart (part replaced, repair or checked false alarm) |
| `monitor_chart(values, flight_no, resets=(), n_baseline=50, min_baseline=20, lam=0.2, L=3, fleet=None)` | readings and their flight numbers; `resets` from `reset_flights`; `fleet` = (center, σ) of the fleet's normal range | the chart the dashboard draws: I chart with all 8 rules and an EWMA. Limits come from the baseline and stay. After each reset the EWMA restarts at the center and the rules count afresh, so a run never spans a repair. During the baseline each reading is checked against the fleet range (rule 1 only). Columns: `flight_no`, `value`, limits, `z`, EWMA limits, `fleet_lcl`/`fleet_ucl`, `rule_1` … `rule_8`, `signal_ewma`, `signal_fleet`, `signal`, `what` (e.g. "EWMA; rule 1") |
| `chart_margin(value, center, lcl, ucl)` | one point and its limits | room left before the nearest limit, 1 (on the center) to 0 (at or past a limit). Used to order the drone cards |

### Drone status and the timeline

| Function | Inputs and parameters | Returns |
|---|---|---|
| `fleet_status(flights, maintenance=None, recent=10, n_baseline=50, min_baseline=20, fleet=None)` | flights, the maintenance log, the fleet reference | one row per drone: `status` (**ground** = Do not fly: the latest reading is an open signal beyond 3σ, or beyond the fleet range during the baseline, or the EWMA is beyond its limit now; **watch** = Warning: an open signal in the last `recent` readings; **go** = Can fly; **not enough data**), `reason` in words, `last_flight_no`, `n_flights`, `health`, `health_driver`. A signal is open until an action is logged on that chart |
| `maintenance_timeline(maintenance)` | the maintenance log | one row per event: `drone_id`, `lane` (part slot or "repairs"), `flight_no`, `marker` (**R** warned and replaced, **F** failed in flight, **S** special cause fixed), `trigger`, `repaired` (fixed without a new part). Checked false alarms are left out |
| `fleet_reference(reference)` | `fleet_reference.csv` | {chart: (center, σ)} from every drone's acceptance flights |

### Part life (Weibull) and replacement

| Function | Inputs and parameters | Returns |
|---|---|---|
| `weibull_fit(life, status, min_failures=3)` | lives (flight hours or charge cycles, > 0); status 1 = failed, 0 = censored (still working or removed for another reason) | `beta` (shape), `eta` (scale), each with 95% limits, `b10`, `mean_life`, `n`, `n_failed`. Two-parameter Weibull by maximum likelihood with right-censoring (lifelines). β > 1 means wear-out |
| `reliability(t, beta, eta)` | ages | R(t) = exp(−(t/η)^β), the share still working |
| `b_life(beta, eta, p=0.1)` | Weibull parameters, a fraction p | B_p = η(−ln(1 − p))^{1/β}, the age by which p of the parts fail. B10 when p = 0.1 |
| `km_curve(life, status)` | lives, status | Kaplan-Meier survival straight from the data: S(t) = S(previous) × (1 − failures at t / parts at risk at t). Drawn next to the Weibull curve as the model check |
| `fit_by_type(components)` | the parts history | one Weibull fit per part type, with its unit, and a `note` if a fit was skipped |
| `compare_lots(components, component_type="battery")` | the parts history | one fit per supplier lot. Lots whose η intervals do not overlap differ by more than chance |
| `replacement_plan(components, flights, by_type)` | parts, flights, and a replace-at policy (`replace_at.csv`) or fits | one row per installed part: `age`, `replace_at` (B_p), `remaining`, `pct_used`, `flights_left` (hours left ÷ the drone's mean flight length; batteries: charges left × 2), `days_left` (÷ the drone's flights per day), `overdue`, `due` (within 10 flights) |
| `parts_health(plan)` | `replacement_plan` output | per drone: `health` = mean over its parts of (100 − % used), clipped to 0–100 (the health bar), `worst_part`, `worst_left` |

### Cost of the replacement policy

| Function | Inputs and parameters | Returns |
|---|---|---|
| `survival_integral(t, beta, eta)` | ages, Weibull parameters | ∫₀ᵗ R(u) du = η Γ(1 + 1/β) P(1/β, (t/η)^β): the use a part delivers up to age t on average |
| `replacement_cost_rate(t, beta, eta, cp, cf)` | replace-at age t; cp = cost of a planned replacement; cf = cost of a failure in flight | long-run cost per unit of use, (cp R(t) + cf F(t)) / ∫₀ᵗ R(u) du: the age-replacement model (Barlow & Proschan). Assumes nothing warns before a failure |
| `retirement_cost(policy, costs, use_per_flight, pcts)` | Weibull per part type; {type: (cp, cf)}; use per drone-flight per type; the p values | per p and part type: `replace_at` (B_p), `fail_share`, `cost_per_use`, `cost_per_flight` |

### Input checks

| Function | Refuses |
|---|---|
| `check_flights(flights)` | missing columns, non-numeric readings, flight ids without a sequence number |
| `check_components(components)` | missing columns, non-numeric lives, status other than 0 or 1 (lives ≤ 0 are refused by `weibull_fit`) |
| `check_maintenance(maintenance)` | missing columns, actions other than replace / repair / no_fault |
| `check_replace_at(policy)` | a policy without a positive replace-at age for each part type |

## API routes (`api.py`)

Dashboard routes are `GET` and take `?dataset=` (`fleet` = Fleet A, the default, or `fleet_b` = Fleet B) and
`?retire=` (the B_p setting: 1, 2, 5, **10** (default), 15, 20 or 30; each is a separate pre-simulated run).

| Route | Returns | `qc.py` functions behind it |
|---|---|---|
| `/api/health` | `{"status": "ok"}` | |
| `/api/fleet` | every drone's status, reason and parts health; every installed part's countdown; the timeline; activity counts | `fleet_status`, `replacement_plan`, `parts_health`, `maintenance_timeline` |
| `/api/drones/{drone_id}` | one drone: status, parts, timeline, and its three control charts (one row per flight). 404 for an unknown drone | `monitor_chart`, `reset_flights`, `drone_series` |
| `/api/reliability` | Weibull fit per part type with 95% intervals, replace-at ages, R(t) and Kaplan-Meier curves | `fit_by_type`, `reliability`, `km_curve` |
| `/api/cost` | cost per drone-flight of each policy, from the model (no charts) and from the simulated runs (with charts), and the cheapest choice. Prices: `cp_motor`, `cf_motor`, `cp_propeller`, `cf_propeller`, `cp_battery`, `cf_battery` (defaults $350 / $80 / $380 planned, $8,000 per failure in flight) | `retirement_cost` |
| `/api/runs` | the slider settings and what each run replaced, caught and lost | |
| `/api/guide` | the answer key, replacement counts and example rows for the welcome page | |

Statistics on your own numbers (`POST`, JSON body):

| Route | Body | Returns |
|---|---|---|
| `/api/spc/imr` | `{"values": [...], "n_baseline": 50}` | `imr_limits` |
| `/api/spc/monitor` | `{"values": [...], "n_baseline": 50}` | `monitor_chart`, one row per reading |
| `/api/weibull` | `{"life": [...], "status": [1, 0, ...]}` | `weibull_fit` |
| `/api/upload` | a file (multipart): an `.xlsx` with `flights` and `components` sheets, optional `maintenance`; up to 10 MB | `{dataset, name, n_drones, n_flights, sources, notes}`. The sheets are checked (`check_flights`, `check_components`, `check_maintenance`), then combined with Fleet A and Fleet B: drones renamed by source (A01, B01, U01 …) in every id, replace-at ages = the B10 fitted on all the parts (`fit_by_type`), the fleet range from every drone's first 20 flights. Every `GET` route serves the result with `?dataset=<id>`; the test fleets are not changed. Bad files get a 422 naming the problem. Tests: `tests/test_upload.py` |

## Deploy (Posit Connect)

`manifestme.sh` writes `manifest.json` (`python-fastapi`, entrypoint `api:app`). Re-run it and commit the
manifest after any change to the code, the data or the build. `deployme.sh` publishes from your machine with
`CONNECT_SERVER` and `CONNECT_API_KEY` in a gitignored `app/.env`. Never commit the key.
