import { describe, expect, it } from 'vitest'
import { columnTitle, plainColumns, splitHeadline, trustChips, visibleColumns, worthKnowing, REASONS } from './answerModel'

const ev = (over: Partial<NonNullable<Parameters<typeof trustChips>[0]['evidence']>> = {}) => ({
  origin: 'question_bank', sources: [{ id: 'pg' }], checks: [{ id: 'dml_safety', status: 'pass' }, { id: 'schema_fidelity', status: 'skipped' }, { id: 'access_check', status: 'pass' }],
  answeredWithoutDataSources: false, warnings: [], elapsedMs: 4000, ...over })

describe('splitHeadline', () => {
  it('takes the first sentence and keeps the rest', () => {
    expect(splitHeadline('Online Banking was assessed most recently. Payments followed two weeks later.')).toEqual({ headline: 'Online Banking was assessed most recently.', rest: 'Payments followed two weeks later.' })
  })
  it('is not fooled by decimals, versions, abbreviations or initials', () => {
    expect(splitHeadline('Revenue was $1.2M in total. Costs were lower.').headline).toBe('Revenue was $1.2M in total.')
    expect(splitHeadline('Version v0.10.23 is out. Upgrade now.').headline).toBe('Version v0.10.23 is out.')
    expect(splitHeadline('Acme Inc. is the largest supplier. Beta follows.').headline).toBe('Acme Inc. is the largest supplier.')
    expect(splitHeadline('J. Smith signed it. Then it was filed.').headline).toBe('J. Smith signed it.')
  })
  it('returns a one-sentence answer, a list or a heading whole', () => {
    expect(splitHeadline('Found 5 results.')).toEqual({ headline: 'Found 5 results.', rest: '' })
    expect(splitHeadline('- one\n- two')).toEqual({ headline: '- one\n- two', rest: '' })
    expect(splitHeadline('# Title\nbody')).toEqual({ headline: '# Title\nbody', rest: '' })
    expect(splitHeadline('')).toEqual({ headline: '', rest: '' })
  })
  it('does not use a first sentence that is too long to be a headline', () => {
    const long = 'x'.repeat(260) + '. Second.'
    expect(splitHeadline(long)).toEqual({ headline: long, rest: '' })
  })
  it('splits at a line break when the first line has no full stop', () => {
    expect(splitHeadline('Three suppliers are late\nThe worst is Beta.')).toEqual({ headline: 'Three suppliers are late', rest: 'The worst is Beta.' })
  })
})

describe('plainColumns', () => {
  it('turns column names in a sentence into words and leaves the rest', () => {
    expect(plainColumns('Found 5 results — first: Atlantic National Bank (usd_amount 75,617,590).')).toBe('Found 5 results — first: Atlantic National Bank (USD amount 75,617,590).')
    expect(plainColumns('Total cash held')).toBe('Total cash held')
  })
})

describe('trustChips', () => {
  it('says an approved answer matches an approved question, names the source, confidence and checks', () => {
    const chips = trustChips({ evidence: ev(), confidence: { score: 90, level: 'high' } })
    expect(chips.map((c) => c.label)).toEqual(['Matches an approved question', 'Source: pg', 'High confidence', '2 checks passed'])
    expect(chips.find((c) => c.id === 'confidence')!.title).toBe('Score 90 of 100')
  })
  it('does not count a skipped check as passed, and names a failing one', () => {
    const chips = trustChips({ evidence: ev({ checks: [{ id: 'row_count', status: 'fail' }, { id: 'x', status: 'fail' }, { id: 'access_check', status: 'pass' }] }) })
    const c = chips.find((x) => x.id === 'checks')!
    expect(c.label).toBe('Row count failed (+1)'); expect(c.tone).toBe('warn')
  })
  it('marks a generated answer plainly and a low confidence as a warning', () => {
    const chips = trustChips({ evidence: ev({ origin: 'generated' }), confidence: { level: 'low' } })
    expect(chips[0]).toMatchObject({ label: 'Written for this question', tone: 'plain' })
    expect(chips.find((c) => c.id === 'confidence')).toMatchObject({ label: 'Low confidence', tone: 'warn' })
  })
  it('handles hidden sources, no source, many sources and a missing evidence block', () => {
    expect(trustChips({ evidence: ev({ sources: [], warnings: ['Source names are hidden for this user.'] }) }).find((c) => c.id === 'sources')!.label).toBe('Sources hidden')
    expect(trustChips({ evidence: ev({ sources: [], answeredWithoutDataSources: true }) }).find((c) => c.id === 'sources')!.label).toBe('No data source used')
    expect(trustChips({ evidence: ev({ sources: ['a', 'b', 'c', 'd', 'e'].map((id) => ({ id })) }) }).find((c) => c.id === 'sources')!.label).toBe('Source: a, b, c +2')
    expect(trustChips({ evidence: null })).toEqual([])
  })
  it('falls back to the answer confidence the Server puts on done', () => {
    expect(trustChips({ evidence: null, answerConfidence: 'High' })).toEqual([expect.objectContaining({ label: 'High confidence' })])
  })
})

describe('worthKnowing', () => {
  it('lists stated assumptions, a cut result and a failed check', () => {
    const w = worthKnowing({ evidence: ev({ checks: [{ id: 'row_count', status: 'fail' }] }), assumptions: ['"Assessed" means the last control test', ' '], truncated: true, rowCap: 10000 })
    expect(w).toEqual(['"Assessed" means the last control test', 'Only the first 10,000 rows are shown; the result was longer.', 'The row count check did not pass.'])
  })
  it('is empty for a clean answer', () => { expect(worthKnowing({ evidence: ev(), confidence: { level: 'high' } })).toEqual([]) })
  it('warns on low confidence', () => { expect(worthKnowing({ evidence: null, confidence: { level: 'low' } })[0]).toMatch(/Confidence is low/) })
})

describe('visibleColumns', () => {
  const cols = ['business_services_id', 'business_services_name', 'last_assessed']
  const rows = [['7', 'Online Banking', '2026-10-01'], ['8', 'Payments', '2026-09-12']]
  it('hides an ID column when another column names the row, and can show it raw', () => {
    expect(visibleColumns(cols, rows, false)).toEqual({ show: [1, 2], hidden: ['business_services_id'] })
    expect(visibleColumns(cols, rows, true)).toEqual({ show: [0, 1, 2], hidden: [] })
  })
  it('keeps an ID when nothing else could name the row', () => {
    expect(visibleColumns(['payment_id', 'usd_amount'], [['29', '100'], ['30', '200']], false).hidden).toEqual([])
    expect(visibleColumns(['id'], [['1']], false).hidden).toEqual([])
  })
  it('does not treat words that merely end in id as IDs', () => {
    expect(visibleColumns(['paid', 'name'], [['y', 'A']], false).hidden).toEqual([])
  })
})

describe('columnTitle and REASONS', () => {
  it('titles names as a person would say them', () => {
    expect(columnTitle('usd_amount')).toBe('USD amount'); expect(columnTitle('entity')).toBe('Entity'); expect(columnTitle('share_pct')).toBe('Share (%)')
  })
  it('offers the Server\'s five reasons', () => { expect(REASONS.map((r) => r[0])).toEqual(['WRONG_DATA', 'WRONG_CALCULATION', 'MISREAD_QUESTION', 'WRONG_TIME_PERIOD', 'PRESENTATION']) })
})
