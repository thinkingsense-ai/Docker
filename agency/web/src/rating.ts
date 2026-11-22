// The one rating scale on every screen (docs/agency-risk-register-plan.md, section 1): four values, Critical, High, Medium, Low, as Leo asked.
// "Level" means this and nothing else on screen; the position in the taxonomy is called a category, and an ITIL incident priority (P1 to P4) is not shown. Pure, so it is unit-tested.
export const RATINGS = ['Low', 'Medium', 'High', 'Critical'] as const
export type Rating = (typeof RATINGS)[number]

/** Position on the scale, 0 (Low) to 3 (Critical); null for a value that is not on the scale. */
export const ratingRank = (r: string | null | undefined): number | null => { const i = RATINGS.indexOf(r as Rating); return i < 0 ? null : i }
/** The rating for a 0 to 3 score, or null when the score is missing or out of range. */
export const ratingFor = (score: number | null | undefined): Rating | null => (score === null || score === undefined || !Number.isInteger(score) || score < 0 || score > 3 ? null : RATINGS[score])
/** True when `a` is at least as severe as `b`; false if either is not on the scale. */
export const atLeast = (a: string, b: string): boolean => { const x = ratingRank(a), y = ratingRank(b); return x !== null && y !== null && x >= y }
/** The more severe of two ratings (an unknown one yields the other). */
export const higher = (a: Rating | null, b: Rating | null): Rating | null => (a === null ? b : b === null ? a : ratingRank(a)! >= ratingRank(b)! ? a : b)
