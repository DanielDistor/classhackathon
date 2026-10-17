# Demo: the tool on both test fleets

Every number below is what the dashboard shows at its default setting (**retire parts at B10**). A teammate who
follows these steps should see the same numbers. Each step also gives the API URL that returns the same
numbers as JSON, so they can be checked without the dashboard.

**Start:** from the repo folder run `./run.sh`, then open <http://127.0.0.1:8000>. The welcome page states the
problem. Click **Open the dashboard**. The **Test dataset** dropdown at the top switches between Fleet A and
Fleet B.

---

## Fleet A (`data/fleet/`, the main demo)

10 drones × 300 flights. 17 problems planted at random (`data/fleet/answer_key.csv`).

### 1. Fleet health & replacements tab

| What you see | Value | How to read it |
|---|---|---|
| Status counts | **10 can fly, 0 warning, 0 do not fly** | Every signal so far has been acted on, so no drone has an open warning today |
| Parts due within 10 flights | **3** | The parts to have in stock now |
| Due soon (open the panel) | D-09 propeller 3 in **2** flights, D-06 propeller 2 in **4**, D-08 propeller 2 in **5** | Each is replaced when it reaches its replace-at age, before the next flight |
| History line | **99** parts replaced (**84** at their replace-at age, **15** caught worn by a chart), **0** failed in flight, **17** special causes fixed | The charts caught every worn part and every planted problem before a failure |
| Lowest parts health | D-02 at **40%** | Its parts have used 60% of their replace-at life on average |

API: <http://127.0.0.1:8000/api/fleet?dataset=fleet>

### 2. One drone: D-03, a prop strike

Click the **D-03** card and pick **Vibration** in the chart dropdown.

| What you see | Value | How to read it |
|---|---|---|
| Vibration normal range | center **3.34** m/s², limits **2.60 to 4.09** | From D-03's first 50 flights |
| Flight 76 | reading **5.12** m/s², beyond the upper limit; EWMA **3.74**, also beyond its limit | A red ✕ (rule 1) and an EWMA ring: one sudden jump, the shape of a prop strike |
| Answer key | "D-03 prop strike, starts flight 76, caught after flight 76 by EWMA; rule 1" | The tool flagged it on the same flight the problem started |
| Thin line after flight 76 | the propeller was replaced | The chart restarts there, so the old strike stops raising alarms |
| Banner | Parts health **44%**, most worn: motor 4 (**3%** left) | Motor 4 is next to be replaced |

API: <http://127.0.0.1:8000/api/drones/D-03?dataset=fleet>

### 3. Weibull reliability & replace-at ages tab

| Part | Sample | Shape β (95% CI) | Scale η (95% CI) | B10 refit | Replace at (shop schedule) |
|---|---|---|---|---|---|
| Motor | 18 failed / 94 | 2.62 (1.66–3.58) | 508 (392–623) h | 215 h | 240 h |
| Propeller | 110 failed / 266 | 1.91 (1.66–2.15) | 154 (139–169) h | 47 h | 48 h |
| Battery | 24 failed / 71 | 3.57 (2.64–4.50) | 356 (317–396) cycles | 190 cycles | 197 cycles |

**How to read it:** β > 1 for every part type, so the failure risk rises with age (wear-out). That is what makes
replacing at a fixed age worthwhile. The simulator's true values are β = 2.5 / 1.8 / 3.0 and η = 500 h / 150 h /
400 cycles. Every true value falls inside its 95% interval except battery η (true 400, interval 317–396), which
sits just above it. The Kaplan-Meier steps follow the Weibull
curve, which checks the fit.

API: <http://127.0.0.1:8000/api/reliability?dataset=fleet>

### 4. The retirement slider

Move the slider and watch the history line. Retiring parts earlier uses more parts. Retiring later lets more of
them reach visible wear, but the charts still catch them:

| Retire at | B1 | B2 | B5 | **B10** | B15 | B20 | B30 |
|---|---|---|---|---|---|---|---|
| Parts replaced | 312 | 236 | 140 | **99** | 81 | 74 | 65 |
| of which caught worn by a chart | 9 | 7 | 10 | **15** | 18 | 21 | 23 |
| Failed in flight | 0 | 0 | 0 | **0** | 0 | 0 | 0 |

API: <http://127.0.0.1:8000/api/runs?dataset=fleet>

### 5. Cost & savings tab

| What you see | Value | How to read it |
|---|---|---|
| No charts: cheapest choice | replace at 1.5% → **$26.26** per drone-flight | From the age-replacement model. With no warnings, the cheapest plan is to replace parts very early |
| With charts: replace at 10% (slider) | **$4.08** per drone-flight | From the simulated run. Planned replacements only, since nothing failed in flight |
| The charts save | **$66,528** over these 3,000 flights (**$22.18** each) | The value of warning before a failure |

The prices are estimates ($350 / $80 / $380 for a planned motor / propeller / battery, $8,000 for a failure in
flight) and can be changed on the tab.

API: <http://127.0.0.1:8000/api/cost?dataset=fleet>

---

## Fleet B (`data/fleet_b/`, the second check)

Same simulator, different seed (7100): new part lives, new problems, new timing. Pick **Fleet B** in the
dropdown. 11 problems planted (`data/fleet_b/answer_key.csv`).

| Step | What you see | Value |
|---|---|---|
| 1. Status | counts | **10 can fly, 0 warning, 0 do not fly**, **0** parts due within 10 flights |
| 1. Next due | Due soon panel | D-05 motor 4 in **30** flights, D-08 propeller 3 in **30**, D-09 propeller 3 in **33** |
| 1. History | history line | **119** replaced (**104** at age, **15** caught worn), **0** failed in flight, **11** special causes fixed |
| 2. One drone | D-09, Vibration, flight 111 | reading **4.58** m/s² against limits **2.25 to 3.82**, EWMA **3.35**: rule 1 + EWMA. Answer key: prop strike starting flight 111, caught after flight 111 |
| 3. Weibull | motor / propeller / battery | β 2.62 / 1.74 / 2.67, η 514 h / 152 h / 425 cycles, B10 218 h / 42 h / 183 cycles |
| 4. Slider | B1 → B30 | 437 → 62 parts replaced, 10 → 28 caught worn, 0 failed in flight at every setting |
| 5. Cost | at B10 | **$5.46** per flight with the charts vs **$31.72** for the cheapest choice without them (replace at 1.5%): the charts save **$78,769** over 3,000 flights |

**How to read it:** a second fleet with different problems gives the same result. Every planted problem is
caught, and no part fails in flight, so the method works beyond the one dataset it was built on.

---

## The checks behind these numbers

```bash
python3 -m pytest -q
```

- `tests/test_simulate.py::test_every_special_cause_is_detected_and_fixed`: every answer-key problem is signalled.
- `tests/test_monitor.py::test_tool_signals_on_exactly_the_flights_the_technician_acted_on`: on all 30 drone
  charts, the tool signals on exactly the flights where the technician acted.
- `tests/test_qc.py`, `tests/test_reliability.py`: known answers for the control limits, the EWMA and the Weibull
  fit, plus degenerate inputs (constant data, too few points, no failures) that must be refused.
- `tests/test_api.py`: every API route returns exactly what `app/qc.py` computes, for both fleets.
