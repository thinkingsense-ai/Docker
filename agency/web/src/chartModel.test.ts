import { describe, expect, it } from 'vitest'
import { classify, compact, describePlan, dropRaw, isRanking, niceTicks, planChart, statTiles } from './chartModel'

type Rows = (string | null)[][]
const payments = {
  columns: ['payment_id', 'entity', 'amount', 'currency', 'amount_usd', 'value_date', 'initiated_by'],
  rows: [['35', 'Meridian Europe GmbH', '481481.48', 'EUR', '520000.00', '2026-11-19', 'treasury-agent'], ['33', 'Meridian Europe GmbH', '466042.64', 'EUR', '503326.05', '2026-11-18', 'a.tanaka'],
         ['31', 'Meridian Europe GmbH', '309370.76', 'EUR', '334120.42', '2026-11-19', 'a.tanaka'], ['30', 'Meridian Japan KK', '47448631.04', 'JPY', '313160.96', '2026-11-21', 'a.tanaka']] as Rows,
}
const carriers = { columns: ['carrier', 'shipments'], rows: [['DHL', '40'], ['FedEx', '25'], ['UPS', '20'], ['Maersk', '10'], ['Other', '5']] as Rows }
const forecast = { columns: ['entity', 'avg_forecast_error_pct'], rows: [['Europe', '18.2'], ['Japan', '9.1'], ['Asia', '16.4'], ['US', '4.0']] as Rows }
const days = (n: number): Rows => Array.from({ length: n }, (_, i) => [`2026-11-${String(i + 1).padStart(2, '0')}`, String(10 + ((i * 7) % 13))])

describe('classify', () => {
  it('tells ids from measures, dates from text', () => { expect(classify(payments.columns, payments.rows)).toEqual(['id', 'text', 'measure', 'text', 'measure', 'date', 'text']) })
  it('does not treat an empty column as anything', () => { expect(classify(['a'], [[null], ['']])).toEqual(['empty']) })
})

describe('dropRaw', () => {
  it('keeps the normalised column beside a raw one', () => { expect(dropRaw(['amount', 'amount_usd', 'fees'])).toEqual(['amount_usd', 'fees']) })
  it('leaves unrelated names alone', () => { expect(dropRaw(['amount', 'count'])).toEqual(['amount', 'count']) })
})

describe('what is worth drawing', () => {
  it('a listing of records is read, not drawn: no chart for the payments list', () => { expect(planChart(payments.columns, payments.rows)).toBeNull() })
  it('two rows are easier to read than to draw', () => { expect(planChart(['k', 'v'], [['a', '5'], ['b', '3']])).toBeNull() })
  it('a name, one descriptive column and a number is a comparison and is drawn', () => {
    const p = planChart(['supplier', 'country', 'spend'], [['Acme', 'DE', '90'], ['Beta', 'FR', '40'], ['Gamma', 'US', '70']])!; expect(p.intent).toBe('comparison'); expect(p.labels).toEqual(['Acme', 'Gamma', 'Beta'])
  })
  it('three descriptive columns make it a listing', () => { expect(planChart(['a', 'b', 'c', 'd', 'n'], [['x1', 'p', 'q', 'r', '1'], ['x2', 'p', 'q', 'r', '2'], ['x3', 'p', 'q', 'r', '3']])).toBeNull() })
  it('draws nothing when it would be a guess', () => {
    expect(planChart(['a', 'b'], [['x', '1']])).toBeNull()
    expect(planChart(['a', 'b'], Array.from({ length: 101 }, (_, i) => [`r${i}`, '1']))).toBeNull()
    expect(planChart(['a', 'b'], [['x', 'p'], ['y', 'q'], ['z', 'r']])).toBeNull()
    expect(planChart(['a', 'b', 'v'], [['x', 'p', '1'], ['x', 'q', '2'], ['y', 'q', '3']])).toBeNull()
  })
})

describe('only the views that fit the answer are offered', () => {
  it('amounts that add up across categories: bars, or a donut', () => { const p = planChart(carriers.columns, carriers.rows)!; expect(p.kind).toBe('bar'); expect(p.options).toEqual(['bar', 'donut']); expect(p.intent).toBe('comparison') })
  it('an average, rate or score is never offered as parts of a whole', () => { expect(planChart(forecast.columns, forecast.rows)!.options).toEqual(['bar']) })
  it('a ranking (the top of a longer list) is not parts of a whole', () => {
    expect(planChart(carriers.columns, carriers.rows, { question: 'Which carrier ships the most?' })!.options).toEqual(['bar']); expect(planChart(carriers.columns, carriers.rows, { question: 'How many shipments does each carrier have?' })!.options).toEqual(['bar', 'donut'])
    expect([isRanking('Top 5 suppliers'), isRanking('Which suppliers do we hold the most stock from?'), isRanking('Show headroom, tightest first'), isRanking('How many shipments does each carrier have?'), isRanking(undefined)]).toEqual([true, true, true, false, false])
  })
  it('more than six categories is bars only', () => { expect(planChart(['k', 'v'], Array.from({ length: 7 }, (_, i) => [`c${i}`, String(i + 1)]))!.options).toEqual(['bar']) })
  it('negative values are never parts of a whole', () => { expect(planChart(['k', 'v'], [['a', '5'], ['b', '-3'], ['c', '2']])!.options).toEqual(['bar']) })
  it('a few points over time: a line, and bars as the only alternative', () => { const p = planChart(['day', 'orders'], days(6))!; expect(p.kind).toBe('line'); expect(p.intent).toBe('trend'); expect(p.options).toEqual(['line', 'bar']) })
  it('many points over time: a line and nothing else', () => { const p = planChart(['day', 'orders'], days(30))!; expect(p.kind).toBe('line'); expect(p.options).toEqual(['line']) })
  it('a trend keeps date order and all its points', () => { const p = planChart(['day', 'orders'], days(20))!; expect(p.labels[0]).toBe('2026-11-01'); expect(p.labels.length).toBe(20); expect(p.omitted).toBe(0) })
  it('a donut can be chosen only where it is offered', () => {
    expect(planChart(carriers.columns, carriers.rows, { kind: 'donut' })!.kind).toBe('donut'); expect(planChart(forecast.columns, forecast.rows, { kind: 'donut' })!.kind).toBe('bar')
    expect(planChart(['day', 'n'], days(30), { kind: 'donut' })!.kind).toBe('line')
  })
})

describe('how it is drawn', () => {
  it('bars are sorted high to low; long or many labels go horizontal', () => {
    const p = planChart(['entity', 'total'], [['Meridian Europe GmbH', '5'], ['Meridian Japan KK', '9'], ['Meridian Asia Pte', '7']])!
    expect(p.labels[0]).toBe('Meridian Japan KK'); expect(p.horizontal).toBe(true); expect(planChart(carriers.columns, carriers.rows)!.horizontal).toBe(false)
  })
  it('keeps the top 12 of a long list and says so', () => {
    const p = planChart(['item', 'n'], Array.from({ length: 30 }, (_, i) => [`item ${i}`, String(i)]))!
    expect(p.labels.length).toBe(12); expect(p.omitted).toBe(18); expect(p.note).toMatch(/top 12 of 30/); expect(p.measures[0].values[0]).toBe(29)
  })
  it('measures that differ by orders of magnitude get panels of their own', () => {
    expect(planChart(['region', 'revenue', 'orders'], [['East', '9000000', '12'], ['West', '4000000', '8'], ['North', '6000000', '9']])!.panels).toBe(true)
    expect(planChart(['region', 'a', 'b'], [['East', '10', '12'], ['West', '4', '8'], ['North', '6', '9']])!.panels).toBe(false)
  })
  it('plots the normalised amount, never the ids, and prefers a unique name as the label', () => {
    const p = planChart(['payment_id', 'vendor', 'amount', 'amount_usd'], [['1', 'Acme', '100', '108'], ['2', 'Beta', '50', '54'], ['3', 'Gamma', '70', '75']])!
    expect(p.measures.map((m) => m.name)).toEqual(['amount_usd']); expect(p.labels[0]).toBe('Acme')
  })
  it('labels an id with the name beside it when the names repeat', () => {
    const p = planChart(['payment_id', 'entity', 'usd'], [['1', 'Europe', '108'], ['2', 'Europe', '54'], ['3', 'Japan', '75']])!; expect(p.labels[0]).toBe('1 · Europe')
  })
  it('lets the person pick another measure', () => {
    const cols = ['region', 'a', 'b'], rows: Rows = [['E', '10', '12'], ['W', '4', '8'], ['N', '6', '9']]
    expect(planChart(cols, rows, { measures: ['b'] })!.measures.map((m) => m.name)).toEqual(['b']); expect(planChart(cols, rows)!.candidates).toEqual(['a', 'b'])
  })
})

describe('compact, ticks, description, stats', () => {
  it('shortens big numbers for axes only', () => { expect([compact(520000), compact(1500), compact(3400000), compact(12), compact(0.256), compact(-2500000), compact(999)]).toEqual(['520K', '1.5K', '3.4M', '12', '0.256', '-2.5M', '999']) })
  it('gives round ticks starting at zero', () => { expect(niceTicks(0, 520000)).toEqual([0, 200000, 400000, 600000]); expect(niceTicks(0, 0)).toEqual([0, 1]); expect(niceTicks(3, 3)).toEqual([0, 1, 2, 3]) })
  it('describes the chart for a screen reader', () => { expect(describePlan(planChart(carriers.columns, carriers.rows)!)).toBe('Bar chart of shipments by carrier, 5 rows. The highest shipments is 40 for DHL.') })
  it('shows a single row of numbers as large tiles', () => {
    expect(statTiles(['total_liquidity_usd', 'accounts'], [['1250000.50', '12']])).toEqual([{ label: 'total_liquidity_usd', value: '1250000.50' }, { label: 'accounts', value: '12' }])
    expect(statTiles(['name'], [['x']])).toBeNull(); expect(statTiles(['a', 'b'], [['1', '2'], ['3', '4']])).toBeNull()
  })
})

describe('scatter', () => {
  const cols = ['supplier', 'spend_usd', 'late_days']
  const rows = [['A', '100', '3'], ['B', '250', '9'], ['C', '90', '2'], ['D', '400', '15'], ['E', '60', '1']]
  it('is offered for two measures over five or more things, and plots the first across and the second up', () => {
    const p = planChart(cols, rows, { kind: 'scatter' })!
    expect(p.options).toContain('scatter'); expect(p.kind).toBe('scatter'); expect(p.intent).toBe('relationship')
    expect(p.measures.map((m) => m.name)).toEqual(['spend_usd', 'late_days']); expect(p.labels).toEqual(['A', 'B', 'C', 'D', 'E'])
  })
  it('is not offered for one measure, fewer than five rows, a trend or a ranking question', () => {
    expect(planChart(['supplier', 'spend_usd'], rows.map((r) => r.slice(0, 2)))!.options).not.toContain('scatter')
    expect(planChart(cols, rows.slice(0, 4))!.options).not.toContain('scatter')
    expect(planChart(cols, rows, { question: 'Top suppliers by spend' })!.options).not.toContain('scatter')
    const trend = rows.map((r, i) => [`2026-0${i + 1}-01`, r[1], r[2]])
    expect(planChart(['month', 'spend_usd', 'late_days'], trend)!.options).not.toContain('scatter')
  })
  it('keeps the chosen pair and describes it in words', () => {
    const p = planChart(cols, rows, { kind: 'scatter', measures: ['late_days', 'spend_usd'] })!
    expect(p.measures.map((m) => m.name)).toEqual(['late_days', 'spend_usd']); expect(describePlan(p)).toMatch(/Scatter chart of spend USD against late days/)
  })
})
