"""The welcome page: what the tool does, the test datasets, key terms, the tabs.

Plain content only (no statistics). Edit the wording here freely; app.py
shows this page first and swaps to the dashboard when "Continue" is clicked.
"""

from __future__ import annotations

from shiny import ui

DATASET_CARDS = [
    {
        "key": "healthy",
        "name": "Healthy fleet",
        "tag": "Baseline",
        "body": "10 drones, about 100 flights each over September 2026. Nothing is planted: "
                "every drone wears normally.",
        "look": "Almost every drone is go. D-06 and D-07 show a 'watch' false alarm, a reminder "
                "that 3σ limits estimated from 30 flights aren't perfect.",
    },
    {
        "key": "motor_drift",
        "name": "Motor drift + prop strike",
        "tag": "The demo",
        "body": "Same fleet. D-07's motor 3 bearing wears: its temperature rise climbs 0.2 °C per "
                "flight after flight 60, and it crashes on flight 95. D-03 has a prop strike on flight 80.",
        "look": "D-07 is grounded. Its EWMA crosses the limit at flight 74, 21 flights before the crash. "
                "D-03's vibration chart flags flight 80.",
    },
    {
        "key": "bad_battery_lot",
        "name": "Bad battery lot",
        "tag": "Reliability",
        "body": "Same fleet, but batteries from supplier lot B wear out about 40% sooner "
                "(true life scale 240 cycles instead of 400).",
        "look": "The flight charts look healthy. The problem only shows in the Reliability tab "
                "(coming in Stage 4), which compares battery lots.",
    },
]

TERMS = [
    ("Baseline", "Each drone's first 30 logged flights. The drone is assumed healthy then, and "
                 "its own normal variation sets the limits for every later flight."),
    ("Control limits (UCL / LCL)", "The upper and lower lines on a chart: baseline mean ± 3σ̂. "
                                   "A healthy drone stays between them about 99.7% of the time."),
    ("σ̂ (sigma-hat)", "The estimated flight-to-flight spread: the average jump between "
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
    ("Go / Watch / Ground", "Go: every chart in control. Watch: a signal in the last 10 flights. "
                            "Ground: the latest reading is out, the EWMA is out now, or the drone crashed."),
    ("Weibull life, B10, censored", "Coming in Stage 4. A Weibull model of how long parts last, "
                                    "B10 = the age by which 10% have failed, and censored = parts "
                                    "that haven't failed yet."),
]

TABS = [
    ("Fleet", "Every drone's status, go, watch or ground, with the reason in plain English. "
              "Start here each morning."),
    ("Drone", "Four control charts for the drone you pick: EWMA and I chart of motor temperature "
              "rise, plus vibration and battery voltage sag. Each comes with a table explaining every number."),
    ("Reliability", "How long motors, propellers and batteries last, and when to replace them "
                    "(coming in Stage 4)."),
]

STEPS = [
    ("1", "Log each flight", "Flight minutes, air temperature, battery voltage at takeoff and landing, "
                             "hottest motor temperature (infrared thermometer) and vibration from "
                             "the flight log."),
    ("2", "Compare to the drone's own normal", "The tool learns each drone's normal from its first "
                                               "30 flights and checks every new flight against it."),
    ("3", "Act on go / watch / ground", "Ground a drone before it fails in the air, instead of "
                                        "investigating after a crash."),
]


FACTS = [
    ("10", "delivery drones (D-01 to D-10)"),
    ("~100", "flights each, Sep 1–30, 2026"),
    ("~1,000", "flights logged per dataset"),
    ("~22 min", "per flight, 0.5–2.5 kg package"),
    ("~300", "part records since spring 2025"),
]


def _callout(x: int, y: int, title: str, lines: list[str], cols: list[str], anchor: str = "start") -> str:
    """One label block: a bold title, plain lines, then the data columns in monospace."""
    out = [f'<text x="{x}" y="{y}" text-anchor="{anchor}" class="d-title">{title}</text>']
    yy = y + 19
    for ln in lines:
        out.append(f'<text x="{x}" y="{yy}" text-anchor="{anchor}" class="d-body">{ln}</text>')
        yy += 16
    for c in cols:
        out.append(f'<text x="{x}" y="{yy + 2}" text-anchor="{anchor}" class="d-col">{c}</text>')
        yy += 16
    return "".join(out)


def drone_diagram() -> str:
    """Top view of a quadcopter, each part labelled with the data columns it produces."""
    cx, cy, r_prop = 480, 270, 70
    arms = {1: (360, 150), 2: (600, 150), 3: (600, 390), 4: (360, 390)}
    parts = []
    for n, (x, y) in arms.items():
        parts.append(f'<line x1="{cx}" y1="{cy}" x2="{x}" y2="{y}" class="d-arm"/>')
    for n, (x, y) in arms.items():
        cls = "d-prop strike" if n == 1 else "d-prop"
        parts.append(f'<circle cx="{x}" cy="{y}" r="{r_prop}" class="{cls}"/>')
        parts.append(f'<line x1="{x - 58}" y1="{y + 14}" x2="{x + 58}" y2="{y - 14}" class="d-blade"/>')
    for n, (x, y) in arms.items():
        cls = "d-motor wear" if n == 3 else "d-motor"
        parts.append(f'<circle cx="{x}" cy="{y}" r="20" class="{cls}"/>')
        parts.append(f'<text x="{x}" y="{y + 5}" text-anchor="middle" class="d-motor-num">{n}</text>')
    body = (
        f'<rect x="410" y="215" width="140" height="110" rx="18" class="d-body-shape"/>'
        f'<rect x="430" y="228" width="100" height="34" rx="6" class="d-battery"/>'
        f'<text x="480" y="250" text-anchor="middle" class="d-inner">BATTERY</text>'
        f'<rect x="455" y="275" width="50" height="36" rx="5" class="d-fc"/>'
        f'<text x="480" y="298" text-anchor="middle" class="d-inner">FC</text>'
        f'<text x="480" y="52" text-anchor="middle" class="d-front">▲ front</text>'
    )
    leaders = "".join(f'<polyline points="{p}" class="d-leader"/>' for p in (
        "252,84 310,101",            # propellers -> prop 1 rim
        "252,262 410,268",           # package -> body
        "252,436 342,398",           # motors -> motor 4
        "708,217 530,245",           # batteries -> battery
        "708,327 505,295",           # flight controller -> FC
    )) + "".join(f'<circle cx="{x}" cy="{y}" r="3.5" class="d-dot"/>' for x, y in (
        (310, 101), (410, 268), (342, 398), (530, 245), (505, 295)))
    labels = "".join([
        _callout(24, 70, "Propellers ×4", ["Chips and cracks are caught", "at the before-flight check"],
                 ["preflight_fail_item", "components.csv (flight hours)"]),
        _callout(24, 248, "Package", ["Weighed at loading"], ["payload_kg"]),
        _callout(24, 404, "Motors ×4", ["Hottest motor, infrared", "thermometer right after landing"],
                 ["motor_temp_max_c", "components.csv (flight hours)"]),
        _callout(936, 70, "Air at the launch pad", ["Not on the drone: subtracted so", "a hot day isn't mistaken for wear"],
                 ["ambient_temp_c"], anchor="end"),
        _callout(936, 203, "Batteries ×2, used in turn", ["The battery reports its own", "voltage and charge cycles"],
                 ["battery_id · battery_cycles", "voltage_start_v · voltage_end_v", "components.csv (cycles, lot A/B/C)"],
                 anchor="end"),
        _callout(936, 330, "Flight controller (FC)", ["Its log gives flight time,", "vibration and alerts"],
                 ["flight_min · vibration_rms", "inflight_event"], anchor="end"),
    ])
    planted = (
        '<text x="360" y="66" text-anchor="middle" class="d-planted">D-03: prop strike on flight 80</text>'
        '<text x="600" y="482" text-anchor="middle" class="d-planted">D-07: motor 3 wears out, crash on flight 95</text>'
    )
    return (
        '<svg viewBox="0 0 960 500" role="img" class="drone-svg" '
        'aria-label="Top view of a quadcopter with each part labelled with the data it produces">'
        + "".join(parts) + body + leaders + labels + planted + "</svg>"
    )


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

            ui.h2("What we track on each drone"),
            ui.p("Every number in the dashboard comes from something a technician can measure with "
                 "a checklist, an infrared thermometer, the battery's own readout or the flight log. "
                 "Gray labels are the column names in the data files.", class_="section-note"),
            ui.div(*[ui.div(ui.div(v, class_="fact-value"), ui.div(k, class_="fact-label"), class_="fact")
                     for v, k in FACTS], class_="facts"),
            ui.div(ui.HTML(drone_diagram()),
                   ui.p(ui.span("Red", class_="red-word"), " marks where the planted problems happen in the "
                        "motor-drift dataset.", class_="diagram-note"),
                   class_="diagram-card"),

            ui.h2("The test datasets"),
            ui.p("All three are invented, built by data/simulate.py from the same random draws, so "
                 "they differ only in what was planted. Pick one in the sidebar.", class_="section-note"),
            ui.div(*[ui.div(
                ui.div(ui.h3(c["name"]), ui.span(c["tag"], class_="tag"), class_="card-head"),
                ui.p(c["body"]),
                ui.p(ui.strong("What to look for: "), c["look"], class_="look"),
                class_="info-card") for c in DATASET_CARDS], class_="grid-3"),

            ui.h2("Key terms"),
            ui.div(*[ui.div(ui.tags.dt(term), ui.tags.dd(desc), class_="term")
                     for term, desc in TERMS], class_="terms"),

            ui.h2("What's in the dashboard"),
            ui.div(*[ui.div(ui.h3(name), ui.p(desc), class_="info-card tab-card")
                     for name, desc in TABS], class_="grid-3"),

            ui.div(
                ui.input_action_button("enter", "Continue to the dashboard  →", class_="btn-continue"),
                ui.p("You can come back to this page any time from the header.", class_="section-note"),
                class_="continue-row",
            ),
            class_="intro-wrap intro-body",
        ),
        class_="intro",
    )
