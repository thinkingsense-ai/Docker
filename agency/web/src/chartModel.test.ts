import { describe, expect, it } from 'vitest'
import { classify, compact, describePlan, dropRaw, niceTicks, planChart, statTiles } from './chartModel'

const payments = {
  columns: ['payment_id', 'entity', 'amount', 'currency', 'amount_usd', 'value_date', 'initiated_by'],
  rows: [['35', 'Meridian Europe GmbH', '481481.48', 'EUR', '520000.00', '2026-11-19', 'treasury-agent'], ['33', 'Meridian Europe GmbH', '466042.64', 'EUR', '503326.05', '2026-11-18', 'a.tanaka'],
         ['31', 'Meridian Europe GmbH', '309370.76', 'EUR', '334120.42', '2026-11-19', 'a.tanaka'], ['30', 'Meridian Japan KK', '47448631.04', 'JPY', '313160.96', '2026-11-21', 'a.tanaka'],
         ['32', 'Meridian Japan KK', '37851529.19', 'JPY', '249820.09', '2026-11-21', 'treasury-agent'], ['29', 'Meridian Asia Pte', '160662.57', 'USD', '160662.57', '2026-11-21', 'a.tanaka'],
         ['34', 'Meridian Asia Pte', '32304.26', 'SGD', '23905.15', '2026-11-21', 'treasury-agent']] as (string | null)[][],
}

describe('classify', () => {
  it('tells ids from measures, dates from text', () => {
    expect(classify(payments.columns, payments.rows)).toEqual(['id', 'text', 'measure', 'text', 'measure', 'date', 'text'])
  })
  it('does not treat an empty column as anything', () => { expect(classify(['a'], [[null], ['']])).toEqual(['empty']) })
})

describe('dropRaw', () => {
  it('keeps the normalised column beside a raw one', () => { expect(dropRaw(['amount', 'amount_usd', 'fees'])).toEqual(['amount_usd', 'fees']) })
  it('leaves unrelated names alone', () => { expect(dropRaw(['amount', 'count'])).toEqual(['amount', 'count']) })
})

describe('planChart on a payments list', () => {
  const p = planChart(payments.columns, payments.rows)!
  it('plots the usd amount, not the mixed-currency one or the ids, sorted high to low', () => {
    expect(p.measures.map((m) => m.name)).toEqual(['amount_usd']); expect(p.measures[0].values[0]).toBe(520000); expect(p.measures[0].values).toEqual([...p.measures[0].values].sort((a, b) => b - a))
  })
  it('labels an id with the entity beside it, and goes horizontal for long labels', () => { expect(p.labels[0]).toBe('35 · Meridian Europe GmbH'); expect(p.horizontal).toBe(true); expect(p.category).toBe(0) })
  it('offers only bars for seven slices (a donut has six colours)', () => { expect(p.options).toEqual(['bar']) })
  it('offers a donut for six or fewer positive rows with one measure', () => { expect(planChart(['k', 'v'], [['a', '5'], ['b', '3'], ['c', '2'], ['d', '1'], ['e', '1'], ['f', '1']])!.options).toEqual(['bar', 'donut']) })
  it('lets the person pick another measure and kind', () => {
    const q = planChart(['k', 'v'], [['a', '5'], ['b', '3']], { kind: 'donut' })!; expect(q.kind).toBe('donut'); expect(planChart(payments.columns, payments.rows, { kind: 'donut' })!.kind).toBe('bar')
    expect(p.candidates).toContain('amount_usd'); expect(p.candidates).not.toContain('amount')
  })
})

describe('planChart: other shapes', () => {
  it('a date column makes a line in date order', () => {
    const p = planChart(['day', 'orders'], [['2026-11-01', '5'], ['2026-11-02', '9'], ['2026-11-03', '4']])!
    expect(p.kind).toBe('line'); expect(p.labels).toEqual(['2026-11-01', '2026-11-02', '2026-11-03']); expect(p.options).toEqual(['line', 'bar'])
  })
  it('a unique text column and a number make a bar chart sorted high to low', () => {
    const p = planChart(['region', 'sales'], [['East', '10'], ['West', '30'], ['North', '20']])!; expect(p.labels).toEqual(['West', 'North', 'East'])
  })
  it('measures that differ by orders of magnitude get panels of their own', () => {
    const p = planChart(['region', 'revenue', 'orders'], [['East', '9000000', '12'], ['West', '4000000', '8']])!; expect(p.panels).toBe(true)
    expect(planChart(['region', 'a', 'b'], [['East', '10', '12'], ['West', '4', '8']])!.panels).toBe(false)
  })
  it('keeps the top 12 of a long list and says so', () => {
    const rows = Array.from({ length: 30 }, (_, i) => [`item ${i}`, String(i)]); const p = planChart(['item', 'n'], rows)!
    expect(p.labels.length).toBe(12); expect(p.omitted).toBe(18); expect(p.note).toMatch(/top 12 of 30/); expect(p.measures[0].values[0]).toBe(29)
  })
  it('draws nothing when it would be a guess', () => {
    expect(planChart(['a', 'b'], [['x', '1']])).toBeNull()                                                             // one row
    expect(planChart(['a', 'b'], Array.from({ length: 101 }, (_, i) => [`r${i}`, '1']))).toBeNull()                    // too many
    expect(planChart(['a', 'b'], [['x', 'p'], ['y', 'q']])).toBeNull()                                                  // no number
    expect(planChart(['a', 'b', 'v'], [['x', 'p', '1'], ['x', 'q', '2'], ['y', 'q', '3']])).toBeNull()                  // two text columns, none unique: which is the category?
    expect(planChart(['id', 'n'], [['1', '5'], ['2', '6']])!.labels).toEqual(['2', '1'])                                // ids alone can still label bars
  })
  it('does not call negatives a donut', () => { expect(planChart(['k', 'v'], [['a', '5'], ['b', '-3']])!.options).toEqual(['bar']) })
})

describe('compact, ticks, description, stats', () => {
  it('shortens big numbers for axes only', () => {
    expect([compact(520000), compact(1500), compact(3400000), compact(12), compact(0.256), compact(-2500000), compact(999)]).toEqual(['520K', '1.5K', '3.4M', '12', '0.256', '-2.5M', '999'])
  })
  it('gives round ticks starting at zero', () => { expect(niceTicks(0, 520000)).toEqual([0, 200000, 400000, 600000]); expect(niceTicks(0, 0)).toEqual([0, 1]); expect(niceTicks(3, 3)).toEqual([0, 1, 2, 3]) })
  it('describes the chart for a screen reader', () => {
    const p = planChart(payments.columns, payments.rows)!; expect(describePlan(p, payments.columns)).toMatch(/^Horizontal bar chart of amount_usd by payment_id, 7 rows\. The highest amount_usd is 520K for 35 · Meridian Europe GmbH\.$/)
  })
  it('shows a single row of numbers as large tiles', () => {
    expect(statTiles(['total_liquidity_usd', 'accounts'], [['1250000.50', '12']])).toEqual([{ label: 'total_liquidity_usd', value: '1250000.50' }, { label: 'accounts', value: '12' }])
    expect(statTiles(['name'], [['x']])).toBeNull(); expect(statTiles(['a', 'b'], [['1', '2'], ['3', '4']])).toBeNull()
  })
})
