# Plan: Flight Control drone fleet reliability tool

Team schedule and how-to steps: [`build-plan.md`](build-plan.md). "Stage N" there = the task ids below.
Done: H-02 (data). H-01: SPEC filled; only the team readback of SPEC section 4 is left (human, not an agent task).

## Tasks, in order

1. **H-03a: control charts** (Stage 2, ~3 h). Files: `app/qc.py`, `app/requirements.txt`, `tests/`.
   - `add_derived(flights)`: `temp_rise_c = motor_temp_max_c - ambient_temp_c`; `sag_rate_v_per_min = (voltage_start_v - voltage_end_v) / flight_min`. Rows with a blank reading are dropped from that chart.
   - `imr_limits(x, n_baseline=30)`: baseline = first 30 points. MR_i = |x_i - x_(i-1)|, σ̂ = MR̄ / 1.128. I chart: center x̄, limits x̄ ± 3σ̂. MR chart: UCL = 3.267 × MR̄, LCL 0. Signal = a point beyond a limit (rule 1 only).
   - `ewma_chart(x, lam=0.2, L=3, n_baseline=30)`: z_0 = baseline mean μ₀, z_t = λx_t + (1-λ)z_(t-1); limits μ₀ ± Lσ̂·sqrt(λ/(2-λ)·(1-(1-λ)^(2t))), σ̂ from the baseline as above. Returns one row per point: z, lcl, ucl, signal.
   - Known answers: I-MR on [10, 12, 11, 13, 12] gives center 11.6, MR̄ 1.5, σ̂ 1.3298, UCL 15.589, LCL 7.611, MR UCL 4.901. EWMA (μ₀ = 10, σ = 1) on [11, 12] gives z 10.2, 10.56 and half-widths 0.600, 0.7684.
   - Data tests: `problem_fleet` D-07 EWMA on temp_rise_c first signals at flight 74; I chart on D-03 vibration flags flight 80 only.
   - Degenerate: constant data (MR̄ = 0) raises ValueError; fewer than 20 baseline points raises; NaN is refused.
2. **H-03b: fleet status** (~30 min, same files). `fleet_status(flights, components, b10)`: **ground** = the latest flight is beyond an I limit, or the EWMA is beyond its limit now; **watch** = any signal in the last 10 flights; **go** = otherwise. (Parts past B10 are a separate list; see Decisions.) Each row has a one-line reason. Test: D-07 = ground at flight 95 in `problem_fleet`.
3. **H-04: Shiny for Python app** (Stage 3, ~2 h). Files: `app/` except qc.py. Tabs: Fleet, Drone, Reliability (Reliability can be empty until step 5). The app only calls `qc.py`. Test: `testme.sh` starts it, and the numbers on one dataset match the H-03 tests.
4. **H-06: deploy** (Stage 3, ~1 h). Files: `.github/workflows/`, `.github/scripts/`, `app/manifest.json`, `app/.python-version`. Load the `connect-publish` skill. Test: the public URL answers HTTP 200 logged out.
5. **H-03c: Weibull** (Stage 4, ~2 h, same files as H-03). `weibull_fit(life, status)`: 2-parameter Weibull, maximum likelihood with right-censoring (`lifelines.WeibullFitter`; status 0 = censored). Returns β (shape), η (scale), 95% CIs, and B10 = η(-ln 0.9)^(1/β). `compare_lots(...)` = one fit per battery lot.
   - Known answer: B10 with η 100, β 2 = 32.459. A fit on 2,000 simulated lives (β 2.5, η 300, 30% censored) recovers β ± 0.15 and η ± 5%.
   - Data test: `problem_fleet` lot B η ≈ 244 cycles, below lot A (≈ 358).
   - Degenerate: all censored, or fewer than 3 failures, raises ValueError.
6. **H-05: demo** (Stage 6, ~1 h). `demo/README.md`, one walk-through per dataset with the exact numbers shown.
7. **H-07: README and function docs** (Stage 6, ~1.5 h). Every function: inputs, parameters, outputs, the formula.
8. **H-08: reproducible and submitted** (Stage 7, ~30 min). Fresh clone, tests pass, Devpost + Canvas.

## Decisions

- **Redesign: one active fleet with a replacement loop (Div, 2026-10-16, task H-10).** Supersedes the "Two datasets" and "Run rules: rule 1 only" decisions below, and removes crashes.
  - The healthy fleet is removed everywhere. The scripted faults (D-07 ramp and crash, D-03 strike, lot B ×0.6, magic-decimal life scales) are removed.
  - 10 drones × 300 flights (~90 days). Every part wears: in the last stretch of its own Weibull life (its P-F interval) its reading drifts up (motor → temperature rise, propeller → vibration, battery → voltage sag).
  - Special causes are random (seeded): one physical cause per Nelson / Western Electric rule shape, 1 = prop strike, 2 = hard landing (motor), 3 = wear trend, 4 = one bad battery of the alternating pair, 5 = loose power connector, 6 = prop imbalance, 7 = vibration log over-filtered after a firmware update (readings too flat), 8 = loose motor mount (vibration rattles in one of two modes). All 8 rules run on the I charts; rules 2-8 are not applied to the EWMA (its points are autocorrelated). Expected cost: more false alarms than rule 1 alone, shown and explained, not tuned away.
  - Warning (W) = whichever comes first: the part is within 10 flights of its B10 replace-at age, or a chart signals (EWMA or any rule) and inspection finds that part worn. The technician then replaces (R) or repairs; a part that fails before that is an F and is replaced at once. No drone stops flying.
  - After every repair or replacement the EWMA restarts at the center line and the run rules start counting afresh. Control limits are kept: a new part returns the drone to its baseline process.
  - Timeline display: one row per part slot, flight number on the X axis, markers W / R / F / S (H-04 rework).
  - **Simplified after review (Div, 2026-10-16, H-11):** a warning means replace before the next flight. The age warning fires at B10 (no 10-flight lead) and a chart-found worn part is replaced at once. The timeline shows only R (warned → replaced), F and S. False alarms are not events: the chart marks and restarts, `maintenance.csv` logs `no_fault`. The dashboard schedules with the shop's replace-at ages (`replace_at.csv`, fitted before the log) and shows the refit on all data beside them. Control charts default to the last 100 flights. Supersedes the 10-flight warning lead and the W / N markers above.
  - Baseline = the first 50 flights per drone (Div, 2026-10-16, H-03 rework; supersedes 30). With 30, the baseline sigma ranged 0.6x to 1.4x the true value and false alarms were 2.8% of chart points; with 50 they are 2.3%. Phase I cleaning (dropping baseline points outside first-pass limits) was tried and barely helped, so it is not used. Special causes start after flight 60.
  - The tool reads its resets from `maintenance.csv` (`chart` column): any logged replacement, repair or inspection on a chart restarts it. Run on the CSVs it signals on exactly the flights the simulated technician acted on (all 30 drone charts, tested).

- Chance warnings are kept, not tuned away (2026-10-16): the healthy fleet shows 2 Warnings (D-06 cool baseline, D-07 one sag reading). Longer baselines (40, 50) only move the false alarms to other drones. Warning cards say "often just chance: inspect at the next check" and the healthy fleet explains the expected rate.

- Two datasets, not three (2026-10-16): `problem_fleet` holds every planted problem (D-07 wear and crash, D-03 prop strike, lot B batteries) and `healthy` is the comparison, because a single-problem fleet changed only one view and switching looked random. Statuses read Can fly / Warning / Do not fly in the app.

- Parts past B10 are listed on the Part reliability tab, not folded into watch (2026-10-16): 51 parts are past B10 in this run-to-failure fleet, which would put nearly every drone on watch.
- Health bar = room left before the nearest control limit on the drone's most-stretched chart (qc.chart_margin), 0 after a crash (2026-10-16).

- Baseline = the first 30 flights per drone (team, 2026-10-16). D-06's healthy-fleet false alarm is kept and explained in the demo as the cost of a short baseline.
- Data: one folder per dataset, two tables each (team, 2026-10-16).
- Stack: Shiny for Python (team). Statistics only in `app/qc.py`; functions take pandas/numpy, return dicts or DataFrames, never plots.
- Run rules: rule 1 only (a point beyond 3σ). EWMA λ = 0.2, L = 3.
- No machine learning, no Cp/Cpk, p-chart only if time is left (SPEC section 9).

## Risks

1. **Wrong limits that look right.** Every statistic is tested against the hand-worked numbers above before any UI work.
2. **The deploy breaks late.** Deploy in Stage 3 while the app is still ugly; get the publisher key early.
3. **Teammates collide.** One task per person, claimed in `CONTRACT.yaml` and pushed before starting; `git pull --rebase` before every push.
