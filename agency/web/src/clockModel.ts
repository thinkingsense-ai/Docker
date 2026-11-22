// The notification clocks after a MAJOR incident (docs/agency-risk-register-plan.md, section 5). A TypeScript twin of demos/payment-workflow/clock_rules.py, tested against the same gold set
// (demos/it-risk-register/clocks_gold.json), so the screen and the workflow cannot disagree. Pure, so it is unit-tested.
// Nothing here decides that an incident is major or material: a person records that decision, and only then do clocks exist. Nothing is sent to any regulator.
// Rules are our reading of public summaries, checked in SECONDARY sources, not against the regulations. Timestamps are UTC (the Server returns them without a zone).
export const CLOCKS_QUESTIONS = {
  incidents: 'Which incidents has the firm recorded, and which have been classified as major?',
  rules: 'What notification rules apply after a major incident, and where do they come from?',
} as const

export interface ClockRule { rule_id?: string; regulator: string; seq: string | number; stage: string; title: string; hours: string | number; starts_from: string; also_within_hours_of_awareness?: string | number | null }
export interface Decision { awareness_at?: string | null; classified_at?: string | null }
export interface Clock { rule_id?: string; regulator: string; stage: string; title: string; due_at: string | null; basis: string; flags: string[]; state: 'open' | 'overdue' | null; seconds_left: number | null }
export interface Clocks { state: 'no_decision' | 'no_regulator' | 'clocks'; clocks: Clock[] }

const TS = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})(?:\.\d+)?\s*(Z|[+-]\d{2}(?::?\d{2})?)?$/
/** A timestamp as epoch milliseconds in UTC. No zone means UTC. null when it cannot be read. */
export function parseTs(s: string | null | undefined): number | null {
  const m = TS.exec((s ?? '').trim()); if (!m) return null
  const [y, mo, d, h, mi, se] = m.slice(1, 7).map(Number); const z = m[7]
  const off = !z || z === 'Z' ? 0 : (z[0] === '+' ? 1 : -1) * (Number(z.slice(1, 3)) * 60 + (z.length > 3 ? Number(z.slice(-2)) : 0))
  return Date.UTC(y, mo - 1, d, h, mi, se) - off * 60000
}
export const iso = (ms: number) => new Date(ms).toISOString().replace(/\.\d{3}Z$/, 'Z')
const num = (v: unknown): number | null => { if (v === null || v === undefined || v === '') return null; const n = Number(v); return Number.isFinite(n) ? Math.trunc(n) : null }
const H = 3600000
const hrs = (h: number) => `${h} hour${h === 1 ? '' : 's'}`

export function computeClocks(rules: ClockRule[], declared: string[], decision: Decision | null, nowMs: number): Clocks {
  const cls = decision ? parseTs(decision.classified_at) : null
  if (!decision || cls === null) return { state: 'no_decision', clocks: [] }
  const aw = parseTs(decision.awareness_at)
  const mine = rules.filter((r) => declared.includes(r.regulator)).sort((a, b) => (a.regulator < b.regulator ? -1 : a.regulator > b.regulator ? 1 : 0) || (num(a.seq) ?? 0) - (num(b.seq) ?? 0))
  if (!mine.length) return { state: 'no_regulator', clocks: [] }
  const out: Clock[] = []; const prev: Record<string, number | null> = {}
  for (const r of mine) {
    const h = num(r.hours) ?? 0; const w = num(r.also_within_hours_of_awareness); let due: number | null = null; let why: string[] = []; const flags: string[] = []
    if (r.starts_from === 'classified') { due = cls + h * H; why.push(`${hrs(h)} after it was recorded as major`) }
    else if (r.starts_from === 'awareness') { if (aw !== null) { due = aw + h * H; why.push(`${hrs(h)} after the firm became aware`) } else flags.push('no awareness time recorded') }
    else if (r.starts_from === 'previous_report') {
      const p = prev[r.regulator]
      if (p) { due = p + h * H; why.push(`${hrs(h)} after the previous report; the latest possible time, assuming it was sent at its deadline`); flags.push('depends on when the previous report is sent') } else flags.push('the previous stage has no deadline')
    }
    if (w !== null && aw !== null) {
      const limit = aw + w * H
      if (due === null || limit < due) { due = limit; why = [`${hrs(w)} after the firm became aware, which comes before ${hrs(h)} after it was recorded as major`] }
      else why.push(`and no later than ${hrs(w)} after the firm became aware (${iso(limit)}), which is later`)
    }
    if (due !== null && due < cls && r.starts_from === 'classified') flags.push('already past when it was recorded as major')
    const left = due === null ? null : Math.trunc((due - nowMs) / 1000)
    out.push({ rule_id: r.rule_id, regulator: r.regulator, stage: r.stage, title: r.title, due_at: due === null ? null : iso(due), basis: why.join('; '), flags, state: due === null ? null : left! < 0 ? 'overdue' : 'open', seconds_left: left })
    prev[r.regulator] = due
  }
  return { state: 'clocks', clocks: out }
}

/** "3 h 20 min left" or "overdue by 2 days 4 h", for a number of seconds (negative = overdue). */
export function leftText(seconds: number | null): string {
  if (seconds === null) return 'no deadline'
  const s = Math.abs(seconds), d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60)
  const t = d ? `${d} day${d === 1 ? '' : 's'} ${h} h` : h ? `${h} h ${m} min` : `${m} min`
  return seconds < 0 ? `overdue by ${t}` : `${t} left`
}
