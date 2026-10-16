"""Drone fleet reliability dashboard (Shiny for Python).

For the fleet maintenance technician: before each flight, which drones are
go, watch or ground, and why. Every statistic comes from qc.py; this file only
loads data, calls qc.py and shows the result. The welcome page lives in
intro.py and the look in styles.css.

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
DATA = HERE / "data"  # a copy of the repo's data/ folder; manifestme.sh refreshes it
DATASETS = {  # folder in data/ -> (name, what's in it)
    "problem_fleet": ("Fleet with problems", "The main demo. D-07's motor wears out (crash on flight 95), "
                      "D-03 hits something on flight 80, and batteries from supplier lot B die early."),
    "healthy": ("Healthy fleet", "The same 10 drones with nothing wrong, for comparison: the tool "
                "should not raise alarms here."),
}
STATUS_ORDER = {"ground": 0, "watch": 1, "not enough data": 2, "go": 3}
STATUS_CLASS = {"ground": "ground", "watch": "watch", "go": "go", "not enough data": "na",
                "neutral": "neutral"}
STATUS_WORD = {"ground": "Do not fly", "watch": "Warning", "go": "Can fly", "not enough data": "Not enough data"}

# (column, chart title, units, decimals, EWMA too?)
DRONE_CHARTS = [
    ("temp_rise_c", "Motor temperature rise", "°C", 1, True),
    ("vibration_rms", "Vibration", "m/s²", 2, False),
    ("sag_rate_v_per_min", "Battery voltage sag per minute", "V/min", 3, False),
]

# Clicking a drone row sends its id to the server as input.open_drone.
CLICK_JS = ui.tags.script("""
document.addEventListener('click', function (e) {
  const row = e.target.closest('[data-drone]');
  if (row && window.Shiny) Shiny.setInputValue('open_drone', row.dataset.drone, {priority: 'event'});
});
""")


def pill(status: str) -> str:
    return f'<span class="pill {STATUS_CLASS[status]}">{STATUS_WORD[status]}</span>'


def health_bar(health: float, status: str, big: bool = True) -> str:
    """A filled bar: length = health (room left before a limit), colour = status."""
    if health is None or (isinstance(health, float) and math.isnan(health)):
        return '<div class="hbar na"><div class="hbar-fill" style="width:0%"></div></div>'
    pct = round(health * 100)
    return (f'<div class="hbar {STATUS_CLASS[status]}{" big" if big else ""}" role="meter" '
            f'aria-valuemin="0" aria-valuemax="100" aria-valuenow="{pct}">'
            f'<div class="hbar-fill" style="width:{max(pct, 1)}%"></div></div>')


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


WARNING_NOTE = "Often just chance: inspect at the next check."


def card_text(status: str, reason: str) -> str:
    """One short line for a drone card. Warnings say which flights looked unusual, plainly."""
    import re
    if status == "watch":
        flights = sorted({int(n) for grp in re.findall(r"flights? ([\d, ]+)", reason)
                          for n in re.findall(r"\d+", grp)})
        where = (f"on flight {flights[0]}" if len(flights) == 1
                 else f"in flights {flights[0]}–{flights[-1]}" if flights else "recently")
        return f"Unusual reading{'s' if len(flights) > 1 else ''} {where}. {WARNING_NOTE}"
    short = reason.split(";")[0]
    return short[0].upper() + short[1:] + "."


def pct_text(health: float) -> str:
    return "–" if isinstance(health, float) and math.isnan(health) else f"{round(health * 100)}%"


controls = ui.div(
    ui.div(ui.span("Which fleet?", class_="ctl-title"),
           ui.span("Both are invented test data: the same 10 drones flying for September 2026.", class_="ctl-sub"),
           class_="ctl-head"),
    ui.input_radio_buttons(
        "dataset", None,
        {k: ui.TagList(ui.span(name, class_="ds-name"), ui.span(desc, class_="ds-desc"))
         for k, (name, desc) in DATASETS.items()},
        selected="problem_fleet", inline=True),
    class_="controls",
)

dashboard = ui.div(
    CLICK_JS,
    ui.div(
        ui.div(ui.span("Drone Fleet Reliability Monitor", class_="title"),
               ui.span("which drones can fly today, and why", class_="subtitle")),
        ui.input_action_link("about", "About this tool and the datasets"),
        class_="topbar",
    ),
    ui.div(
        controls,
        ui.navset_pill(
            ui.nav_panel(
                "Fleet status",
                ui.div(ui.output_ui("fleet_summary"), ui.output_ui("fleet_cards"), class_="pt-3"),
            ),
            ui.nav_panel(
                "Drone detail",
                ui.div(
                    ui.div(ui.input_select("drone", "Drone", [], width="220px"),
                           ui.p("Pick a drone here, or click one on the Fleet status view.", class_="ctl-sub"),
                           class_="drone-pick"),
                    ui.output_ui("drone_banner"),
                    ui.div(ui.h4("The numbers behind the charts"), ui.output_ui("drone_numbers"),
                           class_="panel"),
                    ui.div(ui.output_plot("drone_charts", height="1250px"), class_="panel"),
                    ui.div(
                        ui.h4("How to read these charts"),
                        ui.div(ui.markdown(
                            "The shaded band is the drone's first 30 flights, its **baseline**. The dashed "
                            "**limits** are the baseline mean ± 3 sigma, where sigma = average moving range "
                            "÷ 1.128. A red ✕ is a **signal**: a reading the drone's own normal variation is "
                            "very unlikely to produce.\n\n"
                            "* **EWMA** (top chart): a running average that weights recent flights most "
                            "(λ = 0.2). It catches slow wear early.\n"
                            "* **I charts**: each reading on its own. They catch sudden damage.\n"
                            "* **Temperature rise** = hottest motor after landing − air temperature, so a "
                            "hot day isn't mistaken for wear."), class_="read-me"),
                        class_="panel"),
                    class_="pt-3",
                ),
            ),
            ui.nav_panel(
                "Part reliability",
                ui.div(
                    ui.p("How long motors, propellers and batteries last, from this fleet's parts history "
                         "(components.csv). Parts that haven't failed yet still count: they tell us the part "
                         "lasted at least that long.", class_="section-note"),
                    ui.output_ui("rel_cards"),
                    ui.div(ui.h4("How long parts last"),
                           ui.output_plot("rel_curves", height="380px"),
                           ui.p("Blue = the fitted Weibull model. Gray steps = the same thing measured straight "
                                "from the data (Kaplan-Meier). When the two agree, the model fits. Red dashed "
                                "line = B10, the age by which 10% of parts have failed.", class_="rule-note"),
                           class_="panel"),
                    ui.div(ui.h4("Battery batches compared"),
                           ui.output_ui("lot_sentence"),
                           ui.output_plot("lot_plot", height="260px"),
                           class_="panel"),
                    ui.div(ui.h4("Parts to replace at the next maintenance slot"),
                           ui.output_ui("due_table"), class_="panel"),
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
        ui.nav_panel("intro", intro_page()),
        ui.nav_panel("dashboard", dashboard),
        id="pages",
    ),
    title="Drone Fleet Reliability Monitor",
    class_="p-0",
)


def server(input, output, session):

    # ---------- page switching ----------
    @reactive.effect
    @reactive.event(input.enter)
    def _enter():
        ui.update_navset("pages", selected="dashboard")

    @reactive.effect
    @reactive.event(input.about)
    def _about():
        ui.update_navset("pages", selected="intro")

    @reactive.effect
    @reactive.event(input.open_drone)
    def _open_drone():
        ui.update_select("drone", selected=input.open_drone())
        ui.update_navset("tabs", selected="Drone detail")

    # ---------- data ----------
    @reactive.calc
    def flights() -> pd.DataFrame:
        f = pd.read_csv(DATA / input.dataset() / "flights.csv")
        return qc.add_derived(f)

    @reactive.calc
    def status() -> pd.DataFrame:
        st = qc.fleet_status(flights())
        st["_order"] = st["status"].map(STATUS_ORDER)
        return st.sort_values(["_order", "health", "drone_id"]).drop(columns="_order").reset_index(drop=True)

    @reactive.effect
    def _drones():
        st = status()
        ui.update_select("drone", choices=sorted(st["drone_id"]),
                         selected=st["drone_id"].iloc[0] if len(st) else None)

    # ---------- Fleet status tab ----------
    @render.ui
    def fleet_summary():
        st = status()
        parts = []
        for s_ in ("go", "watch", "ground"):
            n = int((st["status"] == s_).sum())
            parts.append(f'<span class="sum-item {s_}"><span class="sym">{STATUS_SYMBOL[s_]}</span>'
                         f'<b>{n}</b> {STATUS_WORD[s_].lower()}</span>')
        note = ""
        n_watch = int((st["status"] == "watch").sum())
        if input.dataset() == "healthy":
            note = ('<p class="fleet-note"><b>Nothing was planted in this fleet.</b> '
                    + (f"The {n_watch} warning{'s are' if n_watch != 1 else ' is'} ordinary chance readings: "
                       if n_watch else "")
                    + "each control limit is set so a normal reading crosses it only about 3 times in 1,000, "
                    "and the tool checks 10 drones × 4 charts over their last 10 flights (400 checks), so one or "
                    "two chance warnings are expected. No drone is marked Do not fly.</p>")
        return ui.HTML(f'<div class="fleet-summary">{"".join(parts)}'
                       f'<span class="sum-hint">Click a drone to see why.</span>{note}</div>')

    @render.ui
    def fleet_cards():
        cards = []
        for r in status().sort_values("drone_id").itertuples():
            cls = STATUS_CLASS[r.status]
            cards.append(
                f'<button class="drone-card {cls}" data-drone="{escape(r.drone_id)}" '
                f'aria-label="{escape(r.drone_id)}: {escape(STATUS_WORD[r.status])}. Open its details">'
                f'<div class="dc-top"><span class="dc-id">{escape(r.drone_id)}</span>{pill(r.status)}</div>'
                f'{drone_icon(r.status)}'
                f'<div class="dc-health">{health_bar(r.health, r.status, big=False)}'
                f'<span>{pct_text(r.health)}</span></div>'
                f'<div class="dc-why">{escape(card_text(r.status, r.reason))}</div>'
                f'<div class="dc-open">Details ›</div></button>')
        legend = ("<b>Health</b> = how much room is left before the nearest control limit, on the drone's "
                  "most-stretched chart: 100% = right at its normal, 0% = at a limit or crashed. "
                  "<b>Can fly</b> = every chart in control · <b>Warning</b> = a warning sign in the last 10 flights, "
                  "fly but inspect soon · <b>Do not fly</b> = a reading is out of limits now, or it crashed.")
        return ui.div(ui.HTML(f'<div class="hangar">{"".join(cards)}</div>'),
                      ui.HTML(f'<p class="rule-note">{legend}</p>'))

    # ---------- Drone detail tab ----------
    @reactive.calc
    def drone_charts_data():
        """Every chart for the selected drone, computed once by qc.py."""
        drone = input.drone()
        if not drone:
            return None
        f = flights()
        out = []
        try:
            for col, title, unit, dec, with_ewma in DRONE_CHARTS:
                s = qc.drone_series(f, drone, col)
                if with_ewma:
                    out.append(("ewma", qc.ewma_chart(s["value"]), s["flight_no"], title, unit, dec))
                out.append(("i", qc.imr_chart(s["value"]), s["flight_no"], title, unit, dec))
        except ValueError as err:
            raise SafeException(f"No charts for {drone}: {err}") from None
        return out

    @render.ui
    def drone_banner():
        drone = input.drone()
        if not drone:
            return None
        row = status().set_index("drone_id").loc[drone]
        cls = STATUS_CLASS[row["status"]]
        return ui.div(
            ui.div(ui.h3(drone), ui.HTML(pill(row["status"])), class_="banner-head"),
            ui.HTML(f'<div class="banner-health">{health_bar(row["health"], row["status"])}'
                    f'<span>{pct_text(row["health"])} health</span></div>'),
            ui.p(row["reason"][0].upper() + row["reason"][1:] + "."
                 + (f" {WARNING_NOTE}" if row["status"] == "watch" else "")),
            class_=f"banner {cls}")

    @render.ui
    def drone_numbers():
        data = drone_charts_data()
        if not data:
            return None
        rows = []
        for kind, ch, flight_no, title, unit, dec in data:
            sig = ch["signal"] if kind == "ewma" else ch["signal_i"]
            latest = ch["z"].iloc[-1] if kind == "ewma" else ch["value"].iloc[-1]
            last = ch.iloc[-1]
            room = qc.chart_margin(latest, last["center"], last["lcl"], last["ucl"])
            hits = flight_no.reset_index(drop=True)[(sig & ~ch["baseline"]).to_numpy()]
            first = f"flight {hits.iloc[0]}" if len(hits) else "none"
            name = f"{title} · {'EWMA' if kind == 'ewma' else 'I chart'}"
            limit_note = " (settled)" if kind == "ewma" else ""
            rows.append(
                f"<tr><td>{escape(name)}</td>"
                f'<td class="num">{ch["center"].iloc[0]:.{dec}f} {unit}</td>'
                f'<td class="num">{last["lcl"]:.{dec}f} to {last["ucl"]:.{dec}f}{limit_note}</td>'
                f'<td class="num">{latest:.{dec}f}</td>'
                f'<td class="room">{health_bar(room, "neutral", big=False)}'
                f'<span>{round(room * 100)}%</span></td>'
                f'<td class="num">{len(hits)}</td><td class="num">{first}</td></tr>')
        table = ('<table class="numbers"><thead><tr><th>Chart</th><th>Baseline mean</th><th>Limits</th>'
                 "<th>Latest</th><th>Room left</th><th>Signals after baseline</th><th>First signal</th>"
                 f"</tr></thead><tbody>{''.join(rows)}</tbody></table>")
        return ui.HTML(f'<div class="scroll-x">{table}</div>')

    # ---------- Part reliability tab ----------
    @reactive.calc
    def components() -> pd.DataFrame:
        return qc.check_components(pd.read_csv(DATA / input.dataset() / "components.csv"))

    @reactive.calc
    def by_type() -> pd.DataFrame:
        return qc.fit_by_type(components())

    @render.ui
    def rel_cards():
        cards = []
        for r in by_type().itertuples():
            name = charts.PART_TITLE.get(r.component_type, r.component_type)
            if r.note:
                cards.append(ui.div(ui.h3(name), ui.p(f"Not enough failures to fit: {r.note}."),
                                    class_="info-card"))
                continue
            if r.beta_lo > 1:
                shape = "Wear-out (β > 1): the older the part, the likelier it fails, so replacing it early prevents failures."
            elif r.beta_hi < 1:
                shape = "Early failures (β < 1): weak parts fail young; better incoming checks help more than early replacement."
            else:
                shape = "No clear wear-out (the interval for β includes 1): failures look random in age."
            cards.append(ui.div(
                ui.div(ui.h3(name), ui.span(f"{r.n_failed} failed of {r.n}", class_="tag"), class_="card-head"),
                ui.div(ui.span("Replace at", class_="rc-label"),
                       ui.span(f"{r.b10:.0f}", class_="rc-value"), ui.span(r.unit, class_="rc-unit"),
                       class_="rc-main"),
                ui.p(f"10% of {name.lower()} fail by {r.b10:.0f} {r.unit} (B10). Typical life η = {r.eta:.0f} "
                     f"(95% interval {r.eta_lo:.0f}–{r.eta_hi:.0f}); mean life {r.mean_life:.0f}."),
                ui.p(f"Shape β = {r.beta:.2f} ({r.beta_lo:.2f}–{r.beta_hi:.2f}). {shape}", class_="muted-p"),
                class_="info-card rel-card"))
        return ui.div(*cards, class_="grid-3 mb-3")

    @render.plot
    def rel_curves():
        c = components()
        curves = []
        for r in by_type().dropna(subset=["eta"]).itertuples():
            part = c[c["component_type"] == r.component_type]
            t = np.linspace(0, part["life_value"].max() * 1.1, 200)
            curves.append(dict(type=r.component_type, unit=r.unit, t=t, r=qc.reliability(t, r.beta, r.eta),
                               km=qc.km_curve(part["life_value"], part["status"]),
                               b10=r.b10, beta=r.beta, eta=r.eta))
        if not curves:
            return None
        return charts.reliability_figure(curves)

    @reactive.calc
    def lots() -> pd.DataFrame:
        try:
            return qc.compare_lots(components(), "battery")
        except ValueError:
            return pd.DataFrame()

    @render.ui
    def lot_sentence():
        lt = lots().dropna(subset=["eta"]) if len(lots()) else lots()
        if len(lt) < 2:
            return ui.p("Fewer than two battery lots have enough failures to compare.", class_="rule-note")
        worst, best = lt.loc[lt["eta"].idxmin()], lt.loc[lt["eta"].idxmax()]
        if worst["eta_hi"] < best["eta_lo"]:
            msg = (f"<b>Lot {escape(str(worst['lot']))} batteries wear out sooner.</b> Their typical life is "
                   f"{worst['eta']:.0f} charge cycles (95% interval {worst['eta_lo']:.0f}–{worst['eta_hi']:.0f}), "
                   f"against {best['eta']:.0f} for lot {escape(str(best['lot']))}. The intervals don't overlap, so "
                   "this is a real difference, not chance: check the supplier and replace those batteries first.")
            cls = "banner ground"
        else:
            msg = ("<b>No battery lot stands out.</b> Every lot's 95% interval overlaps the others, so the "
                   "differences are within chance.")
            cls = "banner go"
        return ui.div(ui.HTML(f"<p>{msg}</p>"), class_=cls)

    @render.plot
    def lot_plot():
        lt = lots()
        if lt.empty or lt["eta"].isna().all():
            return None
        return charts.lots_figure(lt, "charge cycles")

    @render.ui
    def due_table():
        due = qc.parts_past_b10(components(), by_type())
        if due.empty:
            return ui.p("No part still in service is past its B10 life.", class_="rule-note")
        def table(df):
            rows = "".join(
                f"<tr><td><strong>{escape(r.component_id)}</strong></td><td>{escape(r.drone_id)}</td>"
                f"<td>{escape(r.component_type)}</td><td>{escape(str(r.lot))}</td>"
                f'<td class="num">{r.life_value:g} {qc.LIFE_UNIT.get(r.component_type, "")}</td>'
                f'<td class="num">{r.b10:.0f}</td><td class="num">{r.pct_of_b10:.0f}%</td></tr>'
                for r in df.itertuples())
            return ('<div class="scroll-x"><table class="numbers"><thead><tr><th>Part</th><th>Drone</th>'
                    "<th>Type</th><th>Batch</th><th>Age now</th><th>B10 life</th><th>Age as % of B10</th>"
                    f"</tr></thead><tbody>{rows}</tbody></table></div>")

        counts = due["component_type"].value_counts()
        summary = ", ".join(f"{n} {t}{'s' if n != 1 else ''}" for t, n in counts.items())
        top, rest = due.head(10), due.iloc[10:]
        more = (f"<details class='more'><summary>Show the other {len(rest)} parts</summary>{table(rest)}</details>"
                if len(rest) else "")
        return ui.div(
            ui.HTML(f'<p class="due-summary"><b>{len(due)} parts still flying are past their B10 age</b> '
                    f"({summary}). Most overdue first:</p>"),
            ui.HTML(table(top) + more),
            ui.p("B10 = the age by which 10% of that kind of part fail. This fleet runs parts until they "
                 "break, so many are well past it: replacing at B10 would prevent most in-flight failures.",
                 class_="rule-note"))

    @render.plot
    def drone_charts():
        data = drone_charts_data()
        if not data:
            return None
        panels = []
        for kind, ch, flight_no, title, unit, _ in data:
            label = f"{title}: EWMA (slow wear)" if kind == "ewma" else f"{title}: each flight"
            panels.append((kind, ch, flight_no, label, unit))
        return charts.drone_figure(panels)


app = App(app_ui, server)
