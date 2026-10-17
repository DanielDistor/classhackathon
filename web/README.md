# web/: the React dashboard

The front end of the Drone Fleet Health & Part Wear Monitor: Vite + React, with charts drawn by hand
as SVG (no chart library) and the original stylesheet. It has **no statistics**: every number comes from
the FastAPI app in [`../app/api.py`](../app/api.py), which calls the tested functions in
[`../app/qc.py`](../app/qc.py). Started from [`demos/reactfront/`](../demos/reactfront/).

## Run it

You need Node.js 20 or newer.

```bash
cd web
npm ci             # install the exact versions in package-lock.json
npm run dev        # http://localhost:5173, live reload; /api calls go to the API on port 8000
```

Start the API first in another terminal (`cd app && ./testme.sh`). `npm run dev` proxies `/api` to it.

## Build and test

```bash
npm run build      # writes ../app/static/, which the API serves at http://127.0.0.1:8000/
npm test           # number formatting and chart-scale tests
```

Commit `../app/static/` after building, then re-run `../app/manifestme.sh`: Posit Connect serves the
build from there. Never commit `node_modules/`.

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
