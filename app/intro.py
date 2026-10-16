"""The welcome page: what the tool does, what the data is, the test datasets, key terms, the tabs.

Plain content only (no statistics). Edit the wording here freely; app.py
shows this page first and swaps to the dashboard when "Continue" is clicked.
The example rows are read from the bundled data files, so they always match.
"""

from __future__ import annotations

from html import escape
from pathlib import Path

import pandas as pd
from shiny import ui

DATA = Path(__file__).resolve().parent / "data"

FACTS = [
    ("10", "delivery drones, named D-01 to D-10"),
    ("30 days", "of flying: September 1–30, 2026"),
    ("~100", "flights per drone, about 3 a day"),
    ("~1,000", "flight records in each dataset"),
    ("~300", "part records (motors, props, batteries)"),
]

# (number, part, what it is, what the technician writes down, column names)
PARTS = [
    ("1", "Propellers ×4", "The spinning blades that lift the drone.",
     "When a propeller is replaced, and why (chipped, cracked, hit something).", "components.csv"),
    ("2", "Motors ×4", "Spin the propellers. A worn-out motor runs hotter.",
     "Right after landing: the temperature of the hottest motor, with an infrared thermometer. "
     "When a motor is replaced, and why.", "motor_temp_max_c, components.csv"),
    ("3", "Batteries ×2", "Power the drone. Each drone has two and swaps them between flights. "
     "Old batteries drain faster.",
     "Battery voltage at take-off and at landing (the battery displays it). When a battery is replaced, "
     "and how many charges it lasted.", "voltage_start_v, voltage_end_v, components.csv"),
    ("4", "Flight controller", "The drone's onboard computer. It keeps a log of every flight.",
     "From that log: how long the flight took, how much the drone shook, and any alert.",
     "flight_min, vibration_rms, inflight_event"),
    ("5", "Air thermometer (at the launch pad, not on the drone)",
     "Hot days make every motor hotter.",
     "The air temperature, so the tool can subtract it and not mistake a hot day for a worn motor.",
     "ambient_temp_c"),
]

# Every row of flights.csv covers one whole flight: before, during and after.
MOMENTS = [
    ("Before take-off", "Technician, at the launch pad", [
        ("Battery voltage at take-off", "voltage_start_v"),
        ("Air temperature", "ambient_temp_c"),
    ]),
    ("During the flight", "Recorded automatically by the drone's flight controller", [
        ("How long it flew", "flight_min"),
        ("How much it shook", "vibration_rms"),
        ("Any alert: warning, auto-return, crash", "inflight_event"),
    ]),
    ("Right after landing", "Technician, within a minute of landing", [
        ("Hottest motor temperature (infrared thermometer)", "motor_temp_max_c"),
        ("Battery voltage at landing", "voltage_end_v"),
    ]),
]


def moments_strip() -> ui.Tag:
    cards = []
    for i, (when, who, items) in enumerate(MOMENTS, 1):
        rows = "".join(f"<li>{escape(what)}<code>{escape(cols)}</code></li>" for what, cols in items)
        cards.append(ui.div(
            ui.div(ui.span(str(i), class_="step-num"), ui.h3(when), class_="moment-head"),
            ui.p(who, class_="moment-who"),
            ui.HTML(f'<ul class="moment-list">{rows}</ul>'),
            class_="info-card moment"))
    return ui.div(*cards, class_="grid-3 moments")


FLIGHT_COLS = [  # (column, friendly name)
    ("flight_id", "Flight"), ("drone_id", "Drone"), ("datetime", "Take-off time"),
    ("flight_min", "Minutes flown"), ("ambient_temp_c", "Air temp (°C)"),
    ("motor_temp_max_c", "Hottest motor (°C)"), ("voltage_start_v", "Battery at take-off (V)"),
    ("voltage_end_v", "Battery at landing (V)"), ("vibration_rms", "Vibration (m/s²)"),
]
PART_COLS = [
    ("component_id", "Part"), ("drone_id", "Drone"), ("component_type", "Type"), ("lot", "Batch"),
    ("install_date", "Installed"), ("end_date", "Removed"), ("life_value", "Used for"),
    ("status", "Failed?"), ("failure_mode", "What happened"),
]

SCENARIOS = [
    {
        "num": "1", "file": "problem_fleet", "name": "Fleet with problems (the main demo)",
        "what": "Three things go wrong, the kind this startup only finds after a crash today. "
                "(a) D-07: one motor (part 2) slowly wears out and runs a little hotter every flight, until it "
                "fails and the drone crashes on flight 95. (b) D-03: a propeller (part 1) hits something on "
                "flight 80. (c) Batteries (part 3) bought from supplier batch lot B are faulty and die after "
                "about 240 charges instead of about 400.",
        "expect": "D-07 is marked Do not fly, and the tool first warned at flight 74, 21 flights before the crash. "
                  "D-03's vibration jump on flight 80 is flagged. The Parts replacement view shows lot B "
                  "batteries dying early.",
        "timeline": [(60, "D-07's motor starts wearing out", "wear"),
                     (74, "the tool warns about D-07", "tool"),
                     (80, "D-03's propeller hits something", "wear"),
                     (95, "D-07 crashes", "bad")],
        "lots": [("Lot A", "bought before Oct 2025", 400), ("Lot B", "Oct 2025 – Mar 2026", 240),
                 ("Lot C", "Apr 2026 onward", 400)],
    },
    {
        "num": "2", "file": "healthy", "name": "Healthy fleet (for comparison)",
        "what": "The same 10 drones and the same flights, with nothing planted. Parts wear at their normal rate "
                "and every battery batch is fine.",
        "expect": "Almost every drone Can fly. A couple show a Warning from ordinary random variation, which "
                  "happens now and then. No drone is marked Do not fly.",
        "timeline": [],
        "lots": [("Lot A", "bought before Oct 2025", 400), ("Lot B", "Oct 2025 – Mar 2026", 400),
                 ("Lot C", "Apr 2026 onward", 400)],
    },
]

TERMS = [
    ("Baseline", "Each drone's first 30 logged flights. The drone is assumed healthy then, and "
                 "its own normal variation sets the limits for every later flight."),
    ("Control limits (UCL / LCL)", "The upper and lower lines on a chart: baseline mean ± 3 sigma. "
                                   "A healthy drone stays between them about 99.7% of the time."),
    ("Sigma (σ)", "The typical flight-to-flight spread, estimated from the average jump between "
                  "consecutive baseline readings ÷ 1.128."),
    ("Signal", "A point outside the control limits (a red ✕ on the charts). It means something "
               "has probably changed, so inspect the drone."),
    ("I chart", "Individuals chart: every reading plotted on its own. Best at catching sudden "
                "damage, like a prop strike."),
    ("EWMA", "Exponentially weighted moving average: a running average that weights recent "
             "flights most (λ = 0.2). Catches slow wear long before any single reading looks odd."),
    ("Temperature rise", "Hottest motor right after landing minus the air temperature (°C). "
                         "Subtracting the air temperature means a hot day isn't mistaken for wear."),
    ("Voltage sag", "Battery voltage at takeoff minus at landing, per flight minute (V/min). "
                    "It rises as a battery degrades."),
    ("Can fly / Warning / Do not fly", "Can fly: every chart in control. Warning: a warning sign in the last 10 "
                                       "flights, so fly but inspect soon. Do not fly: a reading is out of limits now, "
                                       "or the drone crashed."),
    ("Weibull life, B10, censored", "Coming in Stage 4. A Weibull model of how long parts last, "
                                    "B10 = the age by which 10% have failed, and censored = parts "
                                    "that haven't failed yet."),
]

TABS = [
    ("Fleet status", "All 10 drones at a glance, drawn green (can fly), amber (warning) or red (do not fly), "
                     "each with the reason. Start here each morning. Click a drone to open its "
                     "control charts (motor temperature, vibration, battery voltage) and the numbers behind them."),
    ("Parts replacement", "When to replace each kind of part (in flight hours, charges and flights), then all "
                          "10 drones' motors, propellers and batteries with how many days each has left or whether "
                          "it is overdue, plus the battery-batch check."),
]

STEPS = [
    ("1", "Log each flight", "A few readings a technician can take in a minute: the hottest motor's "
                             "temperature, battery voltage, and numbers from the flight log."),
    ("2", "Compare to the drone's own normal", "The tool learns each drone's normal from its first "
                                               "30 flights and checks every new flight against it."),
    ("3", "Act on it: can fly, warning, or do not fly", "Stop a drone before it fails in the air, instead of "
                                        "investigating after a crash."),
]


# ---------------------------------------------------------------- the drone picture

def _badge(x: int, y: int, n: str) -> str:
    return (f'<circle cx="{x}" cy="{y}" r="15" class="d-badge"/>'
            f'<text x="{x}" y="{y + 5}" text-anchor="middle" class="d-badge-num">{n}</text>')


def drone_diagram() -> str:
    """Top view of a quadcopter: big numbered badges, one short name per part."""
    cx, cy, rp = 380, 225, 64
    arms = [(268, 113), (492, 113), (492, 337), (268, 337)]
    g = []
    g += [f'<line x1="{cx}" y1="{cy}" x2="{x}" y2="{y}" class="d-arm"/>' for x, y in arms]
    for x, y in arms:
        g.append(f'<circle cx="{x}" cy="{y}" r="{rp}" class="d-prop"/>')
        g.append(f'<line x1="{x - 54}" y1="{y + 13}" x2="{x + 54}" y2="{y - 13}" class="d-blade"/>')
    for x, y in arms:
        g.append(f'<circle cx="{x}" cy="{y}" r="19" class="d-motor"/>')
    g.append('<rect x="318" y="178" width="124" height="94" rx="16" class="d-body-shape"/>')
    g.append('<rect x="334" y="189" width="92" height="32" rx="6" class="d-battery"/>')
    g.append('<text x="380" y="210" text-anchor="middle" class="d-inner">BATTERY</text>')
    g.append('<rect x="356" y="230" width="48" height="32" rx="5" class="d-fc"/>')
    g.append('<text x="380" y="251" text-anchor="middle" class="d-inner">FC</text>')
    g.append('<text x="380" y="34" text-anchor="middle" class="d-front">▲ FRONT</text>')
    # leader lines from each label to its part
    for pts in ("200,92 222,72", "200,350 250,343", "560,168 426,205", "560,282 404,250"):
        g.append(f'<polyline points="{pts}" class="d-leader"/>')
    # badge + name for each part (left column ends at x=200, right column starts at x=560)
    g.append(_badge(40, 92, "1") + '<text x="64" y="98" class="d-name">Propellers</text>')
    g.append(_badge(40, 350, "2") + '<text x="64" y="356" class="d-name">Motors</text>')
    g.append(_badge(590, 168, "3") + '<text x="614" y="174" class="d-name">Batteries</text>')
    g.append(_badge(590, 282, "4") + '<text x="614" y="280" class="d-name">Flight</text>'
             '<text x="614" y="300" class="d-name">controller</text>')
    g.append(_badge(590, 56, "5") + '<text x="614" y="54" class="d-name">Air</text>'
             '<text x="614" y="74" class="d-name">thermometer</text>'
             '<text x="614" y="92" class="d-sub">at the launch pad</text>')
    return ('<svg viewBox="0 0 760 420" role="img" class="drone-svg" '
            'aria-label="Top view of a delivery drone with its parts numbered 1 to 5">'
            + "".join(g) + "</svg>")


def parts_table() -> str:
    rows = "".join(
        f'<tr><td><span class="num-badge">{n}</span></td><td><strong>{escape(part)}</strong>'
        f'<div class="muted">{escape(what)}</div></td><td>{escape(record)}</td>'
        f'<td><code>{escape(cols)}</code></td></tr>'
        for n, part, what, record, cols in PARTS)
    return ('<table class="parts"><thead><tr><th></th><th>Part</th><th>What the technician writes down</th>'
            f'<th>Column in the data</th></tr></thead><tbody>{rows}</tbody></table>')


# ---------------------------------------------------------------- example rows

def _example_table(df: pd.DataFrame, cols: list[tuple[str, str]]) -> str:
    head = "".join(f"<th>{escape(name)}<div class='col-code'>{escape(c)}</div></th>" for c, name in cols)
    body = "".join(
        "<tr>" + "".join(f"<td>{escape('' if pd.isna(r[c]) else str(r[c]))}</td>" for c, _ in cols) + "</tr>"
        for _, r in df.iterrows())
    return f'<div class="scroll-x"><table class="example"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def example_flights() -> str:
    f = pd.read_csv(DATA / "healthy" / "flights.csv")
    return _example_table(f[f["drone_id"] == "D-01"].head(3), FLIGHT_COLS)


def example_parts() -> str:
    c = pd.read_csv(DATA / "healthy" / "components.csv")
    picks = pd.concat([
        c[(c.component_type == "motor") & (c.status == 1)].head(1),
        c[(c.component_type == "propeller") & (c.status == 1)].head(1),
        c[(c.component_type == "battery") & (c.failure_mode == "in_service")].head(1),
    ])
    picks = picks.assign(
        status=picks["status"].map({1: "yes", 0: "no (still OK)"}),
        end_date=picks["end_date"].fillna("(still in use)"),
        life_value=[f"{v:g} {'charges' if t == 'battery' else 'flight hours'}"
                    for v, t in zip(picks["life_value"], picks["component_type"])],
    )
    return _example_table(picks, PART_COLS)


# ---------------------------------------------------------------- the two test datasets

def _timeline(marks: list[tuple[int, str, str]]) -> str:
    """A flight 1 to 100 bar with coloured dots, and the events listed underneath in order."""
    ends = '<div class="tl-ends"><span>flight 1</span><span>flight 100</span></div>'
    if not marks:
        return (f'<div class="tl"><div class="tl-bar calm"></div>{ends}</div>'
                '<ul class="tl-list"><li><span class="tl-dot calm"></span>Nothing planted in any flight</li></ul>')
    dots = "".join(f'<span class="tl-dot {cls}" style="left:{(f - 1) / 99 * 100:.1f}%"></span>'
                   for f, _, cls in marks)
    items = "".join(f'<li><span class="tl-dot {cls}"></span><b>Flight {f}</b> {escape(label)}</li>'
                    for f, label, cls in sorted(marks))
    return (f'<div class="tl"><div class="tl-bar"></div>{dots}{ends}</div>'
            f'<ul class="tl-list">{items}</ul>')


def _lots(lots: list[tuple[str, str, int]]) -> str:
    rows = "".join(
        f'<div class="lot"><div class="lot-name">{escape(n)}<span>{escape(when)}</span></div>'
        f'<div class="lot-track"><div class="lot-bar{" bad" if life < 400 else ""}" '
        f'style="width:{life / 400 * 100:.0f}%">~{life} charges</div></div></div>'
        for n, when, life in lots)
    return f'<div class="lots"><div class="lots-cap">How long batteries from each batch last (built into the data)</div>{rows}</div>'


def scenario_cards() -> list[ui.Tag]:
    cards = []
    for s in SCENARIOS:
        cards.append(ui.div(
            ui.div(ui.span(f"Dataset {s['num']}", class_="tag"), ui.code(f"data/{s['file']}/"),
                   class_="card-head"),
            ui.h3(s["name"]),
            ui.p("Flights, September 2026", class_="mini-cap"),
            ui.HTML(_timeline(s["timeline"])),
            ui.HTML(_lots(s["lots"])),
            ui.tags.dl(
                ui.tags.dt("What happens"), ui.tags.dd(s["what"]),
                ui.tags.dt("What the tool should show"), ui.tags.dd(s["expect"]),
                class_="scenario-dl"),
            class_="info-card scenario"))
    return cards


# ---------------------------------------------------------------- the page

def intro_page() -> ui.Tag:
    """The welcome page shown before the dashboard."""
    return ui.div(
        ui.div(
            ui.div(
                ui.p("Six Sigma Hackathon · Team Flight Control", class_="eyebrow"),
                ui.h1("Drone Fleet Reliability Monitor"),
                ui.p("Catch wear before it becomes a mid-air failure. Built for the fleet "
                     "maintenance technician who decides, before each flight, which drones fly.",
                     class_="lede"),
                class_="intro-wrap",
            ),
            class_="hero",
        ),
        ui.div(
            ui.h2("How it works"),
            ui.div(*[ui.div(ui.span(n, class_="step-num"), ui.h3(t), ui.p(b), class_="step")
                     for n, t, b in STEPS], class_="grid-3"),

            # ---- the data, from the drone up ----
            ui.h2("What the data is"),
            ui.p("We don't have a real startup's records, so we invented realistic ones: one small "
                 "delivery fleet flying for one month.", class_="section-note"),
            ui.div(*[ui.div(ui.div(v, class_="fact-value"), ui.div(k, class_="fact-label"), class_="fact")
                     for v, k in FACTS], class_="facts"),

            ui.h3("The parts we keep track of", class_="sub-h"),
            ui.div(ui.HTML(drone_diagram()), ui.HTML(parts_table()), class_="diagram-card"),

            ui.h3("One flight, three moments", class_="sub-h"),
            ui.p("Every line of the flight logbook is one whole flight, with readings from before, during "
                 "and after it. Both datasets have all three.", class_="section-note"),
            moments_strip(),

            ui.h3("The two files", class_="sub-h"),
            ui.div(
                ui.div(ui.h3("flights.csv: the flight logbook"),
                       ui.p("One line per flight. These are the first 3 flights of drone D-01. The gray text "
                            "under each heading is the column's name in the file. One more column records "
                            "any alert during the flight."),
                       ui.HTML(example_flights()), class_="info-card"),
                ui.div(ui.h3("components.csv: the parts history"),
                       ui.p("One line per part, from the day it was installed until it failed, was removed, "
                            "or today. Three examples: a motor that failed, a propeller that failed, and "
                            "a battery still in use."),
                       ui.HTML(example_parts()), class_="info-card"),
                class_="stack",
            ),

            # ---- the two datasets ----
            ui.h2("The two test datasets"),
            ui.div(
                ui.p(ui.strong("Two invented fleets: one with problems, one without."),
                     " Both are the same 10 drones flying the same 1,000 flights in September 2026. The only "
                     "difference is the problems we planted, so we know the right answer and can check the "
                     "tool finds it, like testing a smoke alarm once with smoke and once without."),
                ui.p("The dashboard opens on the fleet with problems; the cards at the top switch to the healthy one."),
                class_="callout"),
            ui.div(*scenario_cards(), class_="grid-2"),

            ui.h2("Key terms"),
            ui.div(*[ui.div(ui.tags.dt(term), ui.tags.dd(desc), class_="term")
                     for term, desc in TERMS], class_="terms"),

            ui.h2("What's in the dashboard"),
            ui.div(*[ui.div(ui.h3(name), ui.p(desc), class_="info-card tab-card")
                     for name, desc in TABS], class_="grid-2"),

            ui.div(
                ui.input_action_button("enter", "Continue to the dashboard  →", class_="btn-continue"),
                ui.p("You can come back to this page any time from the header.", class_="section-note"),
                class_="continue-row",
            ),
            class_="intro-wrap intro-body",
        ),
        class_="intro",
    )
