// The Server streams about a dozen internal steps while it answers ("sql", "planned", "explain_plan", "plan_narrative", "check" six times). A person needs six plain stages and a clock.
// Pure, so it is unit-tested: events in, a list of stages out.
export type StageId = 'understand' | 'find' | 'write' | 'check' | 'run' | 'answer'
export interface ProgressEvent { step: string; t?: number; [k: string]: any }
export interface StageView { id: StageId; label: string; state: 'done' | 'now' | 'next'; ms?: number; detail?: string }

const STAGES: { id: StageId; label: string }[] = [
  { id: 'understand', label: 'Reading your question' }, { id: 'find', label: 'Choosing where to look' }, { id: 'write', label: 'Writing the query' },
  { id: 'check', label: 'Checking it is safe and sound' }, { id: 'run', label: 'Getting the data' }, { id: 'answer', label: 'Writing the answer' },
]
const OF: Record<string, StageId> = {
  understanding: 'understand', planned: 'find', ontology: 'find', sql: 'write', check: 'check',
  executing: 'run', results: 'run', explain_plan: 'run', plan_narrative: 'run', confidence: 'run', answering: 'answer',
}
const index = (id: StageId) => STAGES.findIndex((s) => s.id === id)

export function fmtMs(ms: number): string { return ms < 950 ? '<1 s' : ms < 59_500 ? (ms / 1000).toFixed(ms < 10_000 ? 1 : 0) + ' s' : Math.floor(ms / 60_000) + ' min ' + Math.round((ms % 60_000) / 1000) + ' s' }

export interface Progress { stages: StageView[]; totalMs: number; finished: boolean; reused: boolean; stopped: boolean }

/** `events` in arrival order (each with the time it arrived, `t`), `now` the clock. */
export function summarize(events: ProgressEvent[], now: number, startedAt?: number): Progress {
  const first = new Map<StageId, number>(); let top = -1, reused = false, finished = false, stopped = false
  const checks = { n: 0, ok: 0 }, detail: Partial<Record<StageId, string>> = {}, sources: string[] = []
  for (const e of events) {
    const t = e.t ?? now
    if (e.step === 'done') { finished = true; continue }
    if (e.step === 'stopped' || e.step === 'error') { stopped = true; continue }
    const id = OF[e.step]; if (!id) continue                              // internal steps with no meaning to a person are folded into their stage by OF; anything else is ignored
    if (!first.has(id)) first.set(id, t)
    top = Math.max(top, index(id))
    if (e.step === 'planned') {
      if (e.source === 'question_bank') reused = true
      for (const b of e.backends ?? []) if (!sources.includes(String(b))) sources.push(String(b))
    }
    if (e.step === 'ontology') detail.find = 'Applied your business definitions'
    if (e.step === 'check') { checks.n++; if (e.status === 'pass' || e.status === 'passed') checks.ok++ }
  }
  if (sources.length) detail.find = (reused ? 'Matched an approved question; ' : '') + 'looking in ' + sources.join(', ')
  else if (reused) detail.find = 'Matched an approved question'
  if (reused) detail.write = 'Reused the approved query'
  if (checks.n) detail.check = `${checks.ok} of ${checks.n} checks passed`
  const begin = startedAt ?? Math.min(...[...first.values(), now])
  const stages: StageView[] = STAGES.map((s, i) => {
    const t0 = first.get(s.id)
    const later = STAGES.slice(i + 1).map((x) => first.get(x.id)).filter((x): x is number => x !== undefined)
    const state: StageView['state'] = finished || i < top ? 'done' : i === top ? 'now' : 'next'
    const end = later.length ? Math.min(...later) : finished ? now : undefined
    return { id: s.id, label: s.label, state, ms: t0 === undefined ? undefined : state === 'now' ? now - t0 : Math.max(0, (end ?? now) - t0), detail: detail[s.id] }
  })
  // while waiting for the first event, the first stage is the one in progress
  if (!finished && top < 0 && !stopped) stages[0] = { ...stages[0], state: 'now', ms: now - begin }
  const lastT = events.length ? events[events.length - 1].t ?? now : now
  return { stages, totalMs: Math.max(0, (finished || stopped ? lastT : now) - begin), finished, reused, stopped }
}

// The Server's check ids, in words. An id this table does not know is shown with its underscores removed.
const CHECK: Record<string, string> = {
  dml_safety: 'Only reads data, never changes it', write_safety: 'Only reads data, never changes it', schema_fidelity: 'Uses tables and columns that exist', backend_routing: 'Sent to the right data source',
  access_check: 'Your access allows it', result_validation: 'The result passes sanity checks', narrative_consistency: 'The summary matches the numbers',
}
export function checkLabel(id: string): string { return CHECK[id] ?? (id.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase())) }
export function checkState(status: string): { text: string; ok: boolean | null } {
  const s = status.toLowerCase()
  return s === 'pass' || s === 'passed' ? { text: 'passed', ok: true } : s === 'skipped' ? { text: 'not needed', ok: null } : { text: s === 'warn' || s === 'warning' ? 'warning' : 'failed', ok: false }
}
