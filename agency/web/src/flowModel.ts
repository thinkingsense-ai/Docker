// The data-flow picture (Data flow screen and the tour's strip): where data comes from, what the Thinking Sense layer does with it, and where it ends up.
// An ILLUSTRATION of the path, not live traffic: the balls are not real requests. Pure, so it is unit-tested; the drawing is in Flow.tsx.
export type Group = 'source' | 'layer' | 'analysis' | 'output' | 'decision'
export interface FlowNode { id: string; label: string; sub: string; group: Group; x: number; y: number; planned?: boolean }
export const W = 1000, H = 560
export const NODE_W = 128, NODE_H = 54

export const GROUPS: { id: Group; label: string; x: number }[] = [
  { id: 'source', label: 'Sources', x: 12 }, { id: 'layer', label: 'Thinking Sense layer', x: 196 }, { id: 'analysis', label: 'Analysis (rules)', x: 410 },
  { id: 'output', label: 'Reporting', x: 612 }, { id: 'decision', label: 'Decisions and record', x: 800 },
]
const col = (g: Group) => GROUPS.find((x) => x.id === g)!.x

const n = (id: string, label: string, sub: string, group: Group, y: number, planned = false, dx = 0): FlowNode => ({ id, label, sub, group, x: col(group) + dx, y, planned })
export const NODES: FlowNode[] = [
  n('feeds', 'News feeds', 'headlines, advisories', 'source', 60),
  n('estate', 'Estate data', 'systems, patches, tests', 'source', 160),
  n('events', 'Slack and SharePoint', 'event streams', 'source', 260),
  n('cases', 'Case data', 'incidents, register', 'source', 360),
  n('itsm', 'ServiceNow, Datadog', 'planned', 'source', 460, true),

  n('access', 'Per-person access', 'Workspaces, grants', 'layer', 110, false, 20),
  n('questions', 'Approved questions', 'asked as you', 'layer', 250, false, 20),
  n('rules', 'Stated rules', 'no model decides', 'layer', 390, false, 20),

  n('judge', 'Link judge', 'grade vs sources', 'analysis', 70),
  n('exposure', 'Exposure rules', 'highest score wins', 'analysis', 170),
  n('priorities', 'Priority rules', 'likelihood + impact', 'analysis', 270),
  n('clocks', 'Clock rules', 'DORA, MAS', 'analysis', 370),

  n('record', 'Problem record', 'causes, verdict', 'output', 70),
  n('rating', 'Exposure rating', 'Low to Critical', 'output', 170),
  n('list', 'Ranked systems', 'with reasons', 'output', 270),
  n('deadlines', 'Deadlines', 'to the minute', 'output', 370),

  n('approval', 'Named approver', 'not the proposer', 'decision', 150),
  n('register', 'Risk register', 'append-only', 'decision', 270),
  n('audit', 'Audit', 'hash-chained record', 'decision', 390),
]
export const node = (id: string) => NODES.find((x) => x.id === id)!
export const centre = (id: string): [number, number] => { const m = node(id); return [m.x + NODE_W / 2, m.y + NODE_H / 2] }

export type Icon = 'document' | 'database' | 'server' | 'chat' | 'alert'
export interface Route { id: string; label: string; kind: number; icon: Icon; ids: string[]; example: string }
// kind picks the series colour --c1..--c6 (the same tokens the charts use)
export const ROUTES: Route[] = [
  { id: 'headline', label: 'A headline', kind: 1, icon: 'document', example: 'A story calling an outage "AI hacking" is read, graded against its sources, and becomes a problem record a named person publishes or holds.',
    ids: ['feeds', 'access', 'questions', 'rules', 'judge', 'record', 'approval', 'register', 'audit'] },
  { id: 'estate', label: 'A patch record', kind: 2, icon: 'database', example: 'The estate is asked, as you, whether the same incident could reach it; five scores become one rating, which a person approves.',
    ids: ['estate', 'access', 'questions', 'rules', 'exposure', 'rating', 'approval', 'register', 'audit'] },
  { id: 'priority', label: 'A system', kind: 3, icon: 'server', example: 'Each system gets likelihood and impact; the top one goes for assessment and, if Critical, two second-line people approve a register row.',
    ids: ['estate', 'access', 'questions', 'rules', 'priorities', 'list', 'approval', 'register', 'audit'] },
  { id: 'event', label: 'A chat or file event', kind: 4, icon: 'chat', example: 'A credential in a chat, or a file shared too widely, arrives as an event and changes the exposure rating.',
    ids: ['events', 'access', 'questions', 'rules', 'exposure', 'rating'] },
  { id: 'incident', label: 'An incident', kind: 5, icon: 'alert', example: 'A person records that an incident is major; only then do regulator clocks start. Nothing is ever sent.',
    ids: ['cases', 'access', 'questions', 'rules', 'clocks', 'deadlines', 'approval', 'audit'] },
]

/** What each guided-tour step lights up (tourScript step ids). */
export const STEP_FOCUS: Record<string, string[]> = {
  watch: ['feeds', 'access', 'questions'], sources: ['feeds'], record: ['feeds', 'judge', 'record'], send: ['record', 'approval'], hold: ['approval', 'audit'],
  exposure: ['estate', 'events', 'exposure', 'rating'], priorities: ['estate', 'priorities', 'list'], assess: ['list', 'approval'], second1: ['approval'], second2: ['approval', 'register'],
  clocks: ['cases', 'clocks', 'deadlines'], major: ['approval', 'deadlines'], clocks2: ['clocks', 'deadlines'], audit: ['audit', 'register'],
}

/** The polyline a route follows (node centres) and its length. */
export function routePoints(r: Route): [number, number][] { return r.ids.map(centre) }
export function routeLength(pts: [number, number][]): number { let L = 0; for (let i = 1; i < pts.length; i++) L += Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]); return L }
/** Where a ball is when it has travelled fraction u (0 to 1) of the route. */
export function pointAt(pts: [number, number][], u: number): [number, number] {
  const total = routeLength(pts), want = Math.min(1, Math.max(0, u)) * total; let run = 0
  for (let i = 1; i < pts.length; i++) {
    const seg = Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1])
    if (run + seg >= want) { const f = seg === 0 ? 0 : (want - run) / seg; return [pts[i - 1][0] + (pts[i][0] - pts[i - 1][0]) * f, pts[i - 1][1] + (pts[i][1] - pts[i - 1][1]) * f] }
    run += seg
  }
  return pts[pts.length - 1]
}

export const SPEEDS = { min: 0.25, max: 4, step: 0.25, start: 1 }
export const clampSpeed = (s: number) => (Number.isFinite(s) ? Math.min(SPEEDS.max, Math.max(SPEEDS.min, s)) : SPEEDS.start)

export interface Ball { id: number; route: string; u: number }
export interface Sim { balls: Ball[]; clock: number; next: Record<string, number>; seq: number }
export const newSim = (): Sim => ({ balls: [], clock: 0, next: {}, seq: 0 })
const PX_PER_SEC = 150              // at 1x: how far a ball moves, in drawing units
const GAP_MS = 1800                 // ambient gap between balls on one route at 1x; a route through a focused node gets a ball three times as often
/** One animation step of dtMs real milliseconds at the given speed. Speed scales both how fast balls move and how often they appear, so the picture keeps its density. */
export function advance(sim: Sim, dtMs: number, speed: number, focus: string[] = [], paused = false): Sim {
  if (paused || dtMs <= 0) return sim
  const s = clampSpeed(speed), dt = Math.min(dtMs, 100) * s, clock = sim.clock + dt
  const next = { ...sim.next }; let seq = sim.seq; const balls: Ball[] = []
  for (const b of sim.balls) {
    const r = ROUTES.find((x) => x.id === b.route)!; const L = routeLength(routePoints(r)); const u = b.u + (dt / 1000) * PX_PER_SEC / L
    if (u < 1) balls.push({ ...b, u })
  }
  for (const r of ROUTES) {
    const hot = r.ids.some((i) => focus.includes(i)); const gap = hot ? GAP_MS / 3 : GAP_MS
    if (next[r.id] === undefined) next[r.id] = clock + (ROUTES.indexOf(r) * GAP_MS) / ROUTES.length
    if (clock >= next[r.id]) { balls.push({ id: ++seq, route: r.id, u: 0 }); next[r.id] = clock + gap }
  }
  return { balls, clock, next, seq }
}
