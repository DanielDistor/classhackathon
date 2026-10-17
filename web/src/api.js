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
export const getFleet = () => getJson('api/fleet')
export const getDrone = (id) => getJson(`api/drones/${encodeURIComponent(id)}`)
export const getReliability = () => getJson('api/reliability')
export const getGuide = () => getJson('api/guide')
