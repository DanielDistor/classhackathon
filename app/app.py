"""Drone fleet reliability dashboard (Shiny for Python).

For the fleet maintenance technician: before each flight, which drones are
go, watch or ground, and why. Every statistic comes from qc.py; this file only
loads data, calls qc.py and shows the result. The welcome page lives in
intro.py and the look in styles.css.

Run locally:  ./testme.sh   (or: shiny run app.py, from this folder)
"""

from __future__ import annotations

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
    "healthy": "Healthy fleet",
    "motor_drift": "Motor drift + prop strike",
    "bad_battery_lot": "Bad battery lot",
}
STATUS_ORDER = {"ground": 0, "watch": 1, "not enough data": 2, "go": 3}
STATUS_CLASS = {"ground": "ground", "watch": "watch", "go": "go", "not enough data": "na"}
STATUS_WORD = {"ground": "Ground", "watch": "Watch", "go": "Go", "not enough data": "Not enough data"}

# (column, chart title, units, decimals, EWMA too?)
DRONE_CHARTS = [
    ("temp_rise_c", "Motor temperature rise", "°C", 1, True),
    ("vibration_rms", "Vibration", "m/s²", 2, False),
    ("sag_rate_v_per_min", "Battery voltage sag per minute", "V/min", 3, False),
]


def pill(status: str) -> str:
    return f'<span class="pill {STATUS_CLASS[status]}">{STATUS_WORD[status]}</span>'


dashboard = ui.div(
    ui.div(
        ui.div(ui.span("Drone Fleet Reliability Monitor", class_="title"),
               ui.span("go / watch / ground before every flight", class_="subtitle")),
        ui.input_action_link("about", "About this tool and the datasets"),
        class_="topbar",
    ),
    ui.div(
        ui.layout_sidebar(
            ui.sidebar(
                ui.input_select("dataset", "Test dataset", DATASETS),
                ui.input_file("upload", "Or upload your own flights.csv", accept=[".csv"],
                              button_label="Choose file"),
                ui.input_select("drone", "Drone", []),
                ui.p("Limits come from each drone's own first 30 flights. Column names and units: "
                     "data/README.md in the repo.", class_="sidebar-note"),
                width=290, open="always",
            ),
            ui.navset_tab(
                ui.nav_panel(
                    "Fleet",
                    ui.div(ui.output_ui("fleet_kpis"), ui.output_ui("fleet_table"), class_="pt-3"),
                ),
                ui.nav_panel(
                    "Drone",
                    ui.div(
                        ui.output_ui("drone_banner"),
                        ui.div(ui.h4("The numbers behind the charts"), ui.output_ui("drone_numbers"),
                               class_="panel"),
                        ui.div(ui.output_plot("drone_charts", height="1250px"), class_="panel"),
                        ui.div(
                            ui.h4("How to read these charts"),
                            ui.div(ui.markdown(
                                "The shaded band is the drone's first 30 flights, its **baseline**. The dashed "
                                "**limits** are the baseline mean ± 3σ̂, where σ̂ = average moving range ÷ 1.128. "
                                "A red ✕ is a **signal**: a reading the drone's own normal variation is very "
                                "unlikely to produce.\n\n"
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
                    "Reliability",
                    ui.div(ui.h3("Coming in Stage 4"),
                           ui.p("Weibull life curves for motors, propellers and batteries, B10 life, "
                                "replacement intervals, and the battery lot comparison."),
                           class_="coming"),
                ),
                id="tabs",
            ),
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
        return st.sort_values(by=["status", "drone_id"], key=lambda c: c.map(STATUS_ORDER)
                              if c.name == "status" else c).reset_index(drop=True)

    @reactive.effect
    def _drones():
        st = status()
        drones = sorted(st["drone_id"])
        ui.update_select("drone", choices=drones, selected=st["drone_id"].iloc[0] if len(st) else None)

    # ---------- Fleet tab ----------
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
    def fleet_table():
        rows = "".join(
            f"<tr><td><strong>{escape(r.drone_id)}</strong></td><td>{pill(r.status)}</td>"
            f'<td class="why">{escape(r.reason)}</td><td class="num">{r.last_flight_no}</td>'
            f'<td class="num">{r.n_flights}</td></tr>'
            for r in status().itertuples())
        table = ('<table class="fleet"><thead><tr><th>Drone</th><th>Status</th><th>Why</th>'
                 f"<th>Last flight</th><th>Flights logged</th></tr></thead><tbody>{rows}</tbody></table>")
        return ui.div(
            ui.HTML(table),
            ui.p("Ground = latest reading outside a limit, EWMA outside its limit now, or a crash · "
                 "Watch = a signal in the last 10 flights · Go = every chart in control. "
                 "Pick a drone in the sidebar, then open the Drone tab to see why.", class_="rule-note"),
            class_="panel")

    # ---------- Drone tab ----------
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
        return ui.div(ui.h3(f"{drone} · {STATUS_WORD[row['status']]}"), ui.p(row["reason"] + "."),
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
            hits = flight_no.reset_index(drop=True)[(sig & ~ch["baseline"]).to_numpy()]
            first = f"flight {hits.iloc[0]}" if len(hits) else "none"
            name = f"{title} · {'EWMA' if kind == 'ewma' else 'I chart'}"
            limit_note = " (settled)" if kind == "ewma" else ""
            rows.append(
                f"<tr><td>{escape(name)}</td>"
                f'<td class="num">{ch["center"].iloc[0]:.{dec}f} {unit}</td>'
                f'<td class="num">{ch["lcl"].iloc[-1]:.{dec}f} to {ch["ucl"].iloc[-1]:.{dec}f}{limit_note}</td>'
                f'<td class="num">{latest:.{dec}f}</td>'
                f'<td class="num">{len(hits)}</td><td class="num">{first}</td></tr>')
        table = ('<table class="numbers"><thead><tr><th>Chart</th><th>Baseline mean</th><th>Limits</th>'
                 "<th>Latest</th><th>Signals after baseline</th><th>First signal</th></tr></thead>"
                 f"<tbody>{''.join(rows)}</tbody></table>")
        return ui.HTML(table)

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
