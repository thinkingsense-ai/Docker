import { describe, expect, it } from 'vitest'
import { composeSources, health, parseWhen, summaryLine } from './sourcesModel'

const NOW = new Date('2026-11-20T12:00:00Z')
const t = (rows: (string | null)[][]) => ({ columns: ['source', 'kind', 'last_status', 'last_success_at', 'items_last_run', 'items_total', 'matched_total', 'last_error'], rows })
const row = (name: string, kind: string, status: string, ok: string | null, err = ''): (string | null)[] => [name, kind, status, ok, '10', '120', '4', err]

describe('parseWhen', () => {
  it('reads the Server timestamp as UTC, with or without a T or a zone', () => {
    expect(parseWhen('2026-11-20 10:30:00')?.toISOString()).toBe('2026-11-20T10:30:00.000Z')
    expect(parseWhen('2026-11-20T10:30:00')?.toISOString()).toBe('2026-11-20T10:30:00.000Z')
    expect(parseWhen('2026-11-20T10:30:00+01:00')?.toISOString()).toBe('2026-11-20T09:30:00.000Z')
  })
  it('turns nothing and rubbish into no date, never a wrong one', () => { expect(parseWhen('')).toBeNull(); expect(parseWhen(undefined)).toBeNull(); expect(parseWhen('soon')).toBeNull() })
})

describe('composeSources', () => {
  it('lists reporting feeds first, then official, then context, each by name', () => {
    const s = composeSources(t([row('Zeta', 'context', 'ok', null), row('Beta', 'official', 'ok', null), row('Alpha', 'reporting', 'ok', null), row('Gamma', 'reporting', 'ok', null)]))
    expect(s.map((x) => x.name)).toEqual(['Alpha', 'Gamma', 'Beta', 'Zeta'])
  })
})

describe('health', () => {
  const h = (r: (string | null)[]) => health(composeSources(t([r]))[0], NOW)
  it('is ok for a feed that answered within three polls', () => expect(h(row('A', 'reporting', 'ok', '2026-11-20 11:40:00'))).toMatchObject({ state: 'ok', text: 'Answered 20 minutes ago.' }))
  it('treats not-modified as an answer', () => expect(h(row('A', 'reporting', 'not_modified', '2026-11-20 11:50:00')).state).toBe('ok'))
  it('says "not updated since" when the last answer is older than three polls', () => expect(h(row('A', 'reporting', 'ok', '2026-11-20 08:00:00'))).toMatchObject({ state: 'late' }))
  it('names a failure and still says when it last answered', () => {
    const x = h(row('A', 'official', 'unreachable', '2026-11-20 11:00:00', 'The read operation timed out'))
    expect(x.state).toBe('failing'); expect(x.text).toContain('The read operation timed out'); expect(x.text).toContain('last answered 60 minutes ago')
  })
  it('says so when a feed has never answered, and when robots.txt forbids it', () => {
    expect(h(row('A', 'reporting', 'unreachable', null, 'boom')).text).toContain('has never answered')
    expect(h(row('A', 'reporting', 'blocked_by_robots', null)).state).toBe('blocked')
    expect(h(row('A', 'reporting', '', null)).state).toBe('never')
  })
})

describe('summaryLine', () => {
  it('says the adapter is not running when there are no rows, not that all is well', () => expect(summaryLine([], NOW)).toMatchObject({ ok: false }))
  it('says all healthy only when every feed is', () => expect(summaryLine(composeSources(t([row('A', 'reporting', 'ok', '2026-11-20 11:50:00'), row('B', 'context', 'ok', '2026-11-20 11:55:00')])), NOW)).toEqual({ ok: true, text: 'All 2 feeds answered recently.' }))
  it('names the feeds that are not healthy', () => {
    const s = summaryLine(composeSources(t([row('A', 'reporting', 'ok', '2026-11-20 11:50:00'), row('Zscaler', 'reporting', 'unreachable', '2026-11-20 06:00:00', 'timeout')])), NOW)
    expect(s.ok).toBe(false); expect(s.text).toBe('1 of 2 feeds answered recently. Not healthy: Zscaler.')
  })
})
