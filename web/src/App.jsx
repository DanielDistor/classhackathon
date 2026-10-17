import { useCallback, useEffect, useState } from 'react'
import useApi from './useApi.js'
import { getFleet } from './api.js'
import FleetTab from './components/FleetTab.jsx'
import ReliabilityTab from './components/ReliabilityTab.jsx'
import DroneModal from './components/DroneModal.jsx'
import Guide from './components/Guide.jsx'
import { Failed, Loading } from './components/common.jsx'

const TABS = [['fleet', 'Fleet health & replacements'], ['weibull', 'Weibull reliability & replace-at ages']]

// The page lives in the URL hash (#guide, #weibull, #fleet/D-05) so Back works and links can be shared.
function readHash() {
  const [page, drone] = window.location.hash.replace(/^#/, '').split('/')
  return { page: page === 'guide' ? 'guide' : 'dashboard', tab: page === 'weibull' ? 'weibull' : 'fleet', drone: drone || null }
}

export default function App() {
  const [view, setView] = useState(readHash)
  const fleet = useApi(getFleet, 'fleet')

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
          <span className="subtitle">Control charts with all 8 rules + Weibull replace-at ages, with every replacement logged</span>
        </div>
        <button className="btn-back" onClick={() => { go('guide'); window.scrollTo(0, 0) }}>Guide &amp; Data Reference</button>
      </div>
      <div className="dash">
        <div className="controls">
          <div className="ctl-head">
            <span className="ctl-title">Active fleet</span>
            <span className="ctl-sub">10 drones × 300 flights, Jul 1 – Sep 29, 2026 (simulated test data, data/fleet). Click
              any drone card for its timeline, parts and control charts.</span>
          </div>
        </div>
        <nav className="nav nav-pills" role="tablist">
          {TABS.map(([id, label]) => (
            <button key={id} role="tab" aria-selected={view.tab === id}
                    className={`nav-link${view.tab === id ? ' active' : ''}`} onClick={() => go(id)}>{label}</button>
          ))}
        </nav>
        {view.tab === 'fleet' && (fleet.error ? <Failed error={fleet.error} />
          : fleet.data ? <FleetTab d={fleet.data} onOpen={(id) => go(`fleet/${id}`)} /> : <Loading what="the fleet" />)}
        {view.tab === 'weibull' && <ReliabilityTab />}
      </div>
      {view.drone && <DroneModal droneId={view.drone} onClose={closeDrone} />}
    </div>
  )
}
