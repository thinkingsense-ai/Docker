import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { QUESTIONS, THRESHOLDS, exposureText, rate, type Key } from './exposureModel'
import type { Table } from './rcaBrief'

const read = (p: string) => JSON.parse(readFileSync(new URL(p, import.meta.url), 'utf8'))
const gold = read('../../../demos/it-risk-estate/exposure_gold.json') as { cases: { name: string; answers: Partial<Record<Key, Table>>; scores: (number | null)[]; level: string | null; setBy: number[]; unknown?: number[] }[] }

describe('gold set', () => {
  for (const c of gold.cases) {
    it(c.name, () => {
      const r = rate(c.answers)
      expect(r.scores.map((s) => s.score)).toEqual(c.scores)
      expect(r.level).toBe(c.level)
      expect(r.setBy).toEqual(c.setBy)
      expect(r.unknown).toEqual(c.unknown ?? [])
    })
  }
})

describe('the questions and the rating', () => {
  it('asks exactly the approved questions, in order, so the question bank matches them', () => {
    const bank = read('../../../demos/it-risk-estate/demo-questions-estate.json') as { question: string }[]
    expect(QUESTIONS.map((q) => q.text)).toEqual(bank.map((b) => b.question))
  })
  it('the overall rating is the highest score and names every question that set it', () => {
    const r = rate(gold.cases[0].answers)
    expect(r.level).toBe('Critical'); expect(r.setBy).toEqual([4, 5]); expect(r.sentence).toBe('Critical: set by questions 4 and 5.')
  })
  it('says the rating may be higher when a question is unknown, and never calls an unknown 0', () => {
    const r = rate(gold.cases[11].answers)
    expect(r.complete).toBe(false); expect(r.scores[2].score).toBeNull(); expect(r.scores[2].label).toBe('Unknown')
    expect(r.sentence).toBe('At least Moderate: set by question 1; question 3 could not be scored, so the rating may be higher.')
  })
  it('gives each score a reason, the rows behind it and its rule', () => {
    const r = rate(gold.cases[0].answers)
    const q4 = r.scores[3]
    expect(q4.reason).toMatch(/Domain controllers.*overdue by more than 15 days.*skipped pre-production testing/)
    expect(q4.rows.rows.length).toBeGreaterThan(0); expect(q4.rule).toMatch(/15 days/)
    expect(r.scores[4].reason).toMatch(/Payment gateway \(production\).*212 days/)
  })
  it('keeps the thresholds the user set: 15 days for a patch, 180 days for a recovery test', () => {
    expect(THRESHOLDS.patchDays).toBe(15); expect(THRESHOLDS.recoveryDays).toBe(180)
  })
  it('writes a plain-text copy that carries the rating and the thresholds', () => {
    const t = exposureText(rate(gold.cases[0].answers))
    expect(t).toMatch(/Critical: set by questions 4 and 5/); expect(t).toMatch(/simulated estate/); expect(t).toMatch(/more than 15 days/)
  })
})
