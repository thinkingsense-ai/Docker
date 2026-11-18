import { describe, expect, it } from 'vitest'
import { pickStarters, TOP } from './StarterTiles'
import type { Starter } from './api'

const q = (n: number, origin: Starter['origin'] = 'approved'): Starter => ({ question: `q${n}`, origin })

describe('pickStarters', () => {
  it('shows the first five approved questions and counts the rest', () => {
    const r = pickStarters(Array.from({ length: 24 }, (_, i) => q(i)), false)
    expect(r.shown.map((s) => s.question)).toEqual(['q0', 'q1', 'q2', 'q3', 'q4']); expect(r.total).toBe(24); expect(r.approved).toBe(24); expect(TOP).toBe(5)
  })
  it('puts approved before suggested, keeping each group in the Server order', () => {
    const r = pickStarters([q(1, 'suggested'), q(2), q(3, 'suggested'), q(4)], false, 3); expect(r.shown.map((s) => s.question)).toEqual(['q2', 'q4', 'q1'])
  })
  it('shows everything on request', () => { expect(pickStarters(Array.from({ length: 24 }, (_, i) => q(i)), true).shown.length).toBe(24) })
  it('copes with none and with fewer than five', () => {
    expect(pickStarters([], false)).toEqual({ shown: [], total: 0, approved: 0 }); expect(pickStarters([q(1), q(2)], false).shown.length).toBe(2)
  })
})
