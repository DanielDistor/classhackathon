import { useRef, useState } from 'react'
import MonitorChart, { MonitorLegend } from '../charts/MonitorChart.jsx'
import { LifeBar, Panel, Pill, Used } from './common.jsx'
import { PART_NAME, PART_TITLE, STATUS_WORD, cap, flightsPhrase, fmt } from '../format.js'

const ORDER = { ground: 0, watch: 1, 'not enough data': 2, go: 3 }

// The words qc.fleet_status uses for each reading in its reason.
const REASON_NAME = { temp_rise_c: 'motor temperature rise', vibration_rms: 'vibration', sag_rate_v_per_min: 'voltage sag' }

/** The chart to open first: the reading the status reason names first, else the first chart. */
function worstChart(charts, reason) {
  let best = 0
  let at = Infinity
  charts.forEach((c, i) => {
    const k = reason.indexOf(REASON_NAME[c.column])
    if (k >= 0 && k < at) { at = k; best = i }
  })
  return best
}

/** The upload box, at the top of every dashboard tab. `upload` = { busy, error, data }. */
export function UploadBar({ upload, onFile, onClose }) {
  const input = useRef(null)
  const choose = (e) => {
    const file = e.target.files?.[0]
    if (file) onFile(file)
    e.target.value = ''
  }
  return (
    <div className="panel upload-bar">
      <div className="upload-row">
        <span className="upload-title">Check your own logbook</span>
        <button type="button" className="upload-btn" disabled={upload.busy} onClick={() => input.current?.click()}>
          {upload.busy ? 'Checking…' : 'Upload a file'}
        </button>
        <input ref={input} className="upload-input" type="file" onChange={choose} tabIndex={-1} aria-hidden="true"
               accept=".xlsx,.xlsm,.csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv" />
        <a className="upload-example" href="./example_logbook.xlsx" download>Download the example workbook</a>
        {upload.data && <button type="button" className="upload-close" onClick={onClose}>Close the results ×</button>}
      </div>
      <p className="rule-note upload-intro">An Excel workbook with a <b>flights</b> sheet (optional <b>maintenance</b> and <b>components</b>{' '}
        sheets), or a flights CSV, with the same columns as the test data. Nothing is stored.</p>
      {upload.error && <div className="upload-error">Couldn't use that file: {upload.error.message}</div>}
      {upload.data && <UploadTab key={upload.n} data={upload.data} />}
    </div>
  )
}

/** The results of an uploaded logbook: every drone's status, its charts, and the parts. */
export default function UploadTab({ data: d }) {
  const first = d ? [...d.status].sort((a, b) => ORDER[a.status] - ORDER[b.status])[0] : null
  const [drone, setDrone] = useState(first?.drone_id ?? null)
  const [reading, setReading] = useState(first ? worstChart(d.charts[first.drone_id], first.reason) : 0)

  if (!d) return null
  const charts = drone ? d.charts[drone] : null
  const chart = charts?.[reading]
  const due = d.plan.filter((p) => p.due).sort((a, b) => a.flights_left - b.flights_left)

  return (
    <div className="upload-results">
        <>
          <Panel title={`${d.file}: ${d.n_drones} drones, ${d.n_flights} flights`}>
            {d.notes.map((n) => <p key={n} className="rule-note">{n}</p>)}
            <div className="scroll-x">
              <table className="numbers">
                <thead><tr><th>Drone</th><th>Status</th><th>Why</th><th /></tr></thead>
                <tbody>
                  {[...d.status].sort((a, b) => ORDER[a.status] - ORDER[b.status] || a.drone_id.localeCompare(b.drone_id)).map((r) => (
                    <tr key={r.drone_id} className={r.drone_id === drone ? 'row-on' : ''}>
                      <td><b>{r.drone_id}</b></td>
                      <td><Pill status={r.status}>{STATUS_WORD[r.status]}</Pill></td>
                      <td>{cap(r.reason)}.</td>
                      <td><button className="link-btn" onClick={() => { setDrone(r.drone_id); setReading(worstChart(d.charts[r.drone_id], r.reason)) }}>Charts ›</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>

          {charts && (
            <Panel title={`${drone}: control charts`}>
              <div className="chart-controls">
                <select value={reading} onChange={(e) => setReading(Number(e.target.value))} aria-label="Reading to chart">
                  {charts.map((c, i) => <option key={c.column} value={i}>{c.title}</option>)}
                </select>
              </div>
              {chart?.error ? <p className="rule-note">No chart: {chart.error}</p> : (
                <>
                  <MonitorLegend />
                  <MonitorChart chart={chart} last={null} />
                </>
              )}
            </Panel>
          )}

          {d.fits.length > 0 && (
            <Panel title="Parts: Weibull replace-at ages from your parts history">
              <div className="scroll-x">
                <table className="numbers">
                  <thead><tr><th>Part</th><th>Sample</th><th>Shape <span className="greek">β</span> (95% CI)</th><th>Scale <span className="greek">η</span> (95% CI)</th><th>Replace at (B10)</th></tr></thead>
                  <tbody>
                    {d.fits.map((f) => (
                      <tr key={f.component_type}>
                        <td><b>{PART_TITLE[f.component_type]}</b></td>
                        {f.note ? <td colSpan={4} className="muted-cell">{f.note}</td> : (
                          <>
                            <td className="num">{f.n_failed} failed / {f.n}</td>
                            <td className="num">{fmt(f.beta, 2)} ({fmt(f.beta_lo, 2)}–{fmt(f.beta_hi, 2)})</td>
                            <td className="num">{fmt(f.eta)} ({fmt(f.eta_lo)}–{fmt(f.eta_hi)})</td>
                            <td className="num"><b>{fmt(f.b10)}</b> {f.unit}</td>
                          </>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <h4 className="upload-sub">Due within {d.warn_flights} flights</h4>
              {due.length === 0 ? <p className="rule-note">No installed part reaches its replace-at age in the next {d.warn_flights} flights.</p> : (
                <div className="scroll-x">
                  <table className="numbers">
                    <thead><tr><th>Drone</th><th>Part</th><th>Used / replace at</th><th>Life used</th><th>Replace</th></tr></thead>
                    <tbody>
                      {due.map((p) => (
                        <tr key={p.component_id}>
                          <td><b>{p.drone_id}</b></td><td>{PART_NAME[p.component_type]} {p.position}</td>
                          <td className="num"><Used p={p} /></td><LifeBar part={p} /><td className="num">{flightsPhrase(p.flights_left)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Panel>
          )}
        </>
    </div>
  )
}
