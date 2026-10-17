# How the Drone Fleet Health & Part Wear Monitor works

A plain-language walk through the whole tool, in the order things happen. No statistics background is
needed; every term is explained the first time it appears, and there is a glossary at the end.

**Contents**

1. [What the tool is for](#1-what-the-tool-is-for)
2. [The big picture in one diagram](#2-the-big-picture-in-one-diagram)
3. [The data: where it comes from](#3-the-data-where-it-comes-from)
4. [Before the first flight: two things the tool needs ready](#4-before-the-first-flight-two-things-the-tool-needs-ready)
5. [Every flight: what the technician logs](#5-every-flight-what-the-technician-logs)
6. [After every landing: the checks](#6-after-every-landing-the-checks)
7. [When a check fires: what the technician does](#7-when-a-check-fires-what-the-technician-does)
8. [Can a part still fail in flight?](#8-can-a-part-still-fail-in-flight)
9. [What the website shows, page by page](#9-what-the-website-shows-page-by-page)
10. [A worked example: drone D-05 from flight 1 to 300](#10-a-worked-example-drone-d-05-from-flight-1-to-300)
11. [The whole run in numbers](#11-the-whole-run-in-numbers)
12. [Honest limits](#12-honest-limits)
13. [Where each piece lives in the code](#13-where-each-piece-lives-in-the-code)
14. [Glossary](#14-glossary)

---

## 1. What the tool is for

A drone delivery startup flies a fleet of **10 drones** (`D-01` to `D-10`). Each drone has
**4 motors, 4 propellers and 2 batteries** (the batteries take turns, one per flight). Parts wear out.
If a part wears out in the air, the drone can fall.

The tool is for the **fleet maintenance technician**. Before every take-off it answers two questions:

1. **Is this drone healthy enough to fly?** (*Can fly / Warning / Do not fly*)
2. **Does any part need replacing now?** And which parts are coming up soon, so they are in stock.

The rule it works by is simple: **a warning means "replace the part before the next flight"**. The
drone is never grounded for long and never stops flying: the part is swapped and off it goes.

It does this with two standard quality-control methods:

- **Control charts** watch the readings from every flight and spot when something has changed
  (a part wearing out, a strike, a loose connector).
- **Weibull reliability** works out from the parts history how long each part type usually lasts, and
  sets a **replace-at age** for each.

---

## 2. The big picture in one diagram

```
 BEFORE THE LOG STARTS                     EVERY FLIGHT (flights 1 to 300, each drone)
 ---------------------                     ---------------------------------------------
 Parts history (run until failure)          Technician logs 1 minute of readings
        |                                          |
        v                                          v
 Weibull fit -> replace-at age per part     Tool computes: temperature rise, voltage sag/min
 (replace_at.csv)                                  |
                                                   v
 Acceptance flights (all-new parts)         CHECKS after landing
        |                                     - flights 1-50: compare with the fleet range
        v                                     - flight 50:    the drone's own limits are set
 Fleet normal range                           - flights 51+:  control charts (8 rules + EWMA)
 (fleet_reference.csv)                        - every flight: is any part at its replace-at age?
                                                   |
                                      +------------+-------------+
                                      |                          |
                                 nothing fired              something fired
                                      |                          |
                                  Can fly              find the cause, before the next flight:
                                                        - worn part        -> replace it   (R)
                                                        - special cause    -> fix it       (S)
                                                        - nothing wrong    -> false alarm, carry on
                                                        then the chart restarts
```

---

## 3. The data: where it comes from

We do not have a real startup's records, so the data is **invented** by a simulation,
[`data/simulate.py`](../data/simulate.py). It is built to behave like a real fleet, and because we made it,
we know every problem in it, so we can check the tool finds each one (like testing a smoke alarm with real
smoke). Running `python data/simulate.py` always produces exactly the same files (fixed random seed 5300).

**What is simulated:** 10 drones × 300 flights = **3,000 flights**, from **1 July to 29 September 2026**
(about 3.3 flights a day per drone).

Inside the simulation, three things happen:

1. **Every part has a hidden lifetime.** When a part is installed it gets a random lifetime from its
   type's life distribution (a Weibull distribution, see the glossary). Nobody can see this number, not
   the technician and not the tool. If a part's use ever passes its lifetime, it fails.
2. **Parts show wear before they fail.** In the last stretch of its life (its **P-F interval**, the
   time between "wear becomes visible" and "failure"), each part pushes one reading upward a little more
   every flight:

   | Part | Reading it pushes up | How long before failure the wear shows |
   |---|---|---|
   | Motor | Motor temperature rise | about 68 flights |
   | Propeller | Vibration | about 22 flights |
   | Battery | Voltage drop per minute | about 60 flights |

3. **Random problems strike** (called *special causes*): 17 of them, at random drones and flights, for
   example a propeller strike, a hard landing that bends a motor shaft, a bad battery cell, a loose power
   connector. Nothing is scripted on a named drone.

A simulated technician then uses the tool after every flight and acts on what it says, exactly as a
real one would (sections 6 and 7). Everything they do is written down.

**The files** (in [`data/fleet/`](../data/fleet/); full column list in [`data/README.md`](../data/README.md)):

| File | One row per | What it is for |
|---|---|---|
| `flights.csv` | flight (3,000) | The readings the technician logs. The control charts read this |
| `components.csv` | part life (431) | Each part from install to removal, failure, or today. The Weibull fit reads this |
| `maintenance.csv` | technician action (255) | Every replacement, repair and false alarm. Tells the charts when to restart |
| `replace_at.csv` | part type (3) | The shop's replace-at ages |
| `fleet_reference.csv` | reading (3) | The fleet's normal range, used for each drone's first 50 flights |
| `answer_key.csv` | injected problem (17) | **The tool never reads this.** The tests use it to check every problem was caught |

---

## 4. Before the first flight: two things the tool needs ready

### 4a. The replace-at age for each part type

Before July the startup flew every part until it broke. That history is a record of how long parts
actually last. The tool fits a **Weibull life model** to it (the standard model for how long parts last)
and reads off **B10**: the age by which 10% of parts of that type have failed. That is the
**replace-at age**: replace a part when it reaches B10, while 90% of parts its age are still fine.

| Part | Replace at (B10) | In drone flights, roughly |
|---|---|---|
| Motor | 240.3 flight hours | ~655 flights |
| Propeller | 47.9 flight hours | ~130 flights |
| Battery | 197.2 charge cycles | ~394 flights (each battery flies every second flight) |

Saved in `replace_at.csv`. Any part already past its B10 on 1 July is replaced before the log starts.

**B10 is the default, not fixed.** The dashboard's slider retires parts at B1 to B30 instead (the age by which
1% to 30% fail). Each setting is the same fleet simulated again under that rule, so every view updates.
Retiring earlier uses more parts; retiring later lets more parts reach visible wear before the charts catch
them. In every setting no part failed in flight. All numbers in this guide are for B10.

### 4b. The fleet's normal range

A drone's own control chart needs its first **50 flights** to learn what is normal *for that drone*
(section 6b). To avoid a blind spot during those 50 flights, the tool also keeps a **fleet normal range**:
the average and spread of each reading over **200 acceptance flights** (20 per drone, flown with all-new
parts when the drone joined the fleet).

| Reading | Fleet average | Fleet spread (standard deviation) |
|---|---|---|
| Motor temperature rise | 18.28 °C | 1.61 °C |
| Vibration | 3.07 m/s² | 0.30 m/s² |
| Voltage drop per minute | 0.170 V/min | 0.015 V/min |

Saved in `fleet_reference.csv`.

---

## 5. Every flight: what the technician logs

About a minute per flight, at three moments:

| When | What | Column |
|---|---|---|
| Before take-off | Battery voltage | `voltage_start_v` |
| | Air temperature at the pad | `ambient_temp_c` |
| During the flight (from the flight controller's log) | How long it flew | `flight_min` |
| | How much it shook | `vibration_rms` |
| | Any alert (a part failed in the air) | `inflight_event` |
| Right after landing | Temperature of the hottest motor (infrared thermometer) | `motor_temp_max_c` |
| | Battery voltage | `voltage_end_v` |

The tool then works out two readings, so weather and flight length don't fool it:

- **Temperature rise** = hottest motor − air temperature. A hot day makes every motor hot; the *rise*
  only goes up when a motor is working harder.
- **Voltage drop per minute** = (voltage at take-off − voltage at landing) ÷ minutes flown, so a long
  flight is comparable with a short one.

So each flight gives **three readings** to watch: temperature rise (motors), vibration (propellers) and
voltage drop per minute (batteries).

---

## 6. After every landing: the checks

The checks run right after each landing, so any warning comes **before the next take-off**.

### 6a. Flights 1 to 50: compared with the fleet

Each reading is compared with the fleet normal range. If it is more than **3 standard deviations** from
the fleet average (outside the range a healthy drone lands in 99.7% of the time), it signals.

Only this one test is used here, because drones differ a little from each other and the fleet range
includes those differences; stricter pattern tests would flag drones that are simply a bit different.

### 6b. Flight 50: the drone's own normal range is set

After 50 flights the tool knows the drone's own normal behaviour. For each reading it computes:

- the **center line** = the average of the 50 readings;
- the **spread**, sigma = the average jump between consecutive readings ÷ 1.128 (a standard formula that
  works on one reading per flight);
- the **control limits** = center ± 3 × sigma.

These limits **never change afterwards**. They are the yardstick for every later flight.

### 6c. Flights 51 onward: the control charts

Each reading is checked two ways:

1. **The I chart and the 8 rules.** Every reading is plotted on its own and tested with the
   8 standard Nelson / Western Electric rules. Rule 1 is "one reading beyond the limits"; rules 2–8 catch
   patterns that are unlikely by chance, each typical of a different problem:

   | Rule | Pattern | A drone problem that makes it |
   |---|---|---|
   | 1 | 1 point beyond 3 sigma | a propeller strike |
   | 2 | 9 in a row on the same side of the center | a hard landing that bends a motor shaft |
   | 3 | 6 in a row steadily rising or falling | a part wearing out |
   | 4 | 14 in a row alternating up and down | one bad battery of the alternating pair |
   | 5 | 2 of 3 beyond 2 sigma on one side | a loose power connector |
   | 6 | 4 of 5 beyond 1 sigma on one side | a slightly unbalanced propeller |
   | 7 | 15 in a row within 1 sigma | a vibration log smoothed by a firmware setting (too flat) |
   | 8 | 8 in a row beyond 1 sigma, both sides | a loose motor mount rattling in two modes |

2. **The EWMA** (exponentially weighted moving average): a running average that weights recent flights
   most (each new reading counts 20%). It smooths out the noise, so a slow drift, like a part wearing,
   shows up before any single reading looks odd. It has its own, narrower limits.

### 6d. Every flight: the age check

Each installed part's age (flight hours, or charge cycles for batteries) is compared with its replace-at
age. A part that reaches it is warned.

---

## 7. When a check fires: what the technician does

Every warning is handled **before the next flight**. There are three possible outcomes:

| What fired | What the technician finds | What they do | Marker on the timeline |
|---|---|---|---|
| A part reached its replace-at age | — | Replace the part | **R** |
| A chart signal | A part showing wear (inside its P-F interval) | Replace the part | **R** |
| A chart signal | A special cause (strike, hard landing, bad cell, loose connector or mount, firmware setting) | Fix it: replace the damaged part, or repair | **S** |
| A chart signal | Nothing wrong | Nothing: it was a **false alarm** | not shown |

**False alarms are normal.** A healthy drone still produces an unusual reading now and then by pure
chance; using all 8 rules catches more real problems, at the price of more of these. In this run about
**1.9%** of readings after the baselines were false alarms. They stay visible as dots on the control charts
but need no action, so they are kept off the timeline.

**After every action, that chart restarts.** The EWMA goes back to the center line and the rules start
counting from zero, so readings from a part that has been removed can't keep raising alarms. The control
limits stay the same: a new part puts the drone back to its normal.

---

## 8. Can a part still fail in flight?

Only if every check misses it: the part dies **younger than its replace-at age** *and* its wear never
showed clearly enough on a chart before it failed. If it happens, the drone gets home, the part is
replaced before the next flight, and the timeline shows **F**.

**In this run no part failed in flight.** Before the fleet check (section 6a) existed, two propellers did,
both during a drone's first 50 flights, while its own chart was not yet watching. The fleet check now
catches that kind of wear.

It is still possible in principle: a part that breaks with no wear first (a sudden fault) gives no
warning. The tool turns failures into warnings; it cannot promise there will never be one.

---

## 9. What the website shows, page by page

Start it locally with `./run.sh` from the repo folder and open
<http://127.0.0.1:8000>.

### The dashboard opens on the **Fleet health & replacements** tab

1. **Summary line.** How many drones *can fly*, have a *warning*, or should *not fly*; how many parts are
   due within 10 flights; and what happened over the 300 flights (parts warned and replaced, failures,
   special causes fixed).
2. **Due soon.** As of each drone's latest flight, the parts that reach their replace-at age within the
   next 10 flights ("have the part ready") or 30 flights ("coming up"). Each will be warned when it gets
   there and replaced before the next flight; this list is the heads-up so the part is in stock.
3. **Drone cards**, one per drone:
   - **Status:**
     - *Can fly*: no signal waiting to be dealt with.
     - *Warning*: a signal nobody has acted on yet.
     - *Do not fly*: the latest flight was beyond the limits, or the EWMA is beyond its limit right now;
       inspect before flying.
   - **Parts health** (0–100%): the average share of replace-at life its 10 parts have left (100% = all new, 0% = all due).
   - **Next part due**, and how many flights until it.
   - Click a card to open that drone's details.
4. **Fleet maintenance timeline.** Every drone on one row, flight number across.
   **R** (blue) = warned and replaced, **F** (red ✕) = failed in flight, **S** (violet) = special cause
   fixed. Read it as the fleet's maintenance history at a glance.

### Clicking a drone opens its details

1. **Status banner**: the status, the health bar and the reason in words.
2. **Maintenance timeline** for this drone: one row per part slot (motor 1–4, propeller 1–4,
   battery 1–2, plus "repairs"), flight number across, a letter over each event.
3. **Installed parts**: each part's age against its replace-at age, the share of its life used, and how
   many flights it has left.
4. **Control charts**, one per reading, showing the latest 100 flights (switch on *Show all flights* for
   all 300):
   - light blue line = each flight's reading;
   - orange line = the EWMA;
   - dashed lines = the drone's control limits;
   - grey dash-dot lines over the first 50 flights = the fleet range;
   - red ✕ = rule 1 (or outside the fleet range);
   - amber ◆ = one of rules 2–8;
   - orange ring = the EWMA beyond its limit;
   - thin vertical lines = the technician acted there and the chart restarted.

   A table above the charts gives each reading's center, limits, latest value, and how often it signalled.

### The **Weibull reliability & replace-at ages** tab

- **One card per part type**: the replace-at age the schedule uses (fitted before the log), and next to it
  the same fit redone on all the data so far. As failures pile up, this estimate can move.
- **Reliability curves**: for each part type, the fitted Weibull curve (the share of parts still working
  at each age) laid over a Kaplan-Meier curve (the same thing read straight from the data with no model).
  If they agree, the model fits. A red line marks B10.
- **The fitted numbers** with 95% confidence intervals: shape β (above 1 means parts wear out, so
  replacing them early pays off), scale η, B10, and mean life.
- **Replacement schedule**: every drone's 10 parts with flights left, folded per drone.

### The **Guide & Data Reference** page (button at the top right)

A short welcome page: what the tool does, the test fleet and the 17 problems that were put into it, the
data files with example rows, and key terms.

---

## 10. A worked example: drone D-05 from flight 1 to 300

Following one drone through the whole log, using the real numbers in the data.

| When | What happened | Why | Marker |
|---|---|---|---|
| Flight 1 (1 July) | First logged flight: temperature rise 20.8 °C, vibration 3.06 m/s², voltage drop 0.188 V/min | — | |
| Flights 5–17 | Propeller 3 starts to wear; with the usual ups and downs, vibration climbs from about 3.1 to 4.25 m/s² | its hidden lifetime is close | |
| **After flight 17** | Vibration is beyond the fleet range (3.07 + 3 × 0.30 = 3.97 m/s²). Propeller 3 is replaced before flight 18 | fleet check, rule 1 | **R** |
| | Without the fleet check, this propeller would have failed in flight 25 | | |
| After flight 50 | D-05's own limits are set. Vibration: center 3.09, limits 2.23 to 3.94 m/s² | 50-flight baseline | |
| After flight 136 | Propellers 1, 2 and 4 reach their replace-at age (47.9 h) and are replaced | age check | **R** ×3 |
| After flight 141 | A propeller strike: vibration jumps beyond the upper limit. Propeller 4 is replaced | rule 1 | **S** |
| After flight 151 | Battery 1 reaches its replace-at age (197.2 cycles) and is replaced | age check | **R** |
| After flight 153 | Propeller 3 reaches its replace-at age and is replaced | age check | **R** |
| Flights 194–197 | A loose power connector makes the voltage drop jump on some flights; after flight 197 it is caught and repaired | rule 1 | **S** |
| After flight 220 | The vibration EWMA crosses its limit: propeller 1 is wearing out early. Replaced | EWMA | **R** |
| After flight 258 | A bad cell in battery 2: voltage drop spikes on that battery's flights. Battery 2 replaced | rule 1 and EWMA | **S** |
| After flights 269, 274, 285 | Propellers 2, 4 and 3 reach their replace-at age and are replaced | age check | **R** ×3 |
| Throughout | 29 chart signals with nothing wrong (false alarms), mostly on temperature, where D-05's limits happen to be a little tight | chance | not shown |
| Flight 300 | D-05 *can fly*; its next part due is motor 1, about 46 flights away | | |

Every problem was caught within a few flights, every part was replaced on the ground, and D-05 never
stopped flying.

---

## 11. The whole run in numbers

| What | Count |
|---|---|
| Flights | 3,000 (10 drones × 300) |
| Parts warned and replaced (R) | 99: 84 at their replace-at age, 15 found wearing by a chart (3 of them by the fleet check in the first 50 flights) |
| Special causes injected / caught and fixed (S) | 17 / 17, caught a median of 1 flight after they started (at most 12) |
| Parts failed in flight (F) | 0 |
| False alarms (no action needed) | 139, about 1.9% of readings after the baselines |
| Drones that stopped flying | 0 |
| Status at the end | all 10 *can fly*; 3 parts due within 10 flights |

**How we know the numbers are right:** 84 automated tests (`python -m pytest tests -q`). They check every
formula against answers worked by hand, check that silly input (constant data, a single reading) is
refused, check the Weibull fit recovers the true part lives, and check that, given only the CSV files, the
tool signals on exactly the flights where the simulated technician acted, for all 30 drone-reading charts.

---

## 12. Honest limits

- **The data is simulated.** It is realistic in shape, but no real fleet was measured.
- **False alarms come with using all 8 rules**: about 2% of readings. The tool shows them but asks for no
  action. Fewer rules would mean fewer false alarms and fewer problems caught.
- **50 flights is a short baseline.** By chance some drones get limits that are a little tight (D-05's
  temperature) or a little loose. We kept that rather than re-picking the random seed.
- **The fleet check uses rule 1 only.** It catches strong wear in a drone's first 50 flights, not subtle
  patterns.
- **The replace-at age is an estimate.** Fitted on the history before the log (about 15 motor failures),
  the motor B10 is 240 h; refitted on all the data it is 215 h, closer to the true 203 h. The schedule
  keeps the first number; the Weibull tab shows both.
- **No warning for a part that breaks without wearing first.** The tool can only warn from evidence.

---

## 13. Where each piece lives in the code

| File | What it does |
|---|---|
| [`data/simulate.py`](../data/simulate.py) | Makes the test fleet: part lifetimes, wear, special causes, and the simulated technician |
| [`app/qc.py`](../app/qc.py) | **All the statistics**, as plain tested functions. `imr_limits` (limits), `spc_rules` (the 8 rules), `ewma_chart`, `monitor_chart` (everything for one reading of one drone, with the fleet check and the restarts), `fleet_status` (Can fly / Warning / Do not fly), `weibull_fit` and `fit_by_type` (part lives, B10), `km_curve` (Kaplan-Meier), `replacement_plan` (flights left per part), `maintenance_timeline` (R / F / S markers) |
| [`app/api.py`](../app/api.py) | The REST API (FastAPI): loads the files, calls `qc.py`, returns the results as JSON under `/api/` (docs at `/docs`) and serves the website. No statistics of its own |
| [`web/src/`](../web/src/) | The website (React): the dashboard, the drone pop-up, the Weibull tab and the guide page; charts and timelines drawn as SVG from what the API returns |
| [`tests/`](../tests/) | The 84 tests |

---

## 14. Glossary

| Term | Meaning |
|---|---|
| **Baseline** | A drone's first 50 flights. They set its own normal range |
| **Control limits** | Center ± 3 sigma. A healthy drone stays inside them about 99.7% of the time |
| **Sigma (σ)** | The typical flight-to-flight spread of a reading |
| **Common cause** | Ordinary flight-to-flight noise. Not a problem |
| **Special cause** | Something that changed: a worn part, a strike, a loose connector. What the charts look for |
| **I chart** | A chart of every individual reading against its limits |
| **The 8 rules** | Nelson / Western Electric tests for readings that are unlikely by chance (section 6c) |
| **EWMA** | A running average weighted toward recent flights; catches slow drifts early |
| **Fleet check** | During a drone's first 50 flights: a reading more than 3 sigma from the fleet average signals |
| **False alarm** | A signal with nothing wrong; expected now and then, needs no action |
| **Restart** | After an action, a chart's EWMA and rule counting start again (limits stay) |
| **Weibull distribution** | The standard model of how long parts last. Shape β above 1 means parts wear out with age |
| **B10** | The age by which 10% of parts have failed. Used as the replace-at age |
| **Censored** | A part that has not failed (still flying, or removed early). Counted as "lasted at least this long" |
| **Kaplan-Meier curve** | The share of parts still working at each age, read straight from the data |
| **P-F interval** | The stretch between "wear becomes visible" (P) and "failure" (F) |
| **R / F / S** | Timeline markers: warned and replaced / failed in flight / special cause fixed |
