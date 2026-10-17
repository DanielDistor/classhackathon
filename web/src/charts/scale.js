// Tiny helpers for hand-drawn SVG charts (no chart library).

/** A linear map from a data domain [d0, d1] onto pixels [r0, r1]. */
export function linear([d0, d1], [r0, r1]) {
  if (d1 === d0) return () => (r0 + r1) / 2
  const k = (r1 - r0) / (d1 - d0)
  return (v) => r0 + (v - d0) * k
}

/** About `count` round tick values (1, 2, 2.5 or 5 × 10^k steps) inside [lo, hi]. */
export function niceTicks(lo, hi, count = 5) {
  if (!(hi > lo)) return [lo]
  const raw = (hi - lo) / count
  const mag = 10 ** Math.floor(Math.log10(raw))
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw)
  const out = []
  for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-9; v += step) out.push(+v.toFixed(10))
  return out
}

/** [min, max] of the finite numbers among several arrays, padded by `pad` × the span. */
export function extent(arrays, pad = 0.06) {
  let lo = Infinity
  let hi = -Infinity
  for (const a of arrays) for (const v of a) if (v != null && Number.isFinite(v)) { lo = Math.min(lo, v); hi = Math.max(hi, v) }
  if (!Number.isFinite(lo)) return [0, 1]
  const span = hi - lo || Math.abs(hi) || 1
  return [lo - span * pad, hi + span * pad]
}

/** SVG path through points, breaking the line wherever y is null. */
export function linePath(xs, ys, x, y) {
  let d = ''
  let pen = false
  for (let i = 0; i < xs.length; i++) {
    if (ys[i] == null || !Number.isFinite(ys[i])) { pen = false; continue }
    d += `${pen ? 'L' : 'M'}${x(xs[i]).toFixed(1)},${y(ys[i]).toFixed(1)}`
    pen = true
  }
  return d
}

export const COLORS = {
  surface: '#fcfcfb', ink: '#0b0b0b', ink2: '#52514e', grid: '#e4e3df',
  series: '#2a78d6', ewma: '#eb6834', violet: '#6250d6', muted: '#9a9890',
  warning: '#c98500', critical: '#d03b3b',
}
