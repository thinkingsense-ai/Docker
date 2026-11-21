import { describe, expect, it } from 'vitest'
import { RATINGS, atLeast, higher, ratingFor, ratingRank } from './rating'

describe('the rating scale', () => {
  it('has the four values Leo asked for, lowest first, and no "Moderate"', () => {
    expect([...RATINGS]).toEqual(['Low', 'Medium', 'High', 'Critical'])
    expect(ratingRank('Moderate')).toBeNull()
  })
  it('maps a 0 to 3 score to a rating and refuses anything else', () => {
    expect([0, 1, 2, 3].map(ratingFor)).toEqual(['Low', 'Medium', 'High', 'Critical'])
    expect([null, undefined, -1, 4, 1.5].map((s) => ratingFor(s as number))).toEqual([null, null, null, null, null])
  })
  it('compares ratings and treats an unknown value as not comparable', () => {
    expect(atLeast('High', 'Medium')).toBe(true); expect(atLeast('Low', 'Medium')).toBe(false); expect(atLeast('Critical', 'Critical')).toBe(true)
    expect(atLeast('Severe', 'Low')).toBe(false); expect(atLeast('Low', 'Severe')).toBe(false)
  })
  it('takes the more severe of two, and the other when one is missing', () => {
    expect(higher('Low', 'High')).toBe('High'); expect(higher('High', 'Medium')).toBe('High'); expect(higher(null, 'Low')).toBe('Low'); expect(higher(null, null)).toBeNull()
  })
})
