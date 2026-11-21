// The Priorities list (docs/agency-risk-register-plan.md, section 4): which systems to fix first. Rule-based, like the exposure rating and the link judge, so a risk partner can challenge each rule.
// Method, not a standard: it follows the shape of a public technology-risk-prioritization article (likelihood, impact, criticality, dependencies, escalation triggers that override the score).
// Every threshold is a demo constant shown on screen. No model decides anything. The business-impact column stays empty until a firm supplies its business services. Pure, so it is unit-tested against a gold set.
import { records, type Table } from './rcaBrief'
import { RATINGS, ratingRank, type Rating } from './rating'

/** The date the estate figures are stored as of (the demo data is as of this day; a real source would use today). */
export const AS_OF = '2026-11-20'
export const THRESHOLDS = { highEpss: 0.5, midEpss: 0.1, supportDays: 90, recoveryDays: 180, manyDependants: 3 } as const

// The wording must match demos/it-risk-estate/demo-questions-priorities.json exactly (a test checks): the approved question bank matches on it.
export const PRIORITY_QUESTION = 'Which of our systems should we fix first, and what do we know about each?'
export const NEEDS = ['system', 'tier', 'environment', 'data_class', 'internet_facing', 'dependents', 'open_patches', 'known_exploited_open', 'untested_changes', 'days_since_test', 'credentials_wide'] as const

export const TRIGGERS = {
  kev_exposed: 'A known-exploited flaw is open on an internet-facing system of the top business tier.',
  credential_shared: 'A credential is visible beyond its owners or team.',
  exposed_untested: 'An internet-facing system has no recovery test in more than 180 days (or never).',
  exposure_critical: 'The exposure rating is already Critical and this system runs the affected technology.',
} as const
export type TriggerId = keyof typeof TRIGGERS

export const RULES = {
  likelihood: `Critical if a known-exploited flaw is open or a credential is visible beyond its owners or team. High if an open flaw has an exploit score of ${THRESHOLDS.highEpss} or more, or the system is internet-facing with any flaw open. Medium if an open flaw scores ${THRESHOLDS.midEpss} or more, a change skipped pre-production testing, vendor support ends within ${THRESHOLDS.supportDays} days (or has ended), or the last recovery test is older than ${THRESHOLDS.recoveryDays} days or never happened. Otherwise Low.`,
  impact: `Start from the business tier (tier 1 High, tier 2 Medium, tier 3 Low). Add one step for restricted data and one for ${THRESHOLDS.manyDependants} or more dependants; take one step off outside production and disaster recovery. Capped at Critical.`,
  rating: 'The two bands are added (Low 0 to Critical 3): 0 or 1 is Low, 2 or 3 Medium, 4 or 5 High, 6 Critical. A trigger lifts the rating to at least High and is shown beside it.',
  order: 'Rating, then the number of triggers, then the number of dependants, then the business tier.',
} as const

export interface Priority {
  system: string; tier: number | null; rating: Rating; likelihood: Rating; impact: Rating; triggers: TriggerId[]; lifted: boolean
  dependents: number; reason: string; lossEvent: string; businessImpact: null; notes: string[]; likelihoodInputs: string; impactInputs: string
  systemId: string | null; registered: { rating: string; by: string; at: string } | null
}
export interface Priorities { rows: Priority[]; ok: boolean; missing: string[]; sentence: string }

type Rec = Record<string, string>
const num = (s: string | undefined): number | null => { if (s === undefined || s === '') return null; const v = Number(s); return Number.isFinite(v) ? v : null }
const yes = (s: string | undefined) => ['true', 't', '1', 'yes', 'y'].includes((s ?? '').trim().toLowerCase())
const band = (n: number): Rating => RATINGS[Math.max(0, Math.min(3, n))]
const dayDiff = (a: string, b: string) => Math.round((Date.parse(a) - Date.parse(b)) / 86400000)

function score(r: Rec, asOf: string, exposureLevel: Rating | null): Priority {
  const tier = num(r.tier), deps = num(r.dependents) ?? 0, kev = num(r.known_exploited_open) ?? 0, open = num(r.open_patches) ?? 0, epss = num(r.max_epss_open)
  const untested = num(r.untested_changes) ?? 0, creds = num(r.credentials_wide) ?? 0, since = num(r.days_since_test), net = yes(r.internet_facing)
  const never = (r.recovery_result ?? '').toLowerCase() === 'never tested'
  const staleRecovery = never || (since !== null && since > THRESHOLDS.recoveryDays)
  const eos = r.end_of_support ? dayDiff(r.end_of_support, asOf) : null
  const notes: string[] = []

  const lk: string[] = []
  let l = 0
  if (kev > 0) { l = 3; lk.push('a known-exploited flaw is open') }
  if (creds > 0) { l = 3; lk.push('a credential is visible beyond its owners or team') }
  if (l < 2 && ((epss ?? 0) >= THRESHOLDS.highEpss)) { l = 2; lk.push(`an open flaw has an exploit score of ${epss}`) }
  if (l < 2 && net && open > 0) { l = 2; lk.push('it is internet-facing with a flaw open') }
  if (l < 1) {
    if ((epss ?? 0) >= THRESHOLDS.midEpss) { l = 1; lk.push(`an open flaw has an exploit score of ${epss}`) }
    if (untested > 0) { l = 1; lk.push('a change skipped pre-production testing') }
    if (eos !== null && eos <= THRESHOLDS.supportDays) { l = 1; lk.push(eos < 0 ? 'vendor support has ended' : `vendor support ends in ${eos} days`) }
    if (staleRecovery) { l = 1; lk.push(never ? 'recovery was never tested' : `the last recovery test was ${since} days ago`) }
  }
  if (since === null && !never) notes.push('No recovery test on record.')

  const im: string[] = []
  let i = tier === 1 ? 2 : tier === 2 ? 1 : 0
  im.push(tier === null ? 'no business tier recorded' : `tier ${tier}`)
  if ((r.data_class ?? '') === 'restricted') { i += 1; im.push('restricted data') }
  if (deps >= THRESHOLDS.manyDependants) { i += 1; im.push(`${deps} dependants`) }
  if (!['production', 'dr'].includes((r.environment ?? '').toLowerCase())) { i -= 1; im.push('not production') }
  i = Math.max(0, Math.min(3, i))

  const triggers: TriggerId[] = []
  if (kev > 0 && net && tier === 1) triggers.push('kev_exposed')
  if (creds > 0) triggers.push('credential_shared')
  if (net && staleRecovery) triggers.push('exposed_untested')
  if (exposureLevel === 'Critical' && num(r.in_scenario) === 1) triggers.push('exposure_critical')

  const base = l + i
  let rating = band(base <= 1 ? 0 : base <= 3 ? 1 : base <= 5 ? 2 : 3)
  const lifted = triggers.length > 0 && (ratingRank(rating) ?? 0) < 2
  if (lifted) rating = 'High'
  const reason = `${rating}: ${band(l)} likelihood (${lk.length ? lk.join(', ') : 'nothing found that raises it'}), ${band(i)} impact (${im.join(', ')}).` +
    (triggers.length ? ` ${lifted ? 'Lifted to High by' : 'Also hit'}: ${triggers.map((t) => TRIGGERS[t]).join(' ')}` : '')
  return { system: r.system, tier, rating, likelihood: band(l), impact: band(i), triggers, lifted, dependents: deps, reason, lossEvent: r.loss_event ?? '', businessImpact: null, notes, likelihoodInputs: lk.join('; ') || 'nothing found that raises it', impactInputs: im.join(', '),
    systemId: r.system_id || null, registered: r.registered_rating ? { rating: r.registered_rating, by: r.registered_by ?? '', at: r.registered_at ?? '' } : null }
}

/** Ranks the systems in the answer. `exposureLevel` is the case's exposure rating when the Exposure screen has been run (it feeds one trigger), else null. */
export function prioritise(t: Table | undefined, opts: { exposureLevel?: Rating | null; asOf?: string } = {}): Priorities {
  if (!t) return { rows: [], ok: false, missing: [...NEEDS], sentence: 'The question was not answered, so there is no list.' }
  const cols = t.columns.map((c) => c.toLowerCase())
  const missing = NEEDS.filter((c) => !cols.includes(c))
  if (missing.length) return { rows: [], ok: false, missing, sentence: `The answer did not have the columns the rules need (${missing.join(', ')}), so there is no list.` }
  const rows = records(t).map((r) => score(r, opts.asOf ?? AS_OF, opts.exposureLevel ?? null))
  rows.sort((a, b) => (ratingRank(b.rating)! - ratingRank(a.rating)!) || (b.triggers.length - a.triggers.length) || (b.dependents - a.dependents) || ((a.tier ?? 9) - (b.tier ?? 9)) || (a.system < b.system ? -1 : a.system > b.system ? 1 : 0))
  const n = (r: Rating) => rows.filter((x) => x.rating === r).length
  return { rows, ok: true, missing: [], sentence: `${rows.length} systems ranked: ${n('Critical')} Critical, ${n('High')} High, ${n('Medium')} Medium, ${n('Low')} Low.` }
}

/** Plain text of the list, for copying into an email or a ticket. */
export function prioritiesText(p: Priorities): string {
  const L = ['Priorities: which systems to fix first (simulated estate, invented data; a method, not a standard)', p.sentence, '']
  p.rows.forEach((r, i) => L.push(`${i + 1}. ${r.system}: ${r.reason}`))
  L.push('', 'Business impact is not scored: it needs the firm\'s own business services.')
  return L.join('\n')
}
