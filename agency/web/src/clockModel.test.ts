import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { CLOCKS_QUESTIONS, computeClocks, iso, leftText, parseTs, type ClockRule, type Decision } from './clockModel'

const read = (p: string) => JSON.parse(readFileSync(new URL(p, import.meta.url), 'utf8'))
type Case = { name: string; rules: ClockRule[]; declared: string[]; decision: Decision | null; now: string; state: string; expect: [string, string, string][] }
const gold = read('../../../demos/it-risk-register/clocks_gold.json') as { cases: Case[] }

describe('gold set', () => {
  for (const c of gold.cases) {
    it(c.name, () => {
      const r = computeClocks(c.rules, c.declared, c.decision, parseTs(c.now)!)
      expect(r.state).toBe(c.state)
      expect(r.clocks.map((x) => [x.rule_id, x.due_at, x.state])).toEqual(c.expect)
    })
  }
})

describe('the clocks', () => {
  it('asks the approved questions word for word', () => {
    const bank = read('../../../demos/it-risk-register/demo-questions-register.json') as { question: string }[]
    for (const q of Object.values(CLOCKS_QUESTIONS)) expect(bank.map((b) => b.question)).toContain(q)
  })
  it('reads timestamps as UTC, with or without a zone', () => {
    expect(iso(parseTs('2026-11-20 08:15:00.0')!)).toBe('2026-11-20T08:15:00Z')
    expect(iso(parseTs('2026-11-20T09:00:00+02:00')!)).toBe('2026-11-20T07:00:00Z')
    expect(parseTs('soon')).toBeNull(); expect(parseTs(null)).toBeNull()
  })
  it('flags the later DORA stages as depending on when the earlier report is sent, and an initial deadline already past', () => {
    const c = gold.cases[2]; const r = computeClocks(c.rules, c.declared, c.decision, parseTs(c.now)!)
    expect(r.clocks[1].flags).toContain('depends on when the previous report is sent'); expect(r.clocks[0].basis).toMatch(/24 hours after the firm became aware/)
    expect(r.clocks[0].flags).toContain('already past when it was recorded as major')
    const ok = gold.cases[0]; expect(computeClocks(ok.rules, ok.declared, ok.decision, 0).clocks[0].flags).toEqual([])      // 4 hours after the decision is in the future when it is recorded
  })
  it('words the time left', () => {
    expect(leftText(3 * 3600 + 20 * 60)).toBe('3 h 20 min left'); expect(leftText(-(2 * 86400 + 4 * 3600))).toBe('overdue by 2 days 4 h'); expect(leftText(90)).toBe('1 min left'); expect(leftText(null)).toBe('no deadline')
  })
})
