import { COLORS as C } from '../charts/scale.js'
import { fmt } from '../format.js'

/** One small bar chart: a count per retirement setting, the chosen one highlighted. Click a bar to pick it. */
function Bars({ title, rows, field, retire, onPick }) {
  const W = 260
  const H = 92
  const M = { top: 8, bottom: 18, left: 4, right: 4 }
  const max = Math.max(1, ...rows.map((r) => r[field]))
  const bw = (W - M.left - M.right) / rows.length
  return (
    <figure className="tradeoff">
      <figcaption>{title}</figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${title} per retirement setting`}>
        {rows.map((r, i) => {
          const h = (r[field] / max) * (H - M.top - M.bottom)
          const x = M.left + i * bw
          const on = r.retire_pct === retire
          return (
            <g key={r.retire_pct} onClick={() => onPick(r.retire_pct)} className="tradeoff-bar">
              <rect x={x} y={M.top} width={bw} height={H - M.top - M.bottom} fill="transparent" />
              <rect x={x + 3} y={H - M.bottom - h} width={bw - 6} height={Math.max(h, 1)} rx={3}
                    fill={on ? C.series : C.grid} />
              <text x={x + bw / 2} y={H - M.bottom - h - 3} textAnchor="middle" className="tick tiny">{r[field]}</text>
              <text x={x + bw / 2} y={H - 4} textAnchor="middle" className={`tick tiny${on ? ' on' : ''}`}>{r.retire_pct}%</text>
            </g>
          )
        })}
      </svg>
    </figure>
  )
}

/**
 * The retirement slider: parts retire at B_p, the age by which p% of that part type fails.
 * Each setting is a precomputed run of the same fleet (same part lifetimes and problems).
 */
export default function RetireControl({ runs, retire, onChange, dataset, onDataset }) {
  const options = runs.options
  const idx = Math.max(0, options.indexOf(retire))
  // warned and replaced = at the replace-at age + caught worn (the R markers; special-cause swaps are S)
  const rows = runs.summary.map((r) => ({ ...r, warned: r.at_replace_age + r.found_worn }))
  const row = rows.find((r) => r.retire_pct === retire) || {}
  const failed = rows.reduce((n, r) => n + r.failed_in_flight, 0)
  return (
    <div className="retire">
      <div className="retire-left">
        <div className="chart-controls">
          <select value={dataset} onChange={(e) => onDataset(e.target.value)} aria-label="Test dataset">
            {runs.datasets.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
          <label className="ctl-title" htmlFor="retire">Retire parts at B{retire}</label>
        </div>
        <input id="retire" type="range" min={0} max={options.length - 1} step={1} value={idx}
               onChange={(e) => onChange(options[Number(e.target.value)])} />
        <div className="retire-ticks">{options.map((p) => <span key={p}>{p}%</span>)}</div>
        <p className="ctl-sub">
          Replace a part when {retire}% of its type would have failed: motors {fmt(row.replace_at_motor)} h,
          propellers {fmt(row.replace_at_propeller)} h, batteries {fmt(row.replace_at_battery)} cycles.
          Every view below shows the fleet flown under this rule. Cost trade-off: Weibull tab.
        </p>
      </div>
      <Bars title="Parts warned and replaced" rows={rows} field="warned" retire={retire} onPick={onChange} />
      <Bars title="…of which caught worn by a chart" rows={rows} field="found_worn" retire={retire} onPick={onChange} />
      {failed > 0 && <Bars title="Failed in flight" rows={rows} field="failed_in_flight" retire={retire} onPick={onChange} />}
      {failed === 0 && <p className="retire-note">No part failed in flight in any run: the charts caught every worn part.</p>}
    </div>
  )
}
