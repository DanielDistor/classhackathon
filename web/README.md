# web/: the React dashboard

The front end of the Drone Fleet Health & Part Wear Monitor: Vite + React, with charts drawn by hand
as SVG (no chart library) and the original stylesheet. It has **no statistics**: every number comes from
the FastAPI app in [`../app/api.py`](../app/api.py), which calls the tested functions in
[`../app/qc.py`](../app/qc.py). Started from [`demos/reactfront/`](../demos/reactfront/).

## Run it

From the repo folder: `./run.sh`, then open http://127.0.0.1:8000. After you edit anything here, run
`./run.sh` again: it notices the change and rebuilds. Commit everything git shows as changed (the build
lands in `app/static/`, which Posit Connect serves). Needs Node.js 20+ only if you edit this folder.

Optional, for live reload while editing: `npm run dev` here (http://localhost:5173), with `./run.sh`
running in another terminal for the API. `npm test` runs the formatting and chart-scale tests.

## Files

| File | What it shows |
|---|---|
| `src/App.jsx` | The page: header, the two tabs, and the drone pop-up. The view lives in the URL hash (`#fleet`, `#weibull`, `#guide`, `#fleet/D-05`), so Back works and a drone can be linked |
| `src/components/FleetTab.jsx` | Status counts, Due soon, the 10 drone cards, the fleet timeline |
| `src/components/DroneModal.jsx` | One drone: status, timeline, parts, the three control charts and how to read them |
| `src/components/ReliabilityTab.jsx` | Replace-at ages, Weibull vs Kaplan-Meier curves, the fit table, every drone's schedule |
| `src/components/Guide.jsx` | The guide & data reference page (edit the wording here) |
| `src/charts/` | `MonitorChart.jsx` (control chart), `Timeline.jsx` (R / F / S), `ReliabilityChart.jsx`, `scale.js` |
| `src/api.js` | The only place the API address lives (same server by default; `VITE_API_URL` overrides) |
| `src/format.js` | Status words and colours, "in 12 flights", number formatting |
| `src/styles.css`, `src/base.css` | The look (carried over from the Shiny version) and the React-only pieces |
