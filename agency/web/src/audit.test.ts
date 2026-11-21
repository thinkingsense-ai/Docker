import { describe, expect, it } from 'vitest'
import { auditQuery } from './api'

describe('audit filters', () => {
  it('drops blanks, trims and encodes what is left', () => {
    expect(auditQuery({ definition: 'risk-assessment', actor: '  ', outcome: '', control: 'Change & test', run: 'assess-3' })).toBe('definition=risk-assessment&control=Change%20%26%20test&run=assess-3')
    expect(auditQuery({})).toBe('')
  })
})
