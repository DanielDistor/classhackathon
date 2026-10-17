import { useMemo, useState } from 'react'
import { COLORS as C, extent, linear, linePath, niceTicks } from './scale.js'
import { fmt } from '../format.js'

const W = 1000
const H = 270
const M = { top: 30, right: 44, bottom: 30, left: 56 }

/**
 * One qc.monitor_chart() result, drawn as SVG: readings, ±3σ limits, the fleet range
 * during the baseline, the EWMA (restarting after each logged action) and every signal.
 * Drawing only: every number comes from the API.
 */
export default function MonitorChart({ chart, last }) {
  const [hover, setHover] = useState(null)
  const pts = useMemo(() => {
    if (!last) return chart.points
    const cut = chart.points[chart.points.length - 1].flight_no - last
    return chart.points.filter((p) => p.flight_no > cut)
  }, [chart, last])

  const xs = pts.map((p) => p.flight_no)
  const [x0, x1] = [xs[0] - 0.5, xs[xs.length - 1] + 0.5]
  const [y0, y1] = extent([pts.map((p) => p.value), pts.map((p) => p.ucl), pts.map((p) => p.lcl),
    pts.map((p) => p.z), pts.map((p) => p.fleet_ucl), pts.map((p) => p.fleet_lcl)])
  const x = linear([x0, x1], [M.left, W - M.right])
  const y = linear([y0, y1], [H - M.bottom, M.top])
  const dec = chart.decimals
  const base = pts.filter((p) => p.baseline)
  // A vertical line after each logged action that restarted the chart (past the baseline).
  const live = pts.filter((p) => !p.baseline)
  const resets = live.length
    ? chart.resets.filter((r) => r + 0.5 > x0 && r + 0.5 < x1 && r >= live[0].flight_no - 1)
    : []
  const lastPt = pts[pts.length - 1]

  // The EWMA restarts at every reset, so draw one path per segment.
  const ewmaSegments = []
  let seg = []
  pts.forEach((p, i) => {
    if (i > 0 && chart.resets.includes(pts[i - 1].flight_no)) { ewmaSegments.push(seg); seg = [] }
    seg.push(p)
  })
  ewmaSegments.push(seg)

  const onMove = (e) => {
    const box = e.currentTarget.getBoundingClientRect()
    const fx = x0 + ((e.clientX - box.left) / box.width * W - M.left) / (W - M.left - M.right) * (x1 - x0)
    let best = pts[0]
    for (const p of pts) if (Math.abs(p.flight_no - fx) < Math.abs(best.flight_no - fx)) best = p
    setHover(best)
  }

  return (
    <figure className="svg-chart">
      <figcaption><b>{chart.title}</b>: catches {chart.catches}</figcaption>
      <div className="svg-wrap">
        <svg viewBox={`0 0 ${W} ${H}`} role="img" onMouseMove={onMove} onMouseLeave={() => setHover(null)}
             aria-label={`${chart.title} control chart, flights ${xs[0]} to ${xs[xs.length - 1]}`}>
          <rect x={M.left} y={M.top} width={W - M.left - M.right} height={H - M.top - M.bottom} fill={C.surface} />
          {niceTicks(y0, y1, 4).map((t) => (
            <g key={t}>
              <line x1={M.left} x2={W - M.right} y1={y(t)} y2={y(t)} stroke={C.grid} />
              <text x={M.left - 8} y={y(t) + 4} textAnchor="end" className="tick">{fmt(t, dec > 1 ? dec - 1 : dec)}</text>
            </g>
          ))}
          {niceTicks(xs[0], xs[xs.length - 1], 8).map((t) => (
            <text key={t} x={x(t)} y={H - 8} textAnchor="middle" className="tick">{t}</text>
          ))}
          <text x={14} y={H / 2} transform={`rotate(-90 14 ${H / 2})`} textAnchor="middle" className="tick">{chart.unit}</text>

          {base.length > 0 && (
            <g>
              <rect x={x(base[0].flight_no - 0.5)} y={M.top} width={x(base[base.length - 1].flight_no + 0.5) - x(base[0].flight_no - 0.5)}
                    height={H - M.top - M.bottom} fill={C.grid} opacity={0.5} />
              <text x={x(base[0].flight_no - 0.5) + 6} y={M.top + 14} className="tick">baseline: first {base.length} flights, checked against the fleet range</text>
            </g>
          )}
          {resets.map((r) => <line key={r} x1={x(r + 0.5)} x2={x(r + 0.5)} y1={M.top} y2={H - M.bottom} stroke={C.grid} strokeWidth={1.4} />)}

          <path d={linePath(xs, pts.map((p) => p.value), x, y)} fill="none" stroke={C.series} strokeWidth={1} opacity={0.5} />
          {pts.map((p) => <circle key={p.flight_no} cx={x(p.flight_no)} cy={y(p.value)} r={2} fill={C.series} opacity={0.55} />)}
          {['ucl', 'lcl'].map((k) => (
            <g key={k}>
              <path d={linePath(xs, pts.map((p) => p[k]), x, y)} fill="none" stroke={C.ink2} strokeWidth={1.3} strokeDasharray="6 4" />
              <text x={W - M.right + 6} y={y(lastPt[k]) + 4} className="tick">{k.toUpperCase()}</text>
            </g>
          ))}
          {['fleet_ucl', 'fleet_lcl'].map((k) => (
            <path key={k} d={linePath(xs, pts.map((p) => p[k]), x, y)} fill="none" stroke={C.muted} strokeWidth={1.4} strokeDasharray="8 3 2 3" />
          ))}
          {ewmaSegments.map((s, i) => (
            <path key={i} d={linePath(s.map((p) => p.flight_no), s.map((p) => p.z), x, y)} fill="none" stroke={C.ewma} strokeWidth={2} />
          ))}

          {pts.filter((p) => p.rules_triggered && !(p.rule_1 || p.signal_fleet)).map((p) => {
            const cx = x(p.flight_no); const cy = y(p.value)
            return <path key={`d${p.flight_no}`} d={`M${cx},${cy - 6}L${cx + 6},${cy}L${cx},${cy + 6}L${cx - 6},${cy}Z`} fill={C.warning} stroke={C.surface} />
          })}
          {pts.filter((p) => p.rule_1 || p.signal_fleet).map((p) => {
            const cx = x(p.flight_no); const cy = y(p.value)
            return <path key={`x${p.flight_no}`} d={`M${cx - 5},${cy - 5}L${cx + 5},${cy + 5}M${cx + 5},${cy - 5}L${cx - 5},${cy + 5}`} stroke={C.critical} strokeWidth={3} strokeLinecap="round" />
          })}
          {pts.filter((p) => p.signal_ewma).map((p) => (
            <circle key={`e${p.flight_no}`} cx={x(p.flight_no)} cy={y(p.z)} r={6} fill="none" stroke={C.ewma} strokeWidth={1.8} />
          ))}

          {hover && (
            <line x1={x(hover.flight_no)} x2={x(hover.flight_no)} y1={M.top} y2={H - M.bottom} stroke={C.ink2} strokeWidth={0.8} />
          )}
        </svg>
        {hover && (
          <div className="tip" style={{ left: `${(x(hover.flight_no) / W) * 100}%` }}>
            <b>Flight {hover.flight_no}</b>{hover.baseline ? ' (baseline)' : ''}
            <div>Reading: {fmt(hover.value, dec)} {chart.unit}</div>
            {hover.z != null && <div>EWMA: {fmt(hover.z, dec)}</div>}
            <div>Limits: {fmt(hover.lcl, dec)} to {fmt(hover.ucl, dec)}</div>
            {hover.what && <div className="tip-sig">Signal: {hover.what}</div>}
          </div>
        )}
      </div>
    </figure>
  )
}

export function MonitorLegend() {
  return (
    <ul className="chart-legend">
      <li><svg width="22" height="10"><line x1="0" x2="22" y1="5" y2="5" stroke={C.series} /><circle cx="11" cy="5" r="2.5" fill={C.series} /></svg>each flight</li>
      <li><svg width="22" height="10"><line x1="0" x2="22" y1="5" y2="5" stroke={C.ink2} strokeWidth="1.5" strokeDasharray="5 3" /></svg>control limits (±3σ, from the baseline)</li>
      <li><svg width="22" height="10"><line x1="0" x2="22" y1="5" y2="5" stroke={C.muted} strokeWidth="1.5" strokeDasharray="7 2 2 2" /></svg>fleet range (first 50 flights, rule 1 only)</li>
      <li><svg width="22" height="10"><line x1="0" x2="22" y1="5" y2="5" stroke={C.ewma} strokeWidth="2.5" /></svg>EWMA (smoothed trend)</li>
      <li><svg width="14" height="14"><path d="M3,3L11,11M11,3L3,11" stroke={C.critical} strokeWidth="3" strokeLinecap="round" /></svg>rule 1: beyond 3σ (or the fleet range)</li>
      <li><svg width="14" height="14"><path d="M7,1L13,7L7,13L1,7Z" fill={C.warning} /></svg>rules 2–8: a pattern</li>
      <li><svg width="14" height="14"><circle cx="7" cy="7" r="5" fill="none" stroke={C.ewma} strokeWidth="1.8" /></svg>EWMA beyond its limit</li>
    </ul>
  )
}
