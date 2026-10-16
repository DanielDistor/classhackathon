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
