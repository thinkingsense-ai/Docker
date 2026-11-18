import { compact, describePlan, niceTicks, type ChartPlan } from './chartModel'
import { formatCell, humanName } from './format'

// Hand-drawn SVG: no charting library to ship, colours come from the page's own tokens (so light and dark both work), and the drawing scales with its box (viewBox) instead of needing a measured width.
const W = 640, COLORS = ['var(--c1)', 'var(--c2)', 'var(--c3)', 'var(--c4)', 'var(--c5)', 'var(--c6)']
const clip = (s: string, n: number) => (s.length > n ? s.slice(0, n - 1) + '…' : s)
const full = (v: number) => formatCell(String(v))

function Legend({ names }: { names: string[] }) {
  if (names.length < 2) return null
  return <ul className="legend">{names.map((n, i) => <li key={n}><i style={{ background: COLORS[i % COLORS.length] }} aria-hidden="true" /> {humanName(n)}</li>)}</ul>
}

function HBars({ plan }: { plan: ChartPlan }) {
  const k = plan.measures.length, row = 14 * k + 10, n = plan.labels.length
  const left = Math.min(230, Math.max(70, Math.max(...plan.labels.map((l) => Math.min(l.length, 34))) * 6.9)), right = 70, top = 8, bottom = 26
  const max = Math.max(...plan.measures.flatMap((m) => m.values), 0) || 1, ticks = niceTicks(0, max), end = ticks[ticks.length - 1] || 1
  const x = (v: number) => left + (Math.max(v, 0) / end) * (W - left - right), H = top + n * row + bottom
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img" aria-label={describePlan(plan, [])}>
      {ticks.map((t) => <g key={t}><line x1={x(t)} x2={x(t)} y1={top} y2={H - bottom} className="grid" /><text x={x(t)} y={H - 8} textAnchor="middle" className="tick">{compact(t)}</text></g>)}
      {plan.labels.map((l, i) => (
        <g key={i}>
          <text x={left - 8} y={top + i * row + row / 2 + 4} textAnchor="end" className="cat">{clip(l, 34)}<title>{l}</title></text>
          {plan.measures.map((m, j) => (
            <g key={m.name}>
              <rect x={left} y={top + i * row + 4 + j * 14} width={Math.max(2, x(m.values[i]) - left)} height={11} rx={3} fill={COLORS[j % COLORS.length]}><title>{`${l}: ${humanName(m.name)} ${full(m.values[i])}`}</title></rect>
              <text x={x(m.values[i]) + 6} y={top + i * row + 13 + j * 14} className="val">{compact(m.values[i])}</text>
            </g>))}
        </g>))}
    </svg>
  )
}

function VBars({ plan }: { plan: ChartPlan }) {
  const k = plan.measures.length, n = plan.labels.length, left = 46, right = 12, top = 18, bottom = 54, H = 280
  const max = Math.max(...plan.measures.flatMap((m) => m.values), 0) || 1, ticks = niceTicks(0, max), end = ticks[ticks.length - 1] || 1
  const slot = (W - left - right) / n, bw = Math.max(4, Math.min(48, (slot * 0.72) / k)), y = (v: number) => top + (1 - Math.max(v, 0) / end) * (H - top - bottom)
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img" aria-label={describePlan(plan, [])}>
      {ticks.map((t) => <g key={t}><line x1={left} x2={W - right} y1={y(t)} y2={y(t)} className="grid" /><text x={left - 6} y={y(t) + 4} textAnchor="end" className="tick">{compact(t)}</text></g>)}
      {plan.labels.map((l, i) => {
        const cx = left + slot * i + slot / 2
        return (
          <g key={i}>
            {plan.measures.map((m, j) => {
              const bx = cx - (bw * k) / 2 + j * bw
              return <g key={m.name}><rect x={bx} y={y(m.values[i])} width={bw - 1} height={Math.max(1, H - bottom - y(m.values[i]))} rx={3} fill={COLORS[j % COLORS.length]}><title>{`${l}: ${humanName(m.name)} ${full(m.values[i])}`}</title></rect>
                {n <= 10 && k === 1 && <text x={bx + bw / 2} y={y(m.values[i]) - 5} textAnchor="middle" className="val">{compact(m.values[i])}</text>}</g>
            })}
            <text x={cx} y={H - bottom + 16} textAnchor="middle" className="cat">{clip(l, Math.max(4, Math.floor(slot / 6.7)))}<title>{l}</title></text>
          </g>)
      })}
    </svg>
  )
}

function Lines({ plan }: { plan: ChartPlan }) {
  const n = plan.labels.length, left = 46, right = 16, top = 16, bottom = 34, H = 260
  const all = plan.measures.flatMap((m) => m.values), lo = Math.min(...all, 0), hi = Math.max(...all, 0) || 1, ticks = niceTicks(lo, hi), a = ticks[0], b = ticks[ticks.length - 1] || 1
  const x = (i: number) => left + (n === 1 ? (W - left - right) / 2 : (i / (n - 1)) * (W - left - right)), y = (v: number) => top + (1 - (v - a) / (b - a)) * (H - top - bottom)
  const every = Math.max(1, Math.ceil(n / 7))
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img" aria-label={describePlan(plan, [])}>
      {ticks.map((t) => <g key={t}><line x1={left} x2={W - right} y1={y(t)} y2={y(t)} className="grid" /><text x={left - 6} y={y(t) + 4} textAnchor="end" className="tick">{compact(t)}</text></g>)}
      {plan.measures.map((m, j) => {
        const c = COLORS[j % COLORS.length], d = m.values.map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ')
        return (
          <g key={m.name}>
            {plan.measures.length === 1 && <path d={`${d} L${x(n - 1)},${y(Math.max(a, 0))} L${x(0)},${y(Math.max(a, 0))} Z`} fill={c} opacity={0.16} />}
            <path d={d} fill="none" stroke={c} strokeWidth={2.5} strokeLinejoin="round" />
            {m.values.map((v, i) => <circle key={i} cx={x(i)} cy={y(v)} r={n > 40 ? 2 : 4} fill="var(--panel)" stroke={c} strokeWidth={2}><title>{`${plan.labels[i]}: ${humanName(m.name)} ${full(v)}`}</title></circle>)}
          </g>)
      })}
      {plan.labels.map((l, i) => i % every === 0 && <text key={i} x={x(i)} y={H - 12} textAnchor="middle" className="cat">{clip(formatCell(l), 12)}</text>)}
    </svg>
  )
}

function Donut({ plan }: { plan: ChartPlan }) {
  const m = plan.measures[0], total = m.values.reduce((s, v) => s + Math.max(v, 0), 0) || 1, R = 80, r = 52, cx = 100, cy = 100
  let acc = 0
  const arcs = m.values.map((v, i) => {
    const f = Math.max(v, 0) / total, a0 = acc * 2 * Math.PI - Math.PI / 2; acc += f; const a1 = acc * 2 * Math.PI - Math.PI / 2 - (f >= 0.9999 ? 0.001 : 0)
    const p = (rad: number, a: number) => `${(cx + rad * Math.cos(a)).toFixed(2)},${(cy + rad * Math.sin(a)).toFixed(2)}`, big = f > 0.5 ? 1 : 0
    return { d: `M${p(R, a0)} A${R},${R} 0 ${big} 1 ${p(R, a1)} L${p(r, a1)} A${r},${r} 0 ${big} 0 ${p(r, a0)} Z`, f, i }
  })
  return (
    <div className="donut">
      <svg viewBox="0 0 200 200" className="chart" role="img" aria-label={describePlan(plan, [])}>
        {arcs.map((a) => <path key={a.i} d={a.d} fill={COLORS[a.i % COLORS.length]} stroke="var(--panel)" strokeWidth={2}><title>{`${plan.labels[a.i]}: ${full(m.values[a.i])} (${Math.round(a.f * 100)}%)`}</title></path>)}
        <text x={cx} y={cy - 2} textAnchor="middle" className="center">{compact(total)}</text><text x={cx} y={cy + 16} textAnchor="middle" className="tick">total</text>
      </svg>
      <ul className="legend vert">{plan.labels.map((l, i) => <li key={i}><i style={{ background: COLORS[i % COLORS.length] }} aria-hidden="true" /> {clip(l, 40)} <span className="muted">{compact(m.values[i])} · {Math.round((Math.max(m.values[i], 0) / total) * 100)}%</span></li>)}</ul>
    </div>
  )
}

/** One chart, or one panel per measure when the measures are too far apart in size to share an axis. */
export default function Chart({ plan }: { plan: ChartPlan }) {
  const draw = (p: ChartPlan) => (p.kind === 'donut' ? <Donut plan={p} /> : p.kind === 'line' ? <Lines plan={p} /> : p.horizontal ? <HBars plan={p} /> : <VBars plan={p} />)
  if (plan.panels) return <div className="panels">{plan.measures.map((m) => <figure key={m.name}><figcaption>{humanName(m.name)}</figcaption>{draw({ ...plan, measures: [m], panels: false })}</figure>)}</div>
  return <div><Legend names={plan.measures.map((m) => m.name)} />{draw(plan)}</div>
}
