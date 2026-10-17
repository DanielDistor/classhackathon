import { STATUS_CLASS, STATUS_WORD, fmt, partClass } from '../format.js'

export const Pill = ({ status, children }) => (
  <span className={`pill ${STATUS_CLASS[status] || status}`}>{children || STATUS_WORD[status]}</span>
)

/** A part's life-used bar (pct_used of its replace-at age, capped at 100%). */
export const LifeBar = ({ part }) => (
  <td className={`pcell ${partClass(part)}`}>
    <div className="pbar"><div style={{ width: `${Math.min(part.pct_used, 100).toFixed(0)}%` }} /></div>
  </td>
)

export const HealthBar = ({ status, pct, big }) => (
  <div className={`hbar ${big ? 'big ' : ''}${STATUS_CLASS[status]}`}>
    <div className="hbar-fill" style={{ width: `${pct}%` }} />
  </div>
)

export const healthPct = (h) => (h == null ? 0 : Math.round(h * 100))

export const Panel = ({ title, children, note }) => (
  <div className="panel">
    {title && <h4>{title}</h4>}
    {note && <p className="rule-note">{note}</p>}
    {children}
  </div>
)

export function Loading({ what }) {
  return <p className="rule-note loading">Loading {what}…</p>
}

export function Failed({ error }) {
  return <div className="panel error-box"><b>Couldn't load this view.</b> {error.message}</div>
}

export const Used = ({ p }) => <>{fmt(p.age)} / {fmt(p.b10)} {p.unit}</>
