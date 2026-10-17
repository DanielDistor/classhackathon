import { useCallback, useEffect, useState } from 'react'
import useApi from './useApi.js'
import { getFleet, getRuns, uploadLogbook } from './api.js'
import FleetTab from './components/FleetTab.jsx'
import ReliabilityTab from './components/ReliabilityTab.jsx'
import DroneModal from './components/DroneModal.jsx'
import Guide from './components/Guide.jsx'
import RetireControl from './components/RetireControl.jsx'
import CostTab from './components/CostTab.jsx'
import { UploadBar } from './components/UploadTab.jsx'
import CombinedTab from './components/CombinedTab.jsx'
import AboutTab from './components/AboutTab.jsx'
import { Failed, Loading } from './components/common.jsx'

const TABS = [['fleet', 'Fleet health & replacements'], ['weibull', 'Weibull reliability & replace-at ages'],
  ['cost', 'Cost & savings']]

// The page lives in the URL hash (#guide, #weibull, #fleet/D-05, #combined/U01) so Back works and links can be shared.
function readHash() {
  const [page, drone] = window.location.hash.replace(/^#/, '').split('/')
  const tab = ['weibull', 'cost', 'combined', 'about'].includes(page) ? page : 'fleet'
  return { page: page === 'guide' ? 'guide' : 'dashboard', tab, drone: drone || null }
}

export default function App() {
  const [view, setView] = useState(readHash)
  const [retire, setRetire] = useState(10)
  const [dataset, setDataset] = useState('fleet')
  // An uploaded logbook is combined with Fleet A and Fleet B (POST /api/upload) and shown on its own
  // Combined tab; the other tabs keep showing the test fleets.
  const [upload, setUpload] = useState({ busy: false, error: null, info: null })
  const onUpload = async (file) => {
    setUpload((u) => ({ ...u, busy: true, error: null }))
    try {
      const info = await uploadLogbook(file)
      setUpload({ busy: false, error: null, info })
      window.location.hash = 'combined'
    } catch (error) {
      setUpload((u) => ({ ...u, busy: false, error }))
    }
  }
  const resetUpload = () => { setUpload({ busy: false, error: null, info: null }); window.location.hash = 'fleet' }
  const combined = upload.info
  const onCombined = view.tab === 'combined' && combined
  const tabs = [...TABS, ...(combined ? [['combined', `Combined (${combined.n_drones} drones)`]] : []), ['about', 'About']]
  const runs = useApi(() => getRuns(dataset), `runs-${dataset}`)
  const fleet = useApi(() => getFleet(retire, dataset), `fleet-${dataset}-${retire}`)

  useEffect(() => {
    const onHash = () => setView(readHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])
  const go = (hash) => { window.location.hash = hash }
  const closeDrone = useCallback(() => { window.location.hash = window.location.hash.startsWith('#combined') ? 'combined' : 'fleet' }, [])

  if (view.page === 'guide') {
    return <Guide dataset={dataset} onEnter={() => { go('fleet'); window.scrollTo(0, 0) }} />
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
        <UploadBar upload={upload} onFile={onUpload} onReset={resetUpload} />
        {!onCombined && <div className="controls">
          {runs.data && <RetireControl runs={runs.data} retire={retire} onChange={setRetire}
                                       dataset={dataset} onDataset={setDataset} />}
          {runs.error && <Failed error={runs.error} />}
        </div>}
        <nav className="nav nav-pills" role="tablist">
          {tabs.map(([id, label]) => (
            <button key={id} role="tab" aria-selected={view.tab === id}
                    className={`nav-link${view.tab === id ? ' active' : ''}`} onClick={() => go(id)}>{label}</button>
          ))}
        </nav>
        {view.tab === 'fleet' && (fleet.error ? <Failed error={fleet.error} />
          : fleet.data ? <FleetTab d={fleet.data} onOpen={(id) => go(`fleet/${id}`)} /> : <Loading what="the fleet" />)}
        {view.tab === 'weibull' && <ReliabilityTab retire={retire} dataset={dataset} />}
        {view.tab === 'cost' && <CostTab retire={retire} dataset={dataset} />}
        {onCombined && <CombinedTab info={combined} onOpen={(id) => go(`combined/${id}`)} />}
        {view.tab === 'combined' && !combined && <Failed error={new Error('Upload a logbook first: the Combined tab appears after an upload.')} />}
        {view.tab === 'about' && <AboutTab />}
      </div>
      {view.drone && <DroneModal droneId={view.drone} retire={onCombined ? 10 : retire}
                                 dataset={onCombined ? combined.dataset : dataset} onClose={closeDrone} />}
    </div>
  )
}
