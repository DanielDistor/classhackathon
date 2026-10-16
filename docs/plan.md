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
