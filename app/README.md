# app/: Drone Fleet Reliability Monitor (Shiny for Python)

A dashboard for the **fleet maintenance technician**. Before each flight it shows whether every drone is
**go**, **watch** or **ground**, and why, from the flight log the technician already keeps.

## Run it

```bash
cd app
./testme.sh          # copies the test data in, then serves http://127.0.0.1:8000
```

Needs Python 3.12 and the packages in `requirements.txt` (`python3 -m pip install -r requirements.txt`).

## Files

| File | Job |
|---|---|
| `qc.py` | **All the statistics.** Plain, tested functions (see below). Tests: `tests/test_qc.py` |
| `charts.py` | Draws what `qc.py` computed (matplotlib). No statistics |
| `app.py` | The Shiny app: loads a dataset, calls `qc.py`, shows the result |
| `intro.py` | The welcome page (datasets, key terms, the tabs). Edit the wording here |
| `styles.css` | The look of both pages (colors, cards, status labels) |
| `data/` | A copy of the repo's `data/` test datasets, made by `sync_data.sh` (Connect only receives this folder). `tests/test_app.py` fails if the copy drifts |
| `testme.sh` | Run locally, one command |
| `manifestme.sh` | Write `manifest.json` for Posit Connect. Run on your own machine and commit the result |
| `deployme.sh` | Publish to Posit Connect from your machine (key in a gitignored `app/.env`) |

## The pages

The app opens on a **welcome page**: how the tool works, the three test datasets and what to look for in
each, key terms (baseline, control limits, σ̂, signal, EWMA, I chart, temperature rise, voltage sag,
go/watch/ground), and what each tab shows. **Continue** opens the dashboard, and the header link goes back.


- **Fleet**: one row per drone with its status and the reason in plain English.
- **Drone**: a status banner, a table of the numbers behind every chart (baseline mean, limits, latest
  value, signals), then four control charts: an EWMA and an I chart of motor temperature rise, plus I charts
  of vibration and battery voltage sag per minute. A red ✕ marks a signal.
- **Reliability**: Weibull life analysis (Stage 4, not built yet).

You can pick a bundled test dataset or upload your own `flights.csv` with the columns in
[`data/README.md`](../data/README.md). An upload missing a column is refused with a message naming it.

## Functions in `qc.py`

| Function | Inputs | Returns |
|---|---|---|
| `add_derived(flights)` | flights table | copy with `temp_rise_c = motor_temp_max_c − ambient_temp_c` and `sag_rate_v_per_min = (voltage_start_v − voltage_end_v) / flight_min` |
| `drone_series(flights, drone_id, column)` | table, drone, column | that drone's readings in flight order, blanks dropped: `flight_id`, `flight_no`, `datetime`, `value` |
| `imr_limits(x, n_baseline=30, min_baseline=20)` | numbers | `center`, `lcl`, `ucl`, `sigma_hat`, `mr_bar`, `mr_ucl`, `n_baseline`. Limits = baseline mean ± 3σ̂, σ̂ = MR̄ / 1.128, MR UCL = 3.267 × MR̄ |
| `imr_chart(x, ...)` | numbers | one row per point: `value`, `mr`, limits, `baseline`, `signal_i`, `signal_mr` |
| `ewma_chart(x, lam=0.2, L=3, mu0=None, sigma=None, ...)` | numbers | one row per point: `z` (the EWMA), `center`, `lcl`, `ucl`, `signal`. z_t = λx_t + (1−λ)z_(t−1); limits μ₀ ± Lσ·√(λ/(2−λ)·(1−(1−λ)^(2t))) |
| `fleet_status(flights, recent=10, ...)` | flights table | per drone: `status`, `reason`, `last_flight_no`, `n_flights` (rule below) |
| `check_flights(flights)` | uploaded table | the table if usable, otherwise a ValueError naming the problem |

**Status rule.** *Ground*: the latest flight was a crash, or the latest reading is outside an I-chart limit,
or the EWMA is outside its limit now. *Watch*: a signal within the last 10 readings. *Go*: everything in
control. *Not enough data*: fewer than 20 readings, so no limits can be drawn.

Every function refuses bad input with a `ValueError` rather than returning a misleading number:
constant data (no variation, so limits are undefined), fewer than 20 baseline points, blanks or text.
