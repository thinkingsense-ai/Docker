import { useEffect, useRef, useState } from 'react'
import { GROUPS, type Icon, H, NODES, NODE_H, NODE_W, ROUTES, SPEEDS, W, advance, clampSpeed, newSim, pointAt, routePoints, type Sim } from './flowModel'

const ICONS: Record<Icon, React.ReactElement> = {      // 24 by 24, drawn as outlines so the series colour carries
  document: <><rect x="5" y="3" width="14" height="18" rx="2" /><path d="M8.5 8h7M8.5 12h7M8.5 16h4" /></>,
  database: <><ellipse cx="12" cy="6" rx="7" ry="3" /><path d="M5 6v12c0 1.7 3.1 3 7 3s7-1.3 7-3V6M5 12c0 1.7 3.1 3 7 3s7-1.3 7-3" /></>,
  server: <><rect x="4" y="4" width="16" height="6" rx="1.5" /><rect x="4" y="14" width="16" height="6" rx="1.5" /><path d="M8 7h.01M8 17h.01" /></>,
  chat: <path d="M4 5h16v11H9l-5 4z" />,
  alert: <><path d="M12 3a6 6 0 0 0-6 6v4l-2 3h16l-2-3V9a6 6 0 0 0-6-6z" /><path d="M10 19a2 2 0 0 0 4 0" /></>,
}
const lsGet = () => { try { return clampSpeed(Number(localStorage.getItem('agency.flowspeed') ?? SPEEDS.start)) } catch { return SPEEDS.start } }

/**
 * Data moving through Agency: sources, the Thinking Sense layer (access, approved questions, stated rules), analysis, reporting, decisions and the record.
 * An illustration of the path, not live traffic. `focus` lights up nodes (the tour passes the ones its step is about) and sends balls through them more often.
 */
const focus0 = { current: [] as string[] }
export default function Flow({ focus = [], compact = false }: { focus?: string[]; compact?: boolean }) {
  const [speed, setSpeed] = useState(lsGet)
  const reduced = typeof window !== 'undefined' && !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  const [paused, setPaused] = useState(reduced)
  const [sim, setSim] = useState<Sim>(() => { let s = newSim(); for (let i = 0; i < 300; i++) s = advance(s, 16, 1, focus0.current); return s })     // already under way when the screen opens, not empty
  const [sel, setSel] = useState<string | null>(null)
  const [present, setPresent] = useState(false)
  const root = useRef<HTMLElement>(null)
  // Present: fills the screen (the browser's full screen when it allows, else the window); Escape leaves either
  async function togglePresent() {
    if (present) { setPresent(false); if (document.fullscreenElement) await document.exitFullscreen().catch(() => {}); return }
    setPresent(true); try { await root.current?.requestFullscreen?.() } catch { /* the window fill is enough */ }
  }
  useEffect(() => {
    const off = () => { if (!document.fullscreenElement) setPresent(false) }
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape') setPresent(false) }
    document.addEventListener('fullscreenchange', off); document.addEventListener('keydown', key)
    return () => { document.removeEventListener('fullscreenchange', off); document.removeEventListener('keydown', key) }
  }, [])
  const live = useRef({ speed, paused, focus }); live.current = { speed, paused, focus }
  useEffect(() => {
    let raf = 0, last = performance.now()
    const tick = (t: number) => { const dt = t - last; last = t; setSim((s) => advance(s, dt, live.current.speed, live.current.focus, live.current.paused)); raf = requestAnimationFrame(tick) }
    raf = requestAnimationFrame(tick); return () => cancelAnimationFrame(raf)
  }, [])
  const set = (v: number) => { const c = clampSpeed(v); setSpeed(c); try { localStorage.setItem('agency.flowspeed', String(c)) } catch { /* private window */ } }
  const pts = Object.fromEntries(ROUTES.map((r) => [r.id, routePoints(r)]))
  const route = ROUTES.find((r) => r.id === sel)

  return (
    <section ref={root} className={'flow' + (compact ? ' compact' : '') + (present ? ' present' : '')} aria-label="Data flow">
      {!compact && <header className="brief-head">
        <h2>How data moves through Agency</h2>
        <p className="notbuilt" role="note"><strong>An illustration of the path.</strong> The balls are not live traffic. They show what each kind of data goes through: it is read as you, asked for by an approved question, checked by stated rules (no model decides), reported, decided by a named person, and recorded.</p>
      </header>}
      <div className="flow-controls">
        <label>Speed <input type="range" min={SPEEDS.min} max={SPEEDS.max} step={SPEEDS.step} value={speed} onChange={(e) => set(Number(e.target.value))} aria-valuetext={`${speed} times`} /> <output>{speed}×</output></label>
        <button onClick={() => setPaused((p) => !p)} aria-pressed={paused}>{paused ? 'Play' : 'Pause'}</button>
        {!compact && <button onClick={togglePresent} aria-pressed={present}>{present ? 'Leave full screen (Esc)' : 'Full screen'}</button>}
        {reduced && <span className="muted small">Motion is reduced in your system settings, so it starts paused.</span>}
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Data flows from sources, through the Thinking Sense layer's access, approved questions and stated rules, to analysis, reporting, a named approver, the risk register and the audit record.">
        {GROUPS.map((g) => <text key={g.id} x={g.x + NODE_W / 2} y={28} textAnchor="middle" className="flow-group">{g.label}</text>)}
        {ROUTES.map((r) => <polyline key={r.id} points={pts[r.id].map((p) => p.join(',')).join(' ')} className={'flow-route' + (sel === r.id ? ' on' : '')} style={{ stroke: `var(--c${r.kind})` }} />)}
        {sim.balls.map((b) => {
          const r = ROUTES.find((x) => x.id === b.route)!; const [x, y] = pointAt(pts[b.route], b.u); const dim = !!sel && sel !== b.route
          return <g key={b.id} className="flow-token" transform={`translate(${x},${y})`} style={{ color: `var(--c${r.kind})`, opacity: dim ? 0.25 : 1 }}>
            <circle r={16} className="flow-disc" /><g transform="translate(-9.5,-9.5) scale(.8)" className="flow-glyph">{ICONS[r.icon]}</g>
          </g>
        })}
        {NODES.map((m) => {
          const on = focus.includes(m.id)
          const hit = sim.balls.some((b) => { const r = ROUTES.find((x) => x.id === b.route)!; const [bx, by] = pointAt(pts[b.route], b.u); return Math.hypot(bx - (m.x + NODE_W / 2), by - (m.y + NODE_H / 2)) < 26 && r.ids.includes(m.id) })
          return <g key={m.id} className={'flow-node g-' + m.group + (on ? ' focus' : '') + (hit ? ' hit' : '') + (m.planned ? ' planned' : '')}>
            <rect x={m.x} y={m.y} width={NODE_W} height={NODE_H} rx={8} />
            <text x={m.x + NODE_W / 2} y={m.y + 23} textAnchor="middle" className="flow-label">{m.label}</text>
            <text x={m.x + NODE_W / 2} y={m.y + 40} textAnchor="middle" className="flow-sub">{m.sub}</text>
          </g>
        })}
      </svg>
      {!compact && <>
        <ul className="flow-legend" aria-label="Kinds of data">
          {ROUTES.map((r) => <li key={r.id}><button className={'link' + (sel === r.id ? ' on' : '')} aria-pressed={sel === r.id} onClick={() => setSel(sel === r.id ? null : r.id)}><svg viewBox="0 0 24 24" width="20" height="20" className="flow-glyph" style={{ color: `var(--c${r.kind})` }} aria-hidden>{ICONS[r.icon]}</svg> {r.label}</button></li>)}
        </ul>
        <p className="small" role="status">{route ? <><strong>{route.label}.</strong> {route.example} <span className="muted">Path: {route.ids.map((i) => NODES.find((n) => n.id === i)!.label).join(' → ')}.</span></> : <span className="muted">Choose a kind of data to follow it and read its path. ServiceNow and Datadog (dashed) are planned: nothing flows from them yet.</span>}</p>
      </>}
    </section>
  )
}
