// The exposure rating (docs/agency-it-risk-flow.md, section 6.3). Rule-based, like the link judge, so a risk partner can challenge each rule.
// Each of the five approved questions scores 0 to 3 from a stated rule over the rows it returns; the overall rating is the HIGHEST score, never an average,
// shown with the question(s) that set it. A question that cannot be answered scores unknown, never 0. Pure, so it is unit-tested against a gold set.
import { records, type Table } from './rcaBrief'
import { RATINGS, type Rating as Level_ } from './rating'

export type Key = 'systems' | 'access' | 'places' | 'exposures' | 'recovery'
export type Score = 0 | 1 | 2 | 3

/** Demo constants, shown on screen. In a real deployment the head of technology risk owns them. */
export const THRESHOLDS = { patchDays: 15, recoveryDays: 180, retestSoonDays: 90, widePeople: 100 } as const

// The wording must match demos/it-risk-estate/demo-questions-estate.json exactly (a test checks): the approved question bank matches on it.
export const QUESTIONS: { key: Key; n: number; text: string; short: string; needs: string[] }[] = [
  { key: 'systems', n: 1, short: 'Where it runs', text: 'For the November 2026 incident cluster, which of our systems run the affected technology?', needs: ['system', 'technology', 'tier'] },
  { key: 'access', n: 2, short: 'Critical data and who can reach it', text: 'Which of those systems and buckets hold restricted or confidential data, and who can reach them?', needs: ['resource', 'data_class', 'reachable_by', 'people', 'reach'] },
  { key: 'places', n: 3, short: 'Runbooks, credentials and recovery steps', text: 'Where do runbooks, credentials or recovery steps for those systems sit, and who can see them?', needs: ['system', 'location', 'kind', 'visible_to', 'people'] },
  { key: 'exposures', n: 4, short: 'Patches and untested changes', text: 'Which of those systems have a security patch overdue or a recent change that skipped pre-production testing?', needs: ['system', 'finding', 'detail', 'days'] },
  { key: 'recovery', n: 5, short: 'Dependants and recovery', text: 'What depends on those systems, and when was each last tested for recovery?', needs: ['system', 'tier', 'dependents', 'result', 'days_since_test'] },
]

export const SCORE_LABEL = ['No concern', 'Watch', 'Concern', 'Critical'] as const
export const LEVELS = RATINGS   // the one scale on every screen (rating.ts): Low, Medium, High, Critical
export type Level = Level_

/** The rule for each question, in words, as shown beside its score. Keep in step with the functions below. */
export const RULES: Record<Key, string> = {
  systems: `Critical (2) if any system that runs the affected technology is tier 1; Watch (1) if some do but none is tier 1; no concern if none. It never scores 3: running the technology is exposure, not a weakness.`,
  access: `Critical (3) if restricted data is reachable beyond its owner team by ${THRESHOLDS.widePeople} or more people. Concern (2) if restricted data is reachable beyond its owner team by anyone, or confidential data by ${THRESHOLDS.widePeople} or more. Watch (1) if confidential data is reachable beyond its owner team by fewer. Otherwise no concern.`,
  places: `Critical (3) if a credential is visible beyond its owners or team (department, company, external, a public channel). Concern (2) if a runbook or recovery step is visible that widely to ${THRESHOLDS.widePeople} or more people. Watch (1) if visible that widely to fewer. Otherwise no concern.`,
  exposures: `Critical (3) if a system has a security patch overdue by more than ${THRESHOLDS.patchDays} days and also a recent change that skipped pre-production testing. Concern (2) if any security patch is overdue by more than ${THRESHOLDS.patchDays} days, or two or more recent changes skipped testing. Watch (1) if a patch is overdue by up to ${THRESHOLDS.patchDays} days or one change skipped testing. Otherwise no concern.`,
  recovery: `Critical (3) if a tier 1 system was last recovery-tested more than ${THRESHOLDS.recoveryDays} days ago or never. Concern (2) if any other system was, or any test took longer than its target. Watch (1) if a test is more than ${THRESHOLDS.retestSoonDays} days old. Otherwise no concern. A recovery answer that does not cover every system is unknown.`,
}

export interface QScore { key: Key; n: number; question: string; short: string; score: Score | null; label: string; reason: string; rows: Table; rule: string }
export interface Rating {
  scores: QScore[]; score: Score | null; level: Level | null; setBy: number[]; unknown: number[]
  complete: boolean; sentence: string
}

type Rec = Record<string, string>
const num = (s: string | undefined): number | null => { if (s === undefined || s === '') return null; const v = Number(s); return Number.isFinite(v) ? v : null }
const WIDE = ['department', 'company', 'external', 'anyone', 'public']

function pick(t: Table, recs: Rec[], which: Rec[]): Table {
  const idx = which.map((r) => recs.indexOf(r)).filter((i) => i >= 0).sort((a, b) => a - b)
  return { columns: t.columns, rows: idx.map((i) => t.rows[i]) }
}
const names = (r: Rec[], f: string) => [...new Set(r.map((x) => x[f]))].join(', ')

type Outcome = { score: Score; reason: string; evidence: Rec[] }

function systems(r: Rec[]): Outcome {
  const tier1 = r.filter((x) => num(x.tier) === 1)
  if (tier1.length) return { score: 2, reason: `${r.length} system${r.length === 1 ? '' : 's'} run the affected technology, ${tier1.length} of them tier 1 (${names(tier1, 'system')}).`, evidence: tier1 }
  if (r.length) return { score: 1, reason: `${r.length} system${r.length === 1 ? '' : 's'} run the affected technology, none tier 1.`, evidence: r }
  return { score: 0, reason: 'No system here runs the affected technology.', evidence: [] }
}
function access(r: Rec[]): Outcome {
  const wide = r.filter((x) => x.reach !== 'owner team')
  const big = (x: Rec) => (num(x.people) ?? 0) >= THRESHOLDS.widePeople
  const a = wide.filter((x) => x.data_class === 'restricted' && big(x))
  if (a.length) return { score: 3, reason: `Restricted data is reachable beyond its owner team by ${THRESHOLDS.widePeople} or more people: ${names(a, 'resource')}.`, evidence: a }
  const b = wide.filter((x) => x.data_class === 'restricted')
  const c = wide.filter((x) => x.data_class === 'confidential' && big(x))
  if (b.length || c.length) return { score: 2, reason: [b.length && `Restricted data is reachable beyond its owner team (${names(b, 'resource')})`, c.length && `confidential data by ${THRESHOLDS.widePeople} or more people (${names(c, 'resource')})`].filter(Boolean).join('; ') + '.', evidence: [...b, ...c] }
  const d = wide.filter((x) => x.data_class === 'confidential')
  if (d.length) return { score: 1, reason: `Confidential data is reachable beyond its owner team by fewer than ${THRESHOLDS.widePeople} people (${names(d, 'resource')}).`, evidence: d }
  return { score: 0, reason: r.length ? 'Data of this class is reachable only by its owner team.' : 'No restricted or confidential data in scope.', evidence: [] }
}
function places(r: Rec[]): Outcome {
  const wide = r.filter((x) => WIDE.includes(x.visible_to))
  const cred = wide.filter((x) => x.kind === 'credential')
  if (cred.length) return { score: 3, reason: `A credential is visible beyond its owners or team: ${cred.map((x) => `${x.location} (${x.visible_to}, ${x.people} people)`).join('; ')}.`, evidence: cred }
  const big = wide.filter((x) => (num(x.people) ?? 0) >= THRESHOLDS.widePeople)
  if (big.length) return { score: 2, reason: `Runbooks or recovery steps are visible to ${THRESHOLDS.widePeople} or more people: ${big.map((x) => `${x.location} (${x.people})`).join('; ')}.`, evidence: big }
  if (wide.length) return { score: 1, reason: `Runbooks or recovery steps are visible beyond the team to fewer than ${THRESHOLDS.widePeople} people: ${wide.map((x) => x.location).join('; ')}.`, evidence: wide }
  return { score: 0, reason: r.length ? 'Runbooks, credentials and recovery steps are visible only to their owners or team.' : 'None found in SharePoint or Slack.', evidence: [] }
}
function exposures(r: Rec[]): Outcome {
  const patch = r.filter((x) => x.finding === 'security patch overdue')
  const change = r.filter((x) => x.finding === 'change without a pre-production test')
  const long = patch.filter((x) => (num(x.days) ?? 0) > THRESHOLDS.patchDays)
  const both = long.filter((p) => change.some((c) => c.system === p.system))
  if (both.length) return { score: 3, reason: `${names(both, 'system')}: a security patch overdue by more than ${THRESHOLDS.patchDays} days and a recent change that skipped pre-production testing.`, evidence: [...both, ...change.filter((c) => both.some((p) => p.system === c.system))] }
  if (long.length || change.length >= 2) return { score: 2, reason: [long.length && `Security patch overdue by more than ${THRESHOLDS.patchDays} days: ${long.map((x) => `${x.system} (${x.days})`).join(', ')}`, change.length >= 2 && `${change.length} recent changes skipped pre-production testing`].filter(Boolean).join('; ') + '.', evidence: [...long, ...(change.length >= 2 ? change : [])] }
  if (patch.length || change.length) return { score: 1, reason: [patch.length && `A security patch is overdue by up to ${THRESHOLDS.patchDays} days`, change.length && 'one recent change skipped pre-production testing'].filter(Boolean).join('; ') + '.', evidence: [...patch, ...change] }
  return { score: 0, reason: 'No security patch is overdue and no recent change skipped testing.', evidence: [] }
}
function recovery(r: Rec[]): Outcome {
  const age = (x: Rec) => num(x.days_since_test)                   // null: never tested
  const stale = (x: Rec) => age(x) === null || (age(x) as number) > THRESHOLDS.recoveryDays
  const t1 = r.filter((x) => num(x.tier) === 1 && stale(x))
  if (t1.length) return { score: 3, reason: `Tier 1 and last recovery-tested more than ${THRESHOLDS.recoveryDays} days ago or never: ${t1.map((x) => `${x.system} (${age(x) === null ? 'never' : age(x) + ' days'})`).join(', ')}.`, evidence: t1 }
  const slow = r.filter((x) => { const a = num(x.rto_actual_minutes), t = num(x.rto_target_minutes); return a !== null && t !== null && a > t })
  const other = r.filter(stale)
  if (other.length || slow.length) return { score: 2, reason: [other.length && `Last tested more than ${THRESHOLDS.recoveryDays} days ago or never: ${other.map((x) => x.system).join(', ')}`, slow.length && `Took longer than its target: ${slow.map((x) => x.system).join(', ')}`].filter(Boolean).join('; ') + '.', evidence: [...other, ...slow.filter((s) => !other.includes(s))] }
  const old = r.filter((x) => (age(x) as number) > THRESHOLDS.retestSoonDays)
  if (old.length) return { score: 1, reason: `A recovery test is more than ${THRESHOLDS.retestSoonDays} days old: ${old.map((x) => `${x.system} (${age(x)})`).join(', ')}.`, evidence: old }
  return { score: 0, reason: 'Every system was recovery-tested recently and within its target.', evidence: [] }
}
const FN: Record<Key, (r: Rec[]) => Outcome> = { systems, access, places, exposures, recovery }

function unknownScore(q: (typeof QUESTIONS)[number], why: string): QScore {
  return { key: q.key, n: q.n, question: q.text, short: q.short, score: null, label: 'Unknown', reason: why, rows: { columns: [], rows: [] }, rule: RULES[q.key] }
}

/** Scores the five answers. A missing answer, one without the expected columns, or a recovery answer that does not cover every system scores unknown, never 0. */
export function rate(a: Partial<Record<Key, Table>>): Rating {
  const inScope = a.systems ? a.systems.rows.length : null
  const scores: QScore[] = QUESTIONS.map((q) => {
    const t = a[q.key]
    if (!t) return unknownScore(q, 'This question was not answered, so it cannot be scored.')
    const cols = t.columns.map((c) => c.toLowerCase())
    const missing = q.needs.filter((c) => !cols.includes(c))
    if (missing.length) return unknownScore(q, `The answer did not have the columns this rule needs (${missing.join(', ')}), so it cannot be scored.`)
    if (q.key === 'recovery' && inScope !== null && t.rows.length < inScope) return unknownScore(q, `Recovery answered for ${t.rows.length} of ${inScope} systems, so it cannot be scored.`)
    const rs = records(t), o = FN[q.key](rs)
    return { key: q.key, n: q.n, question: q.text, short: q.short, score: o.score, label: SCORE_LABEL[o.score], reason: o.reason, rows: pick(t, rs, o.evidence), rule: RULES[q.key] }
  })
  const known = scores.filter((s) => s.score !== null)
  const unknown = scores.filter((s) => s.score === null).map((s) => s.n)
  const top = known.length ? (Math.max(...known.map((s) => s.score as number)) as Score) : null
  const setBy = top === null ? [] : known.filter((s) => s.score === top).map((s) => s.n)
  const level = top === null ? null : LEVELS[top]
  const q = (ns: number[]) => `question${ns.length === 1 ? '' : 's'} ${ns.join(' and ')}`
  const sentence = level === null ? 'No question could be scored, so there is no rating.'
    : (unknown.length ? `At least ${level}: ` : `${level}: `) + `set by ${q(setBy)}${unknown.length ? `; ${q(unknown)} could not be scored, so the rating may be higher` : ''}.`
  return { scores, score: top, level, setBy, unknown, complete: unknown.length === 0, sentence }
}

/** Plain text of the rating, for copying into an email or a ticket. */
export function exposureText(r: Rating): string {
  const L = ['Exposure to a similar incident: November 2026 cluster (simulated estate, invented data)', r.sentence, '']
  for (const s of r.scores) L.push(`${s.n}. ${s.short}: ${s.score === null ? 'Unknown' : `${s.label} (${s.score} of 3)`}. ${s.reason}`)
  L.push('', `Rules are demo constants: patch overdue more than ${THRESHOLDS.patchDays} days, recovery test older than ${THRESHOLDS.recoveryDays} days, ${THRESHOLDS.widePeople} or more people counts as wide.`)
  return L.join('\n')
}
