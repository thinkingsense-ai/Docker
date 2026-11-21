import { describe, expect, it } from 'vitest'
import { actionFor, claimLabel, composeWatch, statusText } from './watchModel'

const cols = ['candidate_id', 'title', 'claim_type', 'status', 'first_seen', 'summary', 'verdict', 'open_incidents', 'incidents', 'sources']
const rows = [
  ['2', 'A model breaks out of its sandbox', 'ai-adjacent', 'traced', '2026-07-01', 's2', 'insufficient_evidence', '0', '1', '1'],
  ['1', 'Six outages in six days, said to be AI hacking', 'ai-attack-claimed', 'traced', '2026-11-12', 's1', 'not_supported', '2', '6', '8'],
]

describe('composeWatch', () => {
  it('lists the newest candidate first and reads counts as numbers', () => {
    const c = composeWatch({ columns: cols, rows })
    expect(c.map((x) => x.id)).toEqual(['1', '2'])
    expect(c[0]).toMatchObject({ incidents: 6, sources: 8, openIncidents: 2, status: 'traced' })
  })
  it('treats an unknown status as not yet traced, so nothing looks tested that is not', () => {
    const r = [...rows[0]]; r[3] = 'something-else'
    expect(composeWatch({ columns: cols, rows: [r] })[0].status).toBe('not_yet_traced')
  })
  it('gives an empty list for no answer', () => { expect(composeWatch(undefined)).toEqual([]) })
})

describe('actions and wording', () => {
  const [nov, jul] = composeWatch({ columns: cols, rows })
  it('opens the brief for the claimed-attack case and reads the other layer by layer', () => {
    expect(actionFor(nov)).toEqual({ kind: 'brief' })
    expect(actionFor(jul)).toMatchObject({ kind: 'ask', question: 'How does the July 2026 breakout read, layer by layer?' })
  })
  it('does not offer to open anything for an untraced candidate', () => {
    expect(actionFor({ ...nov, status: 'not_yet_traced' }).kind).toBe('wait')
    expect(statusText({ ...nov, status: 'not_yet_traced' })).toBe('Claim not yet tested')
  })
  it('spells out the claim type and counts', () => {
    expect(claimLabel('ai-attack-claimed')).toBe('AI attack claimed'); expect(claimLabel('x')).toBe('x')
    expect(statusText(nov)).toBe('Traced: 6 incidents, 8 sources'); expect(statusText(jul)).toBe('Traced: 1 incident, 1 source')
  })
})

describe('feed candidates', () => {
  const cols = ['candidate_id', 'title', 'claim_type', 'status', 'first_seen', 'summary', 'verdict', 'open_incidents', 'incidents', 'sources', 'lead_source', 'lead_url']
  const row = (url: string | null): (string | null)[] => ['1001', 'FAA ground stop: AI hackers', 'ai-attack-claimed', 'not_yet_traced', '2026-11-20', 's', null, null, '0', '2', 'SecurityWeek', url]
  it('keeps the lead headline link for a candidate the feed created', () => {
    const c = composeWatch({ columns: cols, rows: [row('https://example.com/a')] })[0]
    expect(c).toMatchObject({ status: 'not_yet_traced', sources: 2, leadSource: 'SecurityWeek', leadUrl: 'https://example.com/a' })
    expect(actionFor(c).kind).toBe('wait'); expect(statusText(c)).toBe('Claim not yet tested')
  })
  it('never makes a link of anything that is not an http or https address (a feed is outside data)', () => {
    for (const bad of ['javascript:alert(1)', 'data:text/html,x', '//evil.example', 'https://a b', '']) expect(composeWatch({ columns: cols, rows: [row(bad)] })[0].leadUrl, bad).toBe('')
    expect(composeWatch({ columns: cols, rows: [row(null)] })[0].leadUrl).toBe('')
  })
  it('still reads a list without the lead columns (an older stack)', () => {
    const c = composeWatch({ columns: cols.slice(0, 10), rows: [row('x').slice(0, 10)] })[0]; expect(c.leadUrl).toBe(''); expect(c.leadSource).toBe('')
  })
})
