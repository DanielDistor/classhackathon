import { useCallback, useEffect, useState } from 'react'
import useApi from './useApi.js'
import { getFleet, getRuns } from './api.js'
import FleetTab from './components/FleetTab.jsx'
import ReliabilityTab from './components/ReliabilityTab.jsx'
import DroneModal from './components/DroneModal.jsx'
import Guide from './components/Guide.jsx'
import RetireControl from './components/RetireControl.jsx'
import { Failed, Loading } from './components/common.jsx'

const TABS = [['fleet', 'Fleet health & replacements'], ['weibull', 'Weibull reliability & replace-at ages']]

// The page lives in the URL hash (#guide, #weibull, #fleet/D-05) so Back works and links can be shared.
function readHash() {
  const [page, drone] = window.location.hash.replace(/^#/, '').split('/')
  return { page: page === 'guide' ? 'guide' : 'dashboard', tab: page === 'weibull' ? 'weibull' : 'fleet', drone: drone || null }
}

export default function App() {
  const [view, setView] = useState(readHash)
  const [retire, setRetire] = useState(10)
  const runs = useApi(getRuns, 'runs')
  const fleet = useApi(() => getFleet(retire), `fleet-${retire}`)

  useEffect(() => {
    const onHash = () => setView(readHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])
  const go = (hash) => { window.location.hash = hash }
  const closeDrone = useCallback(() => { window.location.hash = 'fleet' }, [])

  if (view.page === 'guide') {
    return <Guide onEnter={() => { go('fleet'); window.scrollTo(0, 0) }} />
  }
  return (
    <div>
      <div className="topbar">
        <div className="topbar-left">
          <span className="title">Drone Fleet Health &amp; Part Wear Monitor</span>
          <span className="subtitle">10 drones × 300 flights (simulated, Jul–Sep 2026) · click a drone for its details</span>
        </div>
        <button className="btn-back" onClick={() => { go('guide'); window.scrollTo(0, 0) }}>Guide &amp; Data Reference</button>
      </div>
      <div className="dash">
        <div className="controls">
          {runs.data && <RetireControl runs={runs.data} retire={retire} onChange={setRetire} />}
          {runs.error && <Failed error={runs.error} />}
        </div>
        <nav className="nav nav-pills" role="tablist">
          {TABS.map(([id, label]) => (
            <button key={id} role="tab" aria-selected={view.tab === id}
                    className={`nav-link${view.tab === id ? ' active' : ''}`} onClick={() => go(id)}>{label}</button>
          ))}
        </nav>
        {view.tab === 'fleet' && (fleet.error ? <Failed error={fleet.error} />
          : fleet.data ? <FleetTab d={fleet.data} onOpen={(id) => go(`fleet/${id}`)} /> : <Loading what="the fleet" />)}
        {view.tab === 'weibull' && <ReliabilityTab retire={retire} />}
      </div>
      {view.drone && <DroneModal droneId={view.drone} retire={retire} onClose={closeDrone} />}
    </div>
  )
}
