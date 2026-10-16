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

import pandas as pd
from shiny import App, reactive, render, ui
from shiny.types import SafeException

import charts
import qc
from intro import intro_page

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"  # a copy of the repo's data/ folder; manifestme.sh refreshes it
DATASETS = {
    "healthy": "Version 1 · A normal month",
    "motor_drift": "Version 2 · A motor wears out",
    "bad_battery_lot": "Version 3 · A bad battery batch",
}
STATUS_ORDER = {"ground": 0, "watch": 1, "not enough data": 2, "go": 3}
STATUS_CLASS = {"ground": "ground", "watch": "watch", "go": "go", "not enough data": "na",
                "neutral": "neutral"}
STATUS_WORD = {"ground": "Ground", "watch": "Watch", "go": "Go", "not enough data": "Not enough data"}

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


def pct_text(health: float) -> str:
    return "–" if isinstance(health, float) and math.isnan(health) else f"{round(health * 100)}%"


controls = ui.div(
    ui.div(ui.input_select("dataset", "Dataset", DATASETS), class_="ctl"),
    ui.div(ui.input_file("upload", "Or upload your own flights.csv", accept=[".csv"],
                         button_label="Choose file"), class_="ctl"),
    ui.div(ui.input_select("drone", "Drone", []), class_="ctl ctl-narrow"),
    class_="controls",
)

dashboard = ui.div(
    CLICK_JS,
    ui.div(
        ui.div(ui.span("Drone Fleet Reliability Monitor", class_="title"),
               ui.span("go / watch / ground before every flight", class_="subtitle")),
        ui.input_action_link("about", "About this tool and the datasets"),
        class_="topbar",
    ),
    ui.div(
        controls,
        ui.navset_pill(
            ui.nav_panel(
                "Fleet health",
                ui.div(ui.output_ui("fleet_kpis"), ui.output_ui("fleet_health"), class_="pt-3"),
            ),
            ui.nav_panel(
                "Drone detail",
                ui.div(
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
                ui.div(ui.h3("Coming in Stage 4"),
                       ui.p("Weibull life curves for motors, propellers and batteries, B10 life, "
                            "replacement intervals, and the battery lot comparison."),
                       class_="coming"),
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
        upload = input.upload()
        if upload:
            try:
                f = pd.read_csv(upload[0]["datapath"])
                qc.check_flights(f)
            except (ValueError, pd.errors.ParserError) as err:
                raise SafeException(f"Can't use that file: {err}") from None
        else:
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

    # ---------- Fleet health tab ----------
    @render.ui
    def fleet_kpis():
        counts = status()["status"].value_counts()
        hints = {"ground": "inspect or repair before the next flight",
                 "watch": "a signal in the last 10 flights",
                 "go": "every chart in control"}
        return ui.div(*[ui.div(ui.div(STATUS_WORD[s], class_="label"),
                               ui.div(str(int(counts.get(s, 0))), class_="value"),
                               ui.div(hints[s], class_="hint"), class_=f"kpi {s}")
                        for s in ("ground", "watch", "go")], class_="kpis")

    @render.ui
    def fleet_health():
        rows = []
        for r in status().itertuples():
            driver = ("crashed on its last flight" if r.health_driver == "crash"
                      else f"closest to a limit: {r.health_driver}" if r.health_driver else "")
            rows.append(
                f'<button class="drone-row" data-drone="{escape(r.drone_id)}" '
                f'aria-label="Open {escape(r.drone_id)}">'
                f'<div class="dr-id">{escape(r.drone_id)}</div>'
                f'<div class="dr-status">{pill(r.status)}</div>'
                f'<div class="dr-bar">{health_bar(r.health, r.status)}'
                f'<div class="dr-why">{escape(r.reason)}</div></div>'
                f'<div class="dr-pct">{pct_text(r.health)}<span>{escape(driver)}</span></div>'
                f'<div class="dr-go">›</div></button>')
        legend = ("<b>Health</b> = how much room is left before the nearest control limit, on the drone's "
                  "most-stretched chart. 100% = right at its normal; 0% = at a limit, or crashed. "
                  "The colour is the status: Ground = latest reading outside a limit, EWMA outside its limit "
                  "now, or a crash · Watch = a signal in the last 10 flights · Go = every chart in control. "
                  "Click a drone to see its charts.")
        return ui.div(ui.HTML(f'<div class="drone-list">{"".join(rows)}</div>'),
                      ui.HTML(f'<p class="rule-note">{legend}</p>'), class_="panel")

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
            ui.p(row["reason"][0].upper() + row["reason"][1:] + "."),
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
