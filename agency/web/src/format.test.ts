import { describe, expect, it } from 'vitest'
import { loadedText } from './PackCards'
import { badges, formatCell, isNumeric, scopeLine } from './format'

describe('formatCell', () => {
  it('groups thousands and keeps decimals', () => {
    expect(formatCell('484614.90')).toBe('484,614.90')
    expect(formatCell('-1234567')).toBe('-1,234,567')
  })
  it('leaves codes and long ids alone', () => {
    expect(formatCell('007')).toBe('007')
    expect(formatCell('1234567890123456789')).toBe('1234567890123456789')
  })
  it('shows empty values as a dash', () => { expect(formatCell(null)).toBe('—'); expect(formatCell('')).toBe('—') })
  it('formats ISO dates', () => { expect(formatCell('2026-11-17')).toBe('17 Nov 2026') })
  it('passes text through', () => { expect(formatCell('Acme Ltd')).toBe('Acme Ltd') })
  it('knows what is numeric', () => { expect(isNumeric('12.5')).toBe(true); expect(isNumeric('007')).toBe(false); expect(isNumeric('x')).toBe(false) })
})

describe('badges and scope', () => {
  it('badges non-commercial data and the embedding model', () => {
    const b = badges({ editions: ['free', 'commercial'], licence: { nonCommercial: true }, needsEmbeddingModel: true, capabilities: ['workflow:x'] })
    expect(b).toEqual(['free + commercial', 'non-commercial data', 'needs embedding model', 'workflow:x'])
  })
  it('labels a Docker-only pack and does not flag synthetic data', () => {
    expect(badges({ editions: ['docker'], licence: { nonCommercial: false }, needsEmbeddingModel: false, capabilities: [] })).toEqual(['Docker only'])
  })
  it('says who enforced the scope', () => {
    expect(scopeLine('agency-hint')).toContain('not enforced')
    expect(scopeLine('server-backends')).toContain('enforced by the Server')
    expect(scopeLine('none')).toContain('All data')
  })
})

describe('loadedText', () => {
  it('words the layer\'s three states', () => {
    expect(loadedText('workspace')).toContain('own Workspace')
    expect(loadedText('category')).toContain('no Workspace')
    expect(loadedText(null)).toContain('unknown')
  })
})

import { currencySymbol, humanName } from './format'
describe('column names for people', () => {
  it('reads underscored names', () => {
    expect(humanName('usd_amount')).toBe('USD amount'); expect(humanName('share_pct')).toBe('Share (%)'); expect(humanName('avg_error_pct')).toBe('Average error (%)'); expect(humanName('total_usd')).toBe('Total USD')
  })
  it('leaves ordinary words and mixed names alone', () => { expect(humanName('Supplier')).toBe('Supplier'); expect(humanName('total amount')).toBe('total amount') })
  it('finds a currency in a name', () => { expect(currencySymbol('total_usd')).toBe('$'); expect(currencySymbol('usd_amount')).toBe('$'); expect(currencySymbol('eur_total')).toBe('€'); expect(currencySymbol('accounts')).toBe(''); expect(currencySymbol('usdx')).toBe('') })
})
