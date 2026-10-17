"""Drone fleet reliability dashboard (Shiny for Python).

For the fleet maintenance technician: the current health of every drone (control
charts with all 8 Nelson / Western Electric rules and an EWMA, restarting after
each logged repair) and the wear of every installed part against its Weibull B10
replace-at age, with a timeline of every warning, replacement, failure and
special cause. Every statistic comes from qc.py; this file only loads data, calls
qc.py and displays the result.

Run locally:  ./testme.sh   (or: shiny run app.py, from this folder)
"""

from __future__ import annotations

import math
from html import escape
from pathlib import Path

import numpy as np
import pandas as pd
from shiny import App, reactive, render, ui
from shiny.types import SafeException

import charts
import qc
from intro import intro_page

HERE = Path(__file__).resolve().parent
FLEET = HERE / "data" / "fleet"  # a copy of the repo's data/fleet/; sync_data.sh refreshes it
STATUS_ORDER = {"ground": 0, "watch": 1, "not enough data": 2, "go": 3}
STATUS_CLASS = {"ground": "ground", "watch": "watch", "go": "go", "not enough data": "na",
                "neutral": "neutral"}
STATUS_WORD = {"ground": "Do not fly", "watch": "Warning", "go": "Can fly", "not enough data": "Not enough data"}
PART_NAME = {"motor": "Motor", "propeller": "Propeller", "battery": "Battery"}
#: Parts within this many flights of their replace-at age are listed as "coming up".
UPCOMING_FLIGHTS = 30

# (column, chart title, what it catches, units, decimals): the three readings behind the status
DRONE_CHARTS = [
    ("temp_rise_c", "Motor temperature rise", "motor wear, hard-landing damage", "°C", 1),
    ("vibration_rms", "Vibration", "propeller wear, strikes, imbalance, loose mounts", "m/s²", 2),
    ("sag_rate_v_per_min", "Battery voltage drop per minute", "battery wear, bad cells, loose connectors",
     "V/min", 3),
]

# Clicking a drone card sends its id to the server as input.open_drone.
CLICK_JS = ui.tags.script("""
document.addEventListener('click', function (e) {
  const row = e.target.closest('[data-drone]');
  if (row && window.Shiny) Shiny.setInputValue('open_drone', row.dataset.drone, {priority: 'event'});
});
""")


def pill(status: str) -> str:
    return f'<span class="pill {STATUS_CLASS[status]}">{STATUS_WORD[status]}</span>'


STATUS_SYMBOL = {"go": "✓", "watch": "!", "ground": "✕", "not enough data": "?"}
STATUS_COLOR = {"go": "#0a7d32", "watch": "#c98500", "ground": "#c62f2f", "not enough data": "#5f6670"}


def drone_icon(status: str) -> str:
    """A small top-view quadcopter drawn in the status colour, with the status symbol on its body."""
    c = STATUS_COLOR[status]
    arms = ((28, 28), (92, 28), (92, 92), (28, 92))
    g = "".join(f'<line x1="60" y1="60" x2="{x}" y2="{y}" stroke="#9aa3ad" stroke-width="7" stroke-linecap="round"/>'
                for x, y in arms)
    g += "".join(f'<circle cx="{x}" cy="{y}" r="22" fill="{c}" fill-opacity="0.13" stroke="{c}" '
                 f'stroke-opacity="0.55" stroke-width="2" stroke-dasharray="4 3"/>'
                 f'<line x1="{x - 18}" y1="{y + 5}" x2="{x + 18}" y2="{y - 5}" stroke="#6b7682" stroke-width="3.5" '
                 f'stroke-linecap="round" opacity="0.6"/><circle cx="{x}" cy="{y}" r="6.5" fill="#3a4450"/>'
                 for x, y in arms)
    g += (f'<rect x="42" y="44" width="36" height="32" rx="9" fill="{c}"/>'
          f'<text x="60" y="66.5" text-anchor="middle" font-size="19" font-weight="700" fill="#fff">'
          f'{STATUS_SYMBOL[status]}</text>')
    return f'<svg class="dc-icon" viewBox="0 0 120 120" aria-hidden="true">{g}</svg>'




def card_text(status: str, reason: str) -> str:
    """One short line for a drone card: the first reason, as a sentence."""
    short = reason.split(";")[0]
    return short[0].upper() + short[1:] + "."


def flights_phrase(n: float) -> str:
    n = round(n)
    if n <= 0:
        return "now"
    return f"in {n} flight{'s' if n != 1 else ''}"


controls = ui.div(
    ui.div(ui.span("Active fleet", class_="ctl-title"),
           ui.span("10 drones × 300 flights, Jul 1 – Sep 29, 2026 (simulated test data, data/fleet). "
                   "Click any drone card for its timeline, parts and control charts.", class_="ctl-sub"),
           class_="ctl-head"),
    ui.tags.details(
        ui.tags.summary("Or load your own logbook (CSV files)"),
        ui.div(
            ui.input_file("up_flights", "Flight logbook (flights.csv)", accept=[".csv"], button_label="Choose file"),
            ui.input_file("up_parts", "Parts history (components.csv, optional)", accept=[".csv"],
                          button_label="Choose file"),
            ui.input_file("up_maint", "Maintenance log (maintenance.csv, optional)", accept=[".csv"],
                          button_label="Choose file"),
            class_="upload-row"),
        ui.p("Same columns as the test data (see data/README.md in the repo). Without a maintenance log "
             "the charts never restart, so every past signal stays open.", class_="ctl-sub"),
        class_="upload-box"),
    class_="controls",
)


def drone_detail_body() -> ui.Tag:
    """The drone pop-up: status, maintenance timeline, parts, control charts."""
    return ui.div(
        ui.output_ui("drone_banner"),
        ui.div(
            ui.h4("Maintenance timeline"),
            ui.p("One row per part slot. W = warning (near its replace-at age, or found worn), R = replaced, "
                 "F = failed in flight, S = special cause found and fixed, | = chart signalled but nothing "
                 "was found. The amber bar is the warning time before each replacement.", class_="rule-note"),
            ui.output_plot("drone_timeline", height="560px"),
            class_="panel",
        ),
        ui.div(
            ui.h4("Installed parts: flights left before the replace-at age (B10)"),
            ui.output_ui("drone_parts"),
            class_="panel",
        ),
        ui.div(
            ui.h4("Control charts"),
            ui.output_ui("drone_numbers"),
            ui.output_plot("drone_charts", height="1050px"),
            class_="panel",
        ),
        ui.div(
            ui.h4("How to read these charts"),
            ui.div(ui.markdown(
                f"The shaded band is the drone's first {qc.N_BASELINE} flights, its **baseline**. The dashed "
                "**control limits** are the baseline mean ± 3σ, where σ̂ = average moving range ÷ 1.128; "
                "they never move. The orange **EWMA** weights recent flights most (λ = 0.2) to catch slow "
                "wear; its dotted limits are narrower because it averages.\n\n"
                "* A red **✕** is **rule 1**: one reading beyond 3σ. An amber **◆** is one of **rules 2–8**: "
                "a pattern (9 on one side, 6 trending, 14 alternating, 2 of 3 beyond 2σ, 4 of 5 beyond 1σ, "
                "15 within 1σ, 8 beyond 1σ on both sides). An orange ring is the EWMA beyond its limit.\n"
                "* Each **thin vertical line** is a logged action (a part replaced, a repair, an inspection). "
                "After it the EWMA starts again at the center line and the rules count afresh, so a run "
                "never spans a repair.\n"
                "* Using all 8 rules catches more problems and raises more false alarms: about 2% of "
                "readings, which shows up as \"no fault found\" inspections (|) on the timeline.\n"
                "* **Temperature rise** = hottest motor after landing − air temperature."),
                class_="read-me"),
            class_="panel"),
    )


dashboard = ui.div(
    CLICK_JS,
    ui.div(
        ui.div(ui.span("Drone Fleet Health & Part Wear Monitor", class_="title"),
               ui.span("Control charts with all 8 rules + Weibull replace-at ages, with every replacement logged",
                       class_="subtitle"),
               class_="topbar-left"),
        ui.input_action_button("about", "Guide & Data Reference", class_="btn-back"),
        class_="topbar",
    ),
    ui.div(
        controls,
        ui.navset_pill(
            ui.nav_panel(
                "Fleet health & replacements",
                ui.div(
                    ui.output_ui("fleet_summary"),
                    ui.div(ui.h4("Due soon"), ui.output_ui("due_soon"), class_="panel"),
                    ui.output_ui("fleet_cards"),
                    ui.div(
                        ui.h4("Fleet maintenance timeline"),
                        ui.p("Every drone on one row, flight number across: W = warning, R = replaced, "
                             "F = failed in flight, S = special cause fixed, faint | = inspected, nothing found. "
                             "No drone stops flying: every part is replaced, on time or right after it fails.",
                             class_="rule-note"),
                        ui.output_plot("fleet_timeline", height="440px"),
                        class_="panel"),
                    class_="pt-3"),
            ),
            ui.nav_panel(
                "Weibull reliability & replace-at ages",
                ui.div(
                    ui.p("Weibull survival models R(t) = exp(−(t/η)^β) fitted by maximum likelihood with "
                         "right-censoring across the fleet's parts history. Each part is replaced at B10, the "
                         "age by which 10% of parts fail (R(B10) = 90%), and warned "
                         f"{qc.WARN_FLIGHTS} flights before.", class_="section-note"),
                    ui.output_ui("rel_cards"),
                    ui.div(
                        ui.h4("Weibull reliability curves R(t) vs. Kaplan-Meier survival from the data"),
                        ui.output_plot("rel_curves", height="390px"),
                        ui.p("Blue curve = fitted two-parameter Weibull R(t). Gray steps = Kaplan-Meier "
                             "estimate from the same censored data, no model. Red dashed line = B10.",
                             class_="rule-note"),
                        class_="panel",
                    ),
                    ui.div(
                        ui.h4("Fitted Weibull parameters & 95% confidence intervals"),
                        ui.output_ui("stats_table"),
                        class_="panel",
                    ),
                    ui.div(
                        ui.h4("Replacement schedule, every drone"),
                        ui.output_ui("parts_by_drone"),
                        class_="panel",
                    ),
                    class_="pt-3",
                ),
            ),
            id="tabs",
        ),
        class_="dash",
    ),
)

app_ui = ui.page_fluid(
    ui.head_content(
        ui.tags.link(rel="preconnect", href="https://fonts.googleapis.com"),
        ui.tags.link(rel="stylesheet",
                     href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;650;700&display=swap"),
        ui.tags.style((HERE / "styles.css").read_text(encoding="utf-8")),
    ),
    ui.navset_hidden(
        ui.nav_panel("dashboard", dashboard),
        ui.nav_panel("intro", intro_page()),
        id="pages",
        selected="dashboard",
    ),
    title="Drone Fleet Health & Part Wear Monitor",
    class_="p-0",
)


def server(input, output, session):

    # ---------- page switching ----------
    @reactive.effect
    @reactive.event(input.enter, input.enter_top)
    def _enter():
        ui.update_navset("pages", selected="dashboard")

    @reactive.effect
    @reactive.event(input.about)
    def _about():
        ui.update_navset("pages", selected="intro")

    @reactive.effect
    @reactive.event(input.open_drone)
    def _open_drone():
        selected.set(input.open_drone())
        ui.modal_show(ui.modal(drone_detail_body(), title=None, size="xl", easy_close=True,
                               footer=ui.modal_button("Close"), class_="drone-modal"))

    # ---------- data ----------
    def _read(upload, default: Path, check, what: str) -> pd.DataFrame | None:
        if upload:
            try:
                return check(pd.read_csv(upload[0]["datapath"]))
            except (ValueError, pd.errors.ParserError) as err:
                raise SafeException(f"Can't use that {what}: {err}") from None
        if input.up_flights():          # someone else's flights: don't mix in our test fleet
            return None
        return check(pd.read_csv(default))

    @reactive.calc
    def flights_raw() -> pd.DataFrame:
        up = input.up_flights()
        if up:
            try:
                return qc.check_flights(pd.read_csv(up[0]["datapath"]))
            except (ValueError, pd.errors.ParserError) as err:
                raise SafeException(f"Can't use that flight logbook: {err}") from None
        return pd.read_csv(FLEET / "flights.csv")

    @reactive.calc
    def flights() -> pd.DataFrame:
        return qc.add_derived(flights_raw())

    @reactive.calc
    def maintenance() -> pd.DataFrame | None:
        return _read(input.up_maint(), FLEET / "maintenance.csv", qc.check_maintenance, "maintenance log")

    @reactive.calc
    def components() -> pd.DataFrame | None:
        return _read(input.up_parts(), FLEET / "components.csv", qc.check_components, "parts history")

    @reactive.calc
    def status() -> pd.DataFrame:
        st = qc.fleet_status(flights(), maintenance())
        st["_order"] = st["status"].map(STATUS_ORDER)
        return st.sort_values(["_order", "health", "drone_id"]).drop(columns="_order").reset_index(drop=True)

    @reactive.calc
    def by_type() -> pd.DataFrame:
        c = components()
        return qc.fit_by_type(c) if c is not None else pd.DataFrame()

    @reactive.calc
    def plan() -> pd.DataFrame:
        c = components()
        if c is None or by_type().empty:
            return pd.DataFrame(columns=["drone_id", "component_id", "component_type", "position", "age", "b10",
                                         "unit", "pct_used", "flights_left", "days_left", "overdue", "due"])
        return qc.replacement_plan(c, flights_raw(), by_type())

    @reactive.calc
    def timeline() -> pd.DataFrame:
        m = maintenance()
        if m is None or m.empty:
            return pd.DataFrame(columns=["drone_id", "lane", "flight_no", "marker", "detail"])
        return qc.maintenance_timeline(m)

    @reactive.calc
    def n_flights() -> int:
        return int(qc.flight_numbers(flights()["flight_id"]).max())

    selected = reactive.value(None)  # the drone whose pop-up is open

    # ---------- Fleet tab ----------
    @render.ui
    def fleet_summary():
        st, p, tl = status(), plan(), timeline()
        parts = []
        for s_ in ("go", "watch", "ground"):
            n = int((st["status"] == s_).sum())
            parts.append(f'<span class="sum-item {s_}"><span class="sym">{STATUS_SYMBOL[s_]}</span>'
                         f'<b>{n}</b> {STATUS_WORD[s_].lower()}</span>')
        n_due = int(p["due"].sum()) if len(p) else 0
        parts.append(f'<span class="sum-item parts-alert"><span class="sym">🔧</span>'
                     f'<b>{n_due}</b> part{"s" if n_due != 1 else ""} due within {qc.WARN_FLIGHTS} flights</span>')
        counts = tl["marker"].value_counts()
        activity = (f'Over flights 1–{n_flights()}: <b>{int(counts.get("R", 0))}</b> parts replaced on time, '
                    f'<b>{int(counts.get("F", 0))}</b> failed in flight, '
                    f'<b>{int(counts.get("S", 0))}</b> special causes found and fixed, '
                    f'<b>{int(counts.get("N", 0))}</b> inspections found nothing (false alarms).') if len(tl) else ""
        return ui.HTML(f'<div class="fleet-summary">{"".join(parts)}'
                       f'<span class="sum-hint">{activity}</span></div>')

    @render.ui
    def due_soon():
        p = plan()
        if p.empty:
            return ui.p("No parts history loaded, so no replace-at ages.", class_="rule-note")
        up = p[p["flights_left"] <= UPCOMING_FLIGHTS].sort_values("flights_left")
        if up.empty:
            return ui.p(f"No part reaches its replace-at age in the next {UPCOMING_FLIGHTS} flights.",
                        class_="rule-note")
        rows = []
        for r in up.itertuples():
            cls = "over" if r.overdue else "soon" if r.due else "ok"
            badge = ("ground", "Replace now") if r.overdue else ("watch", "Warning: replace") if r.due \
                else ("go", "Coming up")
            rows.append(
                f'<tr><td><b>{escape(r.drone_id)}</b></td>'
                f'<td>{PART_NAME[r.component_type]} {r.position} <code class="part-code">{escape(r.component_id)}</code></td>'
                f'<td class="num">{r.age:.0f} / {r.b10:.0f} {escape(r.unit)}</td>'
                f'<td class="pcell {cls}"><div class="pbar"><div style="width:{min(r.pct_used, 100):.0f}%"></div></div></td>'
                f'<td class="num">{flights_phrase(r.flights_left)}</td>'
                f'<td><span class="pill {badge[0]}">{badge[1]}</span></td></tr>')
        n_over = int(up["overdue"].sum())
        over_note = (f' <b>{n_over}</b> of them are already past it ("Replace now"). The replace-at age is '
                     "refitted on all the parts data every time, so as failures accumulate the estimate moves; "
                     "a lower estimate puts parts that were on schedule past it." if n_over else "")
        return ui.HTML(
            f'<p class="due-summary"><b>{int(up["due"].sum())}</b> part(s) within {qc.WARN_FLIGHTS} flights of '
            f'their replace-at age (warning) and <b>{int((~up["due"]).sum())}</b> more within '
            f'{UPCOMING_FLIGHTS}.{over_note}</p>'
            '<div class="scroll-x"><table class="numbers"><thead><tr><th>Drone</th><th>Part</th>'
            '<th>Used / replace at</th><th>Life used</th><th>Replace</th><th></th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>')

    @render.ui
    def fleet_cards():
        p = plan()
        cards = []
        for r in status().sort_values("drone_id").itertuples():
            cls = STATUS_CLASS[r.status]
            pct = 0 if math.isnan(r.health) else round(r.health * 100)
            mine = p[p["drone_id"] == r.drone_id]
            if mine.empty:
                p_badge = '<div class="dc-part-alert ok">No parts history loaded</div>'
            else:
                n_due = int(mine["due"].sum())
                nxt = mine.sort_values("flights_left").iloc[0]
                if n_due:
                    p_badge = (f'<div class="dc-part-alert soon">🔧 {n_due} part{"s" if n_due != 1 else ""} '
                               f'due within {qc.WARN_FLIGHTS} flights</div>')
                else:
                    p_badge = (f'<div class="dc-part-alert ok">✓ Next: {nxt.component_type} {nxt.position} '
                               f'{flights_phrase(nxt.flights_left)}</div>')
            cards.append(
                f'<button class="drone-card {cls}" data-drone="{escape(r.drone_id)}" '
                f'aria-label="{escape(r.drone_id)}: {escape(STATUS_WORD[r.status])}. Open its details">'
                f'<div class="dc-top"><span class="dc-id">{escape(r.drone_id)}</span>{pill(r.status)}</div>'
                f'{drone_icon(r.status)}'
                f'<div class="dc-health-wrap">'
                f'<div class="dc-health-label"><span>Telemetry health</span><b>{pct}%</b></div>'
                f'<div class="hbar {cls}"><div class="hbar-fill" style="width:{pct}%"></div></div>'
                f'</div>'
                f'{p_badge}'
                f'<div class="dc-why">{escape(card_text(r.status, r.reason))}</div>'
                f'<div class="dc-open">Timeline, parts &amp; charts ›</div></button>')
        legend = (
            "<b>Can fly</b> = no open chart signal in the last 10 flights · "
            "<b>Warning</b> = a signal nobody has inspected yet (any of the 8 rules or the EWMA) · "
            "<b>Do not fly</b> = the latest flight is beyond 3σ or the EWMA is beyond its limit now: inspect first · "
            "<b>Telemetry health</b> = room left before the nearest EWMA limit on the drone's tightest chart."
        )
        return ui.div(ui.HTML(f'<div class="hangar">{"".join(cards)}</div>'),
                      ui.HTML(f'<p class="rule-note">{legend}</p>'))

    @render.plot
    def fleet_timeline():
        tl = timeline()
        if tl.empty:
            return None
        return charts.fleet_timeline_figure(tl, sorted(flights()["drone_id"].unique()), n_flights())

    # ---------- Drone pop-up ----------
    @reactive.calc
    def drone_charts_data():
        """Every monitor chart for the selected drone, computed once by qc.py."""
        drone = selected.get()
        if not drone:
            return None
        f, m = flights(), maintenance()
        out = []
        try:
            for col, title, catches, unit, dec in DRONE_CHARTS:
                s = qc.drone_series(f, drone, col)
                resets = qc.reset_flights(m, drone, col)
                out.append((qc.monitor_chart(s["value"], s["flight_no"], resets), resets,
                            title, catches, unit, dec))
        except ValueError as err:
            raise SafeException(f"No charts for {drone}: {err}") from None
        return out

    @render.ui
    def drone_banner():
        drone = selected.get()
        if not drone:
            return None
        row = status().set_index("drone_id").loc[drone]
        cls = STATUS_CLASS[row["status"]]
        pct = 0 if math.isnan(row["health"]) else round(row["health"] * 100)
        driver = row["health_driver"] or "none"
        return ui.div(
            ui.div(
                ui.h3(drone),
                ui.HTML(pill(row["status"])),
                ui.span(f"Telemetry health: {pct}% (tightest margin: {driver})", class_="banner-driver"),
                class_="banner-head",
            ),
            ui.HTML(f'<div class="hbar big {cls}"><div class="hbar-fill" style="width:{pct}%"></div></div>'),
            ui.p(row["reason"][0].upper() + row["reason"][1:] + "."),
            class_=f"banner {cls}")

    @render.plot
    def drone_timeline():
        drone = selected.get()
        tl = timeline()
        if not drone or tl.empty:
            return None
        return charts.drone_timeline_figure(tl[tl["drone_id"] == drone], n_flights(), qc.N_BASELINE)

    @render.ui
    def drone_parts():
        drone = selected.get()
        if not drone:
            return None
        mine = plan()
        mine = mine[mine["drone_id"] == drone]
        if mine.empty:
            return ui.p("No parts history loaded.", class_="rule-note")
        rows = []
        for r in mine.sort_values("flights_left").itertuples():
            cls = "over" if r.overdue else "soon" if r.due else "ok"
            if r.overdue:
                badge = '<span class="pill ground">Replace now</span>'
            elif r.due:
                badge = f'<span class="pill watch">Warning: replace {flights_phrase(r.flights_left)}</span>'
            else:
                badge = f'<span class="pill go">OK, {round(r.flights_left)} flights left</span>'
            rows.append(
                f"<tr><td><b>{PART_NAME[r.component_type]} {r.position}</b> "
                f"<code class='part-code'>{escape(r.component_id)}</code></td>"
                f"<td class='num'>{r.age:.0f} / {r.b10:.0f} {escape(r.unit)} ({r.pct_used:.0f}%)</td>"
                f"<td class='pcell {cls}'><div class='pbar'><div style='width:{min(r.pct_used, 100):.0f}%'></div></div></td>"
                f"<td class='num'>{badge}</td></tr>")
        return ui.HTML(
            '<div class="scroll-x"><table class="numbers"><thead><tr>'
            "<th>Installed part</th><th>Used / replace at (B10)</th><th>Life used</th><th>Action</th>"
            f"</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
            f"<p class='rule-note'>Flights left = (B10 − age) ÷ the drone's average flight length; a battery "
            f"is charged every second flight. A part is warned {qc.WARN_FLIGHTS} flights before B10 and "
            "replaced at it; a chart signal can bring the replacement forward if the part is found worn.</p>")

    @render.ui
    def drone_numbers():
        data = drone_charts_data()
        if not data:
            return None
        rows = []
        for ch, resets, title, catches, unit, dec in data:
            last = ch.iloc[-1]
            live = ch[~ch["baseline"]]
            n_sig = int(live["signal"].sum())
            n_r1 = int(live["rule_1"].sum())
            n_ew = int(live["signal_ewma"].sum())
            rows.append(
                f"<tr><td>{escape(title)}<div class='muted-cell'>catches {escape(catches)}</div></td>"
                f'<td class="num">{last["center"]:.{dec}f} {unit}</td>'
                f'<td class="num">{last["lcl"]:.{dec}f} to {last["ucl"]:.{dec}f}</td>'
                f'<td class="num">{last["value"]:.{dec}f}</td>'
                f'<td class="num">{n_sig} ({n_r1} rule 1, {n_ew} EWMA)</td>'
                f'<td class="num">{len([r for r in resets if r > qc.N_BASELINE])}</td></tr>')
        table = ('<table class="numbers"><thead><tr><th>Reading</th><th>Baseline mean</th>'
                 "<th>3σ control limits</th><th>Latest</th><th>Flights that signalled</th>"
                 f"<th>Restarts</th></tr></thead><tbody>{''.join(rows)}</tbody></table>")
        return ui.HTML(f'<div class="scroll-x">{table}</div>')

    @render.plot
    def drone_charts():
        data = drone_charts_data()
        if not data:
            return None
        panels = [(ch, f"{title}: catches {catches}", unit, resets)
                  for ch, resets, title, catches, unit, _ in data]
        return charts.drone_monitor_figure(panels)

    # ---------- Weibull tab ----------
    @render.ui
    def rel_cards():
        if by_type().empty:
            return ui.p("No parts history loaded.", class_="rule-note")
        cards = []
        for r in by_type().itertuples():
            name = charts.PART_TITLE.get(r.component_type, r.component_type)
            if r.note:
                cards.append(ui.div(ui.h3(name), ui.p(f"Not enough failures to fit: {r.note}."),
                                    class_="info-card"))
                continue
            cards.append(ui.div(
                ui.h3(name),
                ui.div(ui.span("Replace at B10 =", class_="rc-label"),
                       ui.span(f"{r.b10:,.0f}", class_="rc-value"),
                       ui.span(r.unit, class_="rc-unit"), class_="rc-main"),
                ui.p(f"≈ {flights_equiv(r.component_type, r.b10):,.0f} drone flights · "
                     f"Weibull β = {r.beta:.2f}, η = {r.eta:.0f} {r.unit}",
                     class_="rc-sub"),
                class_="info-card rel-card"))
        return ui.div(*cards, class_="grid-3 mb-3")

    @render.ui
    def stats_table():
        if by_type().empty:
            return None
        rows = "".join(
            f"<tr><td><b>{escape(charts.PART_TITLE.get(r.component_type, r.component_type))}</b></td>"
            f'<td class="num">{r.n_failed} failed / {r.n} total</td>'
            f'<td class="num">{r.beta:.2f} ({r.beta_lo:.2f}–{r.beta_hi:.2f})</td>'
            f'<td class="num">{r.eta:.0f} ({r.eta_lo:.0f}–{r.eta_hi:.0f})</td>'
            f'<td class="num"><b>{r.b10:.0f}</b></td><td class="num">{r.mean_life:.0f}</td><td>{escape(r.unit)}</td></tr>'
            for r in by_type().dropna(subset=["eta"]).itertuples())
        return ui.HTML('<div class="scroll-x"><table class="numbers"><thead><tr><th>Component type</th><th>Censored sample</th>'
                       "<th>Shape β (95% CI)</th><th>Characteristic life η (95% CI)</th><th>B10</th><th>MTTF</th><th>Unit</th>"
                       f"</tr></thead><tbody>{rows}</tbody></table></div>"
                       '<p class="rule-note">Two-parameter Weibull fitted by maximum likelihood with right-censoring. '
                       "A part found worn at inspection counts as a (potential) failure; a part damaged by a special "
                       "cause, replaced on schedule or still flying counts as censored. Shape β &gt; 1 means wear-out "
                       "(the failure rate rises with age), which is what makes replacing at B10 = η(−ln 0.9)^(1/β) "
                       "worthwhile.</p>")

    @render.plot
    def rel_curves():
        c = components()
        if c is None or by_type().empty:
            return None
        curves = []
        for r in by_type().dropna(subset=["eta"]).itertuples():
            part = c[c["component_type"] == r.component_type]
            t = np.linspace(0, part["life_value"].max() * 1.1, 200)
            curves.append(dict(type=r.component_type, unit=r.unit, t=t, r=qc.reliability(t, r.beta, r.eta),
                               km=qc.km_curve(part["life_value"], part["status"]),
                               b10=r.b10, beta=r.beta, eta=r.eta))
        return charts.reliability_figure(curves) if curves else None

    @reactive.calc
    def mean_flight_min() -> float:
        return float(flights()["flight_min"].mean())

    def flights_equiv(component_type: str, b10: float) -> float:
        """Replace-at age expressed in drone flights (display only)."""
        if component_type == "battery":
            return b10 * qc.BATTERIES_PER_DRONE
        return b10 / (mean_flight_min() / 60)

    @render.ui
    def parts_by_drone():
        p = plan()
        if p.empty:
            return ui.p("No parts history loaded.", class_="rule-note")

        def part_rows(mine) -> str:
            rows = []
            for r in mine.sort_values(["component_type", "position"]).itertuples():
                cls = "over" if r.overdue else "soon" if r.due else "ok"
                rows.append(f'<tr><td>{PART_NAME[r.component_type]} {r.position}</td>'
                            f'<td class="num">{r.age:.0f} / {r.b10:.0f} {escape(r.unit)}</td>'
                            f'<td class="pcell {cls}"><div class="pbar"><div style="width:{min(r.pct_used, 100):.0f}%">'
                            f'</div></div></td><td class="num when {cls}">{flights_phrase(r.flights_left)}</td></tr>')
            return ('<table class="mini-parts"><thead><tr><th>Part</th><th>Used / B10</th><th>Life used</th>'
                    f'<th>Replace</th></tr></thead><tbody>{"".join(rows)}</tbody></table>')

        items = []
        for drone in sorted(p["drone_id"].unique()):
            mine = p[p["drone_id"] == drone]
            due = mine[mine["due"]]
            if len(due):
                parts = ", ".join(f"{r.component_type} {r.position}" for r in due.itertuples())
                action = f'<b class="over-t">Warning ({len(due)} due within {qc.WARN_FLIGHTS} flights):</b> {parts}'
            else:
                r = mine.sort_values("flights_left").iloc[0]
                action = f"Next: {r.component_type} {r.position} {flights_phrase(r.flights_left)}"
            items.append(f'<details class="pd-item"><summary><span class="pd-id">{escape(drone)}</span>'
                         f'<span class="pd-action">{action}</span><span class="pd-more">10 parts ▾</span></summary>'
                         f'{part_rows(mine)}</details>')
        return ui.HTML(f'<div class="pd-list">{"".join(items)}</div>')


app = App(app_ui, server)
