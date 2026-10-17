import { useState } from 'react'
import useApi from '../useApi.js'
import { getFleet } from '../api.js'
import FleetTab from './FleetTab.jsx'
import ReliabilityTab from './ReliabilityTab.jsx'
import { Failed, Loading, Panel } from './common.jsx'

const PAGE = 10

/** The combined fleet narrowed to the drones in `ids`, so the cards show 10 at a time. Statuses and
 *  parts are the combined results (replace-at ages fitted on all the parts); only the drones shown
 *  change, and the history line is recounted for them. */
function onlyDrones(d, ids) {
  const keep = new Set(ids)
  const mine = (id) => keep.has(id)
  const timeline = d.timeline.filter((e) => mine(e.drone_id))
  const replaced = timeline.filter((e) => e.marker === 'R')
  const byChart = replaced.filter((e) => String(e.trigger).startsWith('chart')).length
  return {
    ...d,
    status: d.status.filter((r) => mine(r.drone_id)),
    plan: d.plan.filter((p) => mine(p.drone_id)),
    drones: d.drones.filter(mine),
    timeline,
    activity: {
      replaced: replaced.length, at_age: replaced.length - byChart, by_chart: byChart,
      failed: timeline.filter((e) => e.marker === 'F').length, special: timeline.filter((e) => e.marker === 'S').length,
    },
  }
}

/**
 * The Combined tab, shown after an upload: Fleet A, Fleet B and the uploaded logbook as one fleet
 * (POST /api/upload builds it). Drones are renamed by source: A01-A10, B01-B10, U01, ... The cards show
 * one source at a time; the Weibull section underneath uses every part of all three.
 */
export default function CombinedTab({ info, onOpen }) {
  const fleet = useApi(() => getFleet(10, info.dataset), `combined-${info.dataset}`)
  // Pages of 10 drones: the upload first, then Fleet A, then Fleet B.
  const order = [info.sources[info.sources.length - 1], ...info.sources.slice(0, -1)].map((s) => s.prefix)
  const [page, setPage] = useState(0)
  const all = fleet.data
    ? [...fleet.data.drones].sort((a, b) => order.indexOf(a[0]) - order.indexOf(b[0]) || a.localeCompare(b)) : []
  const pages = Math.max(1, Math.ceil(all.length / PAGE))
  const shown = all.slice(page * PAGE, page * PAGE + PAGE)
  const sourceOf = (id) => info.sources.find((s) => id?.startsWith(s.prefix))
  const jump = (prefix) => { const i = all.findIndex((id) => id.startsWith(prefix)); if (i >= 0) setPage(Math.floor(i / PAGE)) }
  const onPage = new Set(shown.map((id) => id[0]))
  return (
    <div className="pt-3">
      <Panel title={`Combined fleet: ${info.n_drones} drones, ${info.n_flights.toLocaleString('en-US')} flights`}>
        <p className="combined-intro">
          {info.sources.map((s, i) => (
            <span key={s.prefix}>{i ? ' + ' : ''}<b>{s.name}</b> ({s.prefix}01–{s.prefix}{String(s.n_drones).padStart(2, '0')})</span>
          ))}
          . Each part type's replace-at age is the B10 fitted on all the parts of all three, and each reading's
          normal range comes from every drone's first 20 flights.
        </p>
        <div className="combined-pick" aria-label="Drones to show">
          <button type="button" className="combined-step" disabled={page === 0} onClick={() => setPage(page - 1)}>← Previous 10</button>
          <span className="combined-count">
            Drones {all.length ? page * PAGE + 1 : 0}–{page * PAGE + shown.length} of {all.length}
            {shown.length > 0 && <> · {sourceOf(shown[0])?.name}</>}
          </span>
          <button type="button" className="combined-step" disabled={page >= pages - 1} onClick={() => setPage(page + 1)}>Next 10 →</button>
          <span className="combined-jump">Jump to:</span>
          {order.map((prefix) => {
            const s = info.sources.find((x) => x.prefix === prefix)
            return (
              <button key={prefix} type="button" className={`combined-btn${onPage.has(prefix) ? ' on' : ''}`}
                      onClick={() => jump(prefix)}>{s.name}</button>
            )
          })}
        </div>
      </Panel>
      {fleet.error ? <Failed error={fleet.error} />
        : fleet.data ? <FleetTab d={onlyDrones(fleet.data, shown)} onOpen={onOpen} />
          : <Loading what="the combined fleet" />}
      <h3 className="combined-sub">Weibull reliability on the combined parts (all {info.n_drones} drones)</h3>
      <ReliabilityTab retire={10} dataset={info.dataset} />
    </div>
  )
}
