# app/: Drone Fleet Reliability Monitor (Shiny for Python)

A dashboard for the **fleet maintenance technician** at a drone delivery startup. Before each flight it
shows whether every drone is **go**, **watch** or **ground** and why, and it shows how long motors,
propellers and batteries last, so parts can be replaced before they fail in the air.

## Run it

```bash
cd app
python3 -m pip install -r requirements.txt   # Python 3.12
./testme.sh                                  # copies the test data in, then serves http://127.0.0.1:8000
```

## How the app is laid out

1. **Welcome page.** Covers how the tool works, the six things measured on each drone (with a labelled
   picture), what's recorded before, during and after each flight, example rows from both data files, the
   three test datasets, key terms, and the views. **Continue** opens the dashboard; the header link
   goes back.
2. **Dashboard: which fleet?** A switch at the top picks one of two invented test fleets (the same 10 drones):

   | Card | Folder | What's planted |
   |---|---|---|
   | Fleet with problems (shown first) | `data/problem_fleet/` | D-07's motor wears out and it crashes on flight 95; D-03 has a prop strike on flight 80; batteries from supplier lot B wear out about 40% sooner |
   | Healthy fleet | `data/healthy/` | Nothing (the comparison) |

3. **The views of that fleet:**
   - **Fleet status:** a count of drones that **Can fly**, have a **Warning**, or must **Not fly**, then all 10
     drones as cards in two rows: each drawn in its status colour with a ✓ / ! / ✕ symbol, a **health bar** and
     the reason. **Click a card** to open that drone in a pop-up: a status banner, a table of the
     numbers behind every chart (baseline mean, limits, latest value, room left, signals), and four control charts
     (an EWMA and an I chart of motor temperature rise, plus I charts of vibration and battery voltage sag).
   - **Parts replacement:** one card per part type with its replace-at age (B10) in flight hours or charges and
     in flights; then a table of the 10 drones, each with its 4 motors, 4 propellers and 2 batteries shown as
     "life used" bars with days left or *overdue*, and what to do next; then "Why these numbers": reliability
     curves with the Kaplan-Meier check, and the battery-batch comparison.

## Files

| File | Job |
|---|---|
| `qc.py` | **All the statistics.** Plain, tested functions (below). Tests: `tests/test_qc.py`, `tests/test_reliability.py` |
| `charts.py` | Draws what `qc.py` computed (matplotlib). No statistics |
| `app.py` | The Shiny app: reads the chosen dataset, calls `qc.py`, shows the result |
| `intro.py` | The welcome page. Edit the wording here |
| `styles.css` | The look of both pages |
| `data/` | A copy of the repo's `data/`, made by `sync_data.sh`, because Posit Connect only receives this folder. `tests/test_app.py` fails if the copy drifts |
| `testme.sh` / `manifestme.sh` / `deployme.sh` | Run locally / write `manifest.json` for Posit Connect / publish |

## Functions in `qc.py`

**Control charts and status**

| Function | Inputs | Returns |
|---|---|---|
| `add_derived(flights)` | flights table | a copy with `temp_rise_c = motor_temp_max_c − ambient_temp_c` and `sag_rate_v_per_min = (voltage_start_v − voltage_end_v) / flight_min` |
| `drone_series(flights, drone_id, column)` | table, drone, column | that drone's readings in flight order, blanks dropped |
| `imr_limits(x, n_baseline=30, min_baseline=20)` | numbers | `center`, `lcl`, `ucl`, `sigma_hat`, `mr_bar`, `mr_ucl`. Limits = baseline mean ± 3σ̂, σ̂ = MR̄ / 1.128, MR UCL = 3.267 × MR̄ |
| `imr_chart(x, ...)` | numbers | one row per point: `value`, `mr`, limits, `baseline`, `signal_i`, `signal_mr` |
| `ewma_chart(x, lam=0.2, L=3, ...)` | numbers | one row per point: `z`, `center`, `lcl`, `ucl`, `signal`. z_t = λx_t + (1−λ)z_(t−1); limits μ₀ ± Lσ·√(λ/(2−λ)·(1−(1−λ)^(2t))) |
| `chart_margin(value, center, lcl, ucl)` | one point and its limits | room left before the nearest limit, from 1 (at center) to 0 (at or past a limit) |
| `fleet_status(flights, recent=10)` | flights table | per drone: `status`, `reason`, `health`, `health_driver`, `last_flight_no`, `n_flights` |
| `check_flights(flights)` | flights table | the table if usable, otherwise a ValueError naming the problem |

**Status rule.** *Do not fly* (`ground`): the latest flight was a crash, or the latest reading is outside an I-chart limit,
or the EWMA is outside its limit now. *Warning* (`watch`): a signal within the last 10 readings. *Can fly* (`go`): everything in
control. **Health** = `chart_margin` of the latest point on the drone's most-stretched chart (0 after a crash).

**Reliability**

| Function | Inputs | Returns |
|---|---|---|
| `weibull_fit(life, status)` | lives (> 0) and 1 = failed / 0 = censored | `beta`, `eta` with 95% limits, `b10`, `mean_life`, `n`, `n_failed`. Maximum likelihood with right-censoring |
| `b_life(beta, eta, p=0.10)` | Weibull parameters | age by which a fraction p fail: η(−ln(1−p))^(1/β). B10 when p = 0.10 |
| `reliability(t, beta, eta)` | ages | share still working: exp(−(t/η)^β) |
| `km_curve(life, status)` | lives, status | Kaplan-Meier survival from the data (the model check) |
| `fit_by_type(components)` | components table | one Weibull fit per part type, with its unit (flight hours or charge cycles) |
| `compare_lots(components, "battery")` | components table | one fit per supplier lot. Lots whose η intervals don't overlap differ by more than chance |
| `parts_past_b10(components, by_type)` | components, fits | parts still flying that are older than their type's B10, most overdue first |
| `replacement_plan(components, flights, by_type)` | components, flights, fits | per part in service: `remaining` = B10 − age, `pct_used`, `flights_left` (hours ÷ the drone's mean flight length; batteries: charges × 2, since each drone alternates two batteries), `days_left` (÷ the drone's flights per day), `overdue` |
| `check_components(components)` | components table | the table if usable, otherwise a ValueError |

Every function refuses bad input with a `ValueError` instead of returning a misleading number. Examples:
constant data (limits undefined), fewer than 20 baseline points, blanks, fewer than 3 failures for a Weibull
fit, and lives ≤ 0.
