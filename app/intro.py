"""The welcome page: what you get, how it works, the two test datasets - then reference material.

Plain content only (no statistics). Edit the wording here freely; app.py
shows this page first and swaps to the dashboard when either button is
clicked: "Open the dashboard" in the hero, "Continue" at the bottom.
The example rows are read from the bundled data files, so they always match.
"""

from __future__ import annotations

from html import escape
from pathlib import Path

import pandas as pd
from shiny import ui

DATA = Path(__file__).resolve().parent / "data"

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
        ("Any alert: auto-return after a part failed", "inflight_event"),
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

FLEET = DATA / "fleet"
#: How each injected special cause is described on the welcome page.
CAUSE_CLASS = {"prop strike": "bad", "hard landing": "bad", "bad battery cell": "bad"}


TERMS = [
    ("Baseline", "Each drone's first 50 logged flights: its own normal variation sets the limits for "
                 "every later flight, and the limits never move. While they are being collected, each "
                 "reading is checked against the fleet's normal range from acceptance flights, so a wearing "
                 "part is caught from the very first flight."),
    ("Control limits (UCL / LCL)", "The upper and lower lines on a chart: baseline mean ± 3 sigma. "
                                   "A healthy drone stays between them about 99.7% of the time."),
    ("Sigma (σ)", "The typical flight-to-flight spread, estimated from the average jump between "
                  "consecutive baseline readings ÷ 1.128."),
    ("The 8 rules", "Nelson / Western Electric tests on each reading: rule 1 is one point beyond 3σ; "
                    "rules 2-8 are patterns (a run on one side, a trend, a zig-zag, points piling up near a "
                    "limit, or readings suspiciously flat). Each points to a different kind of special cause."),
    ("EWMA", "Exponentially weighted moving average: a running average that weights recent "
             "flights most (λ = 0.2). Catches slow wear long before any single reading looks odd."),
    ("Restart after a repair", "When the technician replaces a part, repairs something or inspects a "
                               "signal, that chart's EWMA starts again at the center line and the rules count "
                               "afresh, so old readings from a removed part don't keep raising alarms."),
    ("Common and special causes", "Common cause: the ordinary flight-to-flight noise. Special cause: "
                                  "something that changed, such as a worn part, a strike or a loose connector. "
                                  "Charts separate the two."),
    ("Temperature rise", "Hottest motor right after landing minus the air temperature (°C). "
                         "Subtracting the air temperature means a hot day isn't mistaken for wear."),
    ("Voltage sag", "Battery voltage at takeoff minus at landing, per flight minute (V/min). "
                    "It rises as a battery degrades."),
    ("Can fly / Warning / Do not fly", "Can fly: no open signal. Warning: a signal nobody has inspected "
                                       "yet. Do not fly: the latest flight is beyond 3σ or the EWMA is beyond its "
                                       "limit now, so inspect before the next flight."),
    ("Weibull life, B10, censored", "A model of how long each part type lasts, fitted from the parts "
                                    "history. B10 = the age by which 10% have failed - the replace-at "
                                    "age. Censored = parts still in use or removed for another reason, "
                                    "counted in the fit as 'lasted at least this long'."),
    ("R / F / S on the timeline", "R: warned and replaced before the next flight (the part reached its "
                                  "replace-at age, or a chart showed it worn). F: failed in flight, replaced "
                                  "before the next one. S: special cause found from a chart signal and fixed."),
    ("False alarm", "A chart signal with nothing wrong. With all 8 rules about 2% of readings do this. "
                    "They show on the control charts but need no action, so they are not on the timeline."),
]

WHAT_YOU_GET = [
    ("Fleet status at a glance", "All 10 drones on one screen: can fly, warning or do not fly, each "
                                 "with the reason, plus every part due for replacement soon."),
    ("Replacement timeline", "Every warned replacement, in-flight failure and special cause, flight by "
                             "flight, for the whole fleet and for each part slot of each drone."),
    ("Charts for any drone", "Click a drone card for its control charts - motor temperature, vibration, "
                             "battery voltage - with all 8 rules, an EWMA, and a restart at each repair."),
]

STEPS = [
    ("1", "Log each flight", "A minute of readings: the hottest motor's temperature, battery voltage, "
                             "and numbers from the flight log. Log every part you replace."),
    ("2", "Compare to the drone's own normal", "The first 50 flights set each drone's baseline; every "
                                               "later flight is checked against it with 8 rules and an EWMA."),
    ("3", "Replace before it fails", "A part is warned when it reaches its replace-at age, or as soon as a "
                                     "chart shows it wearing, and swapped before the next flight. The drone "
                                     "keeps flying."),
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
    f = pd.read_csv(FLEET / "flights.csv")
    return _example_table(f[f["drone_id"] == "D-01"].head(3), FLIGHT_COLS)


def example_parts() -> str:
    c = pd.read_csv(FLEET / "components.csv")
    picks = pd.concat([
        c[(c.component_type == "motor") & (c.status == 1)].head(1),
        c[c.failure_mode == "replaced_scheduled"].head(1),
        c[(c.component_type == "battery") & (c.failure_mode == "in_service")].head(1),
    ])
    picks = picks.assign(
        status=picks["status"].map({1: "yes", 0: "no (still OK)"}),
        end_date=picks["end_date"].fillna("(still in use)"),
        life_value=[f"{v:g} {'charges' if t == 'battery' else 'flight hours'}"
                    for v, t in zip(picks["life_value"], picks["component_type"])],
    )
    return _example_table(picks, PART_COLS)


# ---------------------------------------------------------------- the test fleet

def _timeline(marks: list[tuple[int, str, str]], n: int) -> str:
    """A flight 1 to n bar with coloured dots, and the events listed underneath in order."""
    ends = f'<div class="tl-ends"><span>flight 1</span><span>flight {n}</span></div>'
    dots = "".join(f'<span class="tl-dot {cls}" style="left:{(f - 1) / (n - 1) * 100:.1f}%"></span>'
                   for f, _, cls in marks)
    items = "".join(f'<li><span class="tl-dot {cls}"></span><b>Flight {f}</b> {escape(label)}</li>'
                    for f, label, cls in sorted(marks))
    return (f'<div class="tl"><div class="tl-bar"></div>{dots}{ends}</div>'
            f'<ul class="tl-list">{items}</ul>')


def fleet_card() -> ui.Tag:
    """The one test fleet: what was injected (from the answer key) and what the technician did."""
    key = pd.read_csv(FLEET / "answer_key.csv")
    m = pd.read_csv(FLEET / "maintenance.csv")
    f = pd.read_csv(FLEET / "flights.csv")
    n = int(f["flight_id"].str.rsplit("-", n=1).str[-1].astype(int).max())
    marks = [(int(e.start_flight), f"{e.drone_id}: {e.cause} (rule {e.rule_shape} shape), caught after "
              f"flight {int(e.detected_after_flight)} by {e.detected_by}", CAUSE_CLASS.get(e.cause, "wear"))
             for e in key.itertuples()]
    reasons = m.loc[m["action"] == "replace", "reason"]
    n_sched = int((reasons == "reached replace-at age (B10)").sum())
    n_worn = int(reasons.str.startswith("worn").sum())
    n_fail = int((reasons == "failed in flight").sum())
    return ui.div(
        ui.div(ui.span("Test fleet", class_="tag"), ui.code("data/fleet/"), class_="card-head"),
        ui.h3(f"10 drones, {len(f):,} flights, Jul–Sep 2026"),
        ui.p(f"The {len(key)} special causes injected at random (the simulation's answer key)", class_="mini-cap"),
        ui.HTML(_timeline(marks, n)),
        ui.tags.dl(
            ui.tags.dt("What happens"),
            ui.tags.dd("Every part wears out at its own random Weibull life, and in its last stretch it "
                       "pushes one reading up (motor → temperature, propeller → vibration, battery → voltage "
                       "sag). On top of that, the special causes above strike random drones. Nothing is "
                       "scripted on a named drone."),
            ui.tags.dt("What the technician did"),
            ui.tags.dd(f"{n_sched} parts warned at their replace-at age and {n_worn} warned early because a chart "
                       "showed them wearing (including in each drone's first 50 flights, checked against the "
                       "fleet's normal range), each replaced before the next flight. "
                       + (f"{n_fail} failed in flight and were replaced before the next flight. " if n_fail else
                          "No part failed in flight. ")
                       + "No drone ever stopped flying."),
            ui.tags.dt("What the tool should show"),
            ui.tags.dd("Every special cause above is signalled, on the flight listed. Run on these files, the "
                       "tool signals on exactly the flights where the technician acted - checked for all 30 "
                       "drone charts in the tests."),
            class_="scenario-dl"),
        class_="info-card scenario")


# ---------------------------------------------------------------- the page

def _fold(summary: str, *body: ui.Tag) -> ui.Tag:
    """Reference material behind a native <details>, so the page stays short."""
    return ui.tags.details(
        ui.tags.summary(summary),
        ui.div(*body, class_="fold-body"),
        class_="fold",
    )


def intro_page() -> ui.Tag:
    """The welcome page shown before the dashboard."""
    return ui.div(
        ui.div(
            ui.div(
                ui.p("Six Sigma Hackathon · Team Flight Control", class_="eyebrow"),
                ui.h1("Drone Fleet Reliability Monitor"),
                ui.p("Catch wear before it becomes a mid-air failure. Every morning, the fleet "
                     "maintenance technician sees which of the 10 drones can fly, which parts to swap "
                     "next - and why.",
                     class_="lede"),
                ui.div(
                    ui.span("10 drones", class_="stat-chip"),
                    ui.span("3,000 flights", class_="stat-chip"),
                    ui.span("every replacement logged", class_="stat-chip"),
                    class_="hero-stats",
                ),
                ui.div(
                    ui.input_action_button("enter_top", "Open the dashboard  →", class_="btn-hero"),
                    ui.span("or read on - everything below explains what you will see", class_="hero-hint"),
                    class_="hero-cta",
                ),
                class_="intro-wrap",
            ),
            class_="hero",
        ),
        ui.div(
            # ---- what the tool gives you ----
            ui.h2("What you get"),
            ui.div(*[ui.div(ui.h3(name), ui.p(desc), class_="info-card tab-card")
                     for name, desc in WHAT_YOU_GET], class_="grid-3"),

            ui.h2("How it works"),
            ui.div(*[ui.div(ui.span(n, class_="step-num"), ui.h3(t), ui.p(b), class_="step")
                     for n, t, b in STEPS], class_="grid-3"),

            # ---- the test fleet ----
            ui.h2("The test fleet"),
            ui.div(
                ui.p(ui.strong("One invented fleet, flying for three months."),
                     " Parts wear out and get replaced, and random problems strike - the kind a real "
                     "delivery fleet sees. Because we generated it, we know every problem we put in, so we "
                     "can check the tool catches each one, like testing a smoke alarm with real smoke."),
                class_="callout"),
            fleet_card(),

            # ---- the data, folded away ----
            ui.h2("The data, from the drone up"),
            ui.p("We don't have a real startup's records, so we invented realistic ones: one small "
                 "delivery fleet flying for three months.", class_="section-note"),
            _fold("The drone and the 5 things the technician measures",
                  ui.div(ui.HTML(drone_diagram()), ui.HTML(parts_table()), class_="diagram-card")),
            _fold("One flight, three moments",
                  ui.p("Every line of the flight logbook is one whole flight, with readings from before, "
                       "during and after it.", class_="section-note"),
                  moments_strip()),
            _fold("Example rows from the data files",
                  ui.div(
                      ui.div(ui.h3("flights.csv: the flight logbook"),
                             ui.p("One line per flight - here, the first 3 flights of D-01. The gray text "
                                  "under each heading is the column's name in the file."),
                             ui.HTML(example_flights()), class_="info-card"),
                      ui.div(ui.h3("components.csv: the parts history"),
                             ui.p("One line per part, from install to failure, removal or today - three "
                                  "examples from that table."),
                             ui.HTML(example_parts()), class_="info-card"),
                      class_="stack")),

            # ---- key terms, folded away ----
            ui.h2("Key terms"),
            _fold("Open the key terms (baseline, sigma, signal, EWMA, B10 ...)",
                  ui.div(*[ui.div(ui.tags.dt(term), ui.tags.dd(desc), class_="term")
                           for term, desc in TERMS], class_="terms")),

            ui.div(
                ui.input_action_button("enter", "Continue to the dashboard  →", class_="btn-continue"),
                ui.p("You can come back to this page any time from the header.", class_="section-note"),
                class_="continue-row",
            ),
            class_="intro-wrap intro-body",
        ),
        class_="intro",
    )
