import { useState } from 'react'
import { COLORS as C, linear, niceTicks } from './scale.js'

/** marker -> (label, colour). Shape and letter carry the meaning too, never colour alone. */
export const MARKER_STYLE = {
  R: ['warned → replaced before the next flight', C.series],
  F: ['failed in flight → replaced', C.critical],
  S: ['special cause → fixed', C.violet],
}
export const PART_LANES = ['motor 1', 'motor 2', 'motor 3', 'motor 4', 'propeller 1', 'propeller 2',
  'propeller 3', 'propeller 4', 'battery 1', 'battery 2']

function Mark({ m, cx, cy, r = 5.5 }) {
  const col = MARKER_STYLE[m][1]
  if (m === 'F') return <path d={`M${cx - r},${cy - r}L${cx + r},${cy + r}M${cx + r},${cy - r}L${cx - r},${cy + r}`} stroke={col} strokeWidth={3.2} strokeLinecap="round" />
  if (m === 'S') return <path d={`M${cx},${cy - r - 1}L${cx + r + 1},${cy}L${cx},${cy + r + 1}L${cx - r - 1},${cy}Z`} fill={col} stroke={C.surface} />
  return <circle cx={cx} cy={cy} r={r} fill={col} stroke={C.surface} />
}

/**
 * Maintenance timeline (qc.maintenance_timeline rows): one row per lane, flights across.
 * lane = "drone_id" for the fleet view, "lane" (part slot) for one drone.
 */
export default function Timeline({ events, rows, rowKey, nFlights, nBaseline, letters = false }) {
  const [hover, setHover] = useState(null)
  const W = 1000
  const rowH = 28
  const M = { top: 22, right: 18, bottom: 30, left: 92 }
  const H = M.top + rows.length * rowH + M.bottom
  const x = linear([0, nFlights + 2], [M.left, W - M.right])
  const y = (lane) => M.top + rows.indexOf(lane) * rowH + rowH / 2
  const shown = events.filter((e) => rows.includes(e[rowKey]))
  const order = { R: 0, S: 1, F: 2 }

  return (
    <div className="svg-wrap">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Maintenance timeline, ${shown.length} events`}>
        <rect x={M.left} y={M.top} width={W - M.left - M.right} height={rows.length * rowH} fill={C.surface} />
        {nBaseline && (
          <g>
            <rect x={x(0)} y={M.top} width={x(nBaseline + 0.5) - x(0)} height={rows.length * rowH} fill={C.grid} opacity={0.4} />
            <text x={(x(0) + x(nBaseline)) / 2} y={M.top - 6} textAnchor="middle" className="tick">baseline</text>
          </g>
        )}
        {niceTicks(0, nFlights, 10).map((t) => (
          <g key={t}>
            <line x1={x(t)} x2={x(t)} y1={M.top} y2={M.top + rows.length * rowH} stroke={C.grid} />
            <text x={x(t)} y={H - 10} textAnchor="middle" className="tick">{t}</text>
          </g>
        ))}
        {rows.map((r) => (
          <g key={r}>
            <line x1={M.left} x2={W - M.right} y1={y(r)} y2={y(r)} stroke={C.grid} strokeWidth={0.7} />
            <text x={M.left - 10} y={y(r) + 4} textAnchor="end" className="tick lane">{r}</text>
          </g>
        ))}
        {[...shown].sort((a, b) => order[a.marker] - order[b.marker]).map((e, i) => (
          <g key={i} onMouseEnter={() => setHover(e)} onMouseLeave={() => setHover(null)} className="tl-mark">
            <circle cx={x(e.flight_no)} cy={y(e[rowKey])} r={11} fill="transparent" />
            <Mark m={e.marker} cx={x(e.flight_no)} cy={y(e[rowKey])} />
            {letters && <text x={x(e.flight_no)} y={y(e[rowKey]) - 9} textAnchor="middle" className="tick tiny">{e.marker}</text>}
          </g>
        ))}
      </svg>
      {hover && (
        <div className="tip" style={{ left: `${(x(hover.flight_no) / W) * 100}%`, top: `${(y(hover[rowKey]) / H) * 100}%` }}>
          <b>{hover.drone_id}, after flight {hover.flight_no}</b>
          <div>{hover.marker}: {MARKER_STYLE[hover.marker][0]}</div>
          <div>{hover.lane}: {hover.trigger}</div>
        </div>
      )}
      <ul className="chart-legend center">
        {Object.entries(MARKER_STYLE).map(([m, [label]]) => (
          <li key={m}><svg width="16" height="16"><Mark m={m} cx={8} cy={8} r={4.5} /></svg>{m} = {label}</li>
        ))}
      </ul>
    </div>
  )
}
