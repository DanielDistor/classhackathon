// The ONLY place the API address lives. By default the dashboard calls the same
// server that served it (app/api.py serves both), so nothing needs configuring.
// To point a dev build at another API, set VITE_API_URL in web/.env.local.
export const API_URL = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')

async function getJson(path) {
  const res = await fetch(`${API_URL}${path}`)
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try { detail = (await res.json()).detail || detail } catch { /* not JSON */ }
    throw new Error(`${path}: ${detail}`)
  }
  return res.json()
}

// Relative paths ("api/...", no leading slash) so it also works under a Posit
// Connect content path like /content/<guid>/.
// ds = the test dataset (fleet = Fleet A, fleet_b = Fleet B); retire = the retirement setting p:
// parts retire at B_p (one precomputed run each).
export const getRuns = (ds) => getJson(`api/runs?dataset=${ds}`)
export const getFleet = (retire, ds) => getJson(`api/fleet?retire=${retire}&dataset=${ds}`)
export const getDrone = (id, retire, ds) => getJson(`api/drones/${encodeURIComponent(id)}?retire=${retire}&dataset=${ds}`)
export const getReliability = (retire, ds) => getJson(`api/reliability?retire=${retire}&dataset=${ds}`)
export const getGuide = (ds) => getJson(`api/guide?dataset=${ds}`)
// costs = { motor: [planned, failure], propeller: [...], battery: [...] } in dollars
export const getCost = (ds, costs) => getJson(`api/cost?dataset=${ds}&` + Object.entries(costs)
  .map(([t, [cp, cf]]) => `cp_${t}=${cp}&cf_${t}=${cf}`).join('&'))
