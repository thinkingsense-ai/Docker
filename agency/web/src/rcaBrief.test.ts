import { describe, expect, it } from 'vitest'
import { briefText, composeBrief, headline, records, type Answers } from './rcaBrief'

const t = (columns: string[], rows: (string | null)[][]) => ({ columns, rows })
// The rows the approved questions return on the local stack (demos/it-risk-rca), kept here so the brief is tested without a Server.
const answers = (): Answers => ({
  causes: t(['operator', 'cause', 'grade', 'sources'], [
    ['Microsoft 365', 'A Windows defect introduced in July', 'confirmed', '1'], ['FAA', 'Two official accounts differ', 'disputed', '2'],
    ['JPMorgan Chase', 'A software bug in on-premise hardware', 'confirmed', '1'], ['United Airlines', 'United has not named a cause', 'not_named', '1'],
    ['NSA (NSANet)', 'Scheduled routine maintenance.', 'confirmed', '1'], ['Apple', 'An internal update', 'confirmed', '1']]),
  open: t(['layer', 'statement', 'grade', 'reason'], [['driver', 'AI is finding vulnerabilities faster', 'inferred', 'Our reasoning'], ['root_condition', 'Change and test capacity', 'to_be_tested', 'Needs the firm records']]),
  verdict: t(['claim', 'verdict', 'open_incidents', 'note'], [['The November outages are AI hacking.', 'not_supported', '2', '']]),
  controls: t(['case_id', 'root_condition', 'grade', 'owning_control', 'owner_role', 'framework', 'category'], [
    ['nov-2026-cluster', 'Change and test capacity', 'to_be_tested', 'Change management and pre-production testing', 'Head of technology risk', 'NIST CSF 2.0', 'PR.PS Platform Security']]),
  speakers: t(['operator', 'speaker', 'speaker_kind', 'publisher', 'url'], [
    ['Microsoft 365', 'Microsoft', 'operator', 'BleepingComputer', 'u'], ['JPMorgan Chase', 'JPMorgan Chase', 'operator', 'CNBC', 'u'],
    ['NSA (NSANet)', 'NSA, via people familiar', 'reporting', 'Nextgov', 'u'], ['Apple', 'Apple', 'operator', 'TechCrunch', 'u']]),
})

describe('composeBrief', () => {
  it('reproduces the specification: causes confirmed for 4 of 6, five stated, two open', () => {
    const b = composeBrief(answers())
    expect(b.counts).toMatchObject({ total: 6, confirmed: 4, stated: 5 })
    expect(b.counts.openIncidents.map((i) => i.operator)).toEqual(['FAA', 'United Airlines'])
    expect(headline(b)).toBe('4 of 6 causes are confirmed, 5 of 6 are stated, and no official source points to an attack. 2 stay open. 1 confirmed grade is higher than the sources support.')
    expect(b.incidents.find((i) => i.operator === 'NSA (NSANet)')?.supported).toBe('stated')
    expect(b.incidents.filter((i) => i.supported)).toHaveLength(1)
  })
  it('names every open incident in the verdict sentence, with its grade (the costliest error)', () => {
    const b = composeBrief(answers())
    expect(b.claim?.sentence).toBe('No official source attributes any of the 6 incidents to an attack, but FAA (disputed) and United Airlines (not named) are still open.')
    expect(b.checks.find((c) => c.rule.includes('flat'))?.ok).toBe(true)
  })
  it('flags a confirmed cause whose only source is reporting (NSANet), which the specification grades confirmed', () => {
    const c = composeBrief(answers()).checks.find((x) => x.rule.startsWith('Confirmed means'))!
    expect(c.ok).toBe(false); expect(c.detail).toMatch(/NSA \(NSANet\) cause is graded confirmed but its sources support stated/)
  })
  it('refuses a cause with no source unless it is inferred', () => {
    const a = answers(); a.causes!.rows[0][3] = '0'
    const c = composeBrief(a).checks.find((x) => x.rule === 'No cause without evidence')!
    expect(c.ok).toBe(false); expect(c.detail).toMatch(/Microsoft 365/)
  })
  it('does not claim "no attack" when the verdict is not not_supported', () => {
    const a = answers(); a.verdict!.rows[0][1] = 'insufficient_evidence'
    expect(headline(composeBrief(a))).toMatch(/cannot be tested yet/)
  })
  it('fails the verdict rule, and says why, when the verdict is missing', () => {
    const c = composeBrief({ ...answers(), verdict: undefined }).checks.find((k) => k.rule.includes('flat'))!
    expect(c.ok).toBe(false); expect(c.detail).toMatch(/missing/)
  })
  it('is incomplete, and says so, when an answer is missing', () => {
    const b = composeBrief({ ...answers(), verdict: undefined })
    expect(b.complete).toBe(false); expect(headline(b)).toMatch(/could not be completed/)
  })
  it('turns an answer into records by lower-cased column name and writes a plain-text copy', () => {
    expect(records(t(['Operator'], [['x']]))[0].operator).toBe('x')
    const txt = briefText(composeBrief(answers()))
    expect(txt).toMatch(/Control to fix:/); expect(txt).toMatch(/Checks that failed:/)
  })
})
