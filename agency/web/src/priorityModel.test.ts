import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { PRIORITY_QUESTION, THRESHOLDS, prioritise, prioritiesText, type TriggerId } from './priorityModel'
import type { Table } from './rcaBrief'

const read = (p: string) => JSON.parse(readFileSync(new URL(p, import.meta.url), 'utf8'))
type Case = { name: string; answer: Table; exposureLevel?: 'Critical'; ok?: boolean; order: string[]; ratings: string[]; triggers: Record<string, TriggerId[]>; lifted?: string[] }
const gold = read('../../../demos/it-risk-estate/priority_gold.json') as { cases: Case[] }

describe('gold set', () => {
  for (const c of gold.cases) {
    it(c.name, () => {
      const p = prioritise(c.answer, { exposureLevel: c.exposureLevel ?? null })
      expect(p.ok).toBe(c.ok ?? true)
      expect(p.rows.map((r) => r.system)).toEqual(c.order)
      expect(p.rows.map((r) => r.rating)).toEqual(c.ratings)
      for (const r of p.rows) expect(r.triggers).toEqual(c.triggers[r.system] ?? [])
      for (const r of p.rows) expect(r.lifted).toBe((c.lifted ?? []).includes(r.system))
    })
  }
})

describe('the list', () => {
  it('asks the approved question word for word', () => {
    const bank = read('../../../demos/it-risk-estate/demo-questions-priorities.json') as { question: string }[]
    expect(bank.map((b) => b.question)).toEqual([PRIORITY_QUESTION])
  })
  it('gives each row a reason with both bands, and leaves business impact empty', () => {
    const p = prioritise(gold.cases[0].answer)
    expect(p.rows[0].reason).toMatch(/^Critical: Critical likelihood \(a known-exploited flaw is open\), Critical impact \(tier 1, 4 dependants\)\./)
    expect(p.rows.every((r) => r.businessImpact === null)).toBe(true)
    expect(p.sentence).toBe('11 systems ranked: 1 Critical, 2 High, 6 Medium, 2 Low.')
  })
  it('says a lift came from a trigger', () => {
    const r = prioritise(gold.cases[6].answer).rows[0]
    expect(r.reason).toMatch(/Lifted to High by: A credential is visible beyond its owners or team\./)
  })
  it('notes a missing recovery record instead of treating it as never tested', () => {
    expect(prioritise(gold.cases[8].answer).rows[0].notes).toEqual(['No recovery test on record.'])
  })
  it('refuses a missing or column-less answer, never ranking from nothing', () => {
    expect(prioritise(undefined).ok).toBe(false)
    expect(prioritise(gold.cases[13].answer).missing).toContain('internet_facing')
  })
  it('copies as text with the method note', () => {
    expect(prioritiesText(prioritise(gold.cases[0].answer))).toMatch(/a method, not a standard/)
    expect(THRESHOLDS.recoveryDays).toBe(180)
  })
})
