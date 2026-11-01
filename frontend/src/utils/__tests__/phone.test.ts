import { describe, it, expect } from 'vitest'
import { toWaPhone } from '../phone'

describe('toWaPhone (Review Focus 5)', () => {
  it('normaliza a E.164 de México', () => {
    expect(toWaPhone('55 1234 5678')).toBe('525512345678')
    expect(toWaPhone('(55) 1234-5678')).toBe('525512345678')
    expect(toWaPhone('+52 55 1234 5678')).toBe('525512345678')
    expect(toWaPhone('5215512345678')).toBe('5215512345678')
  })
  it('lo que no es marcable da null', () => {
    expect(toWaPhone(null)).toBeNull()
    expect(toWaPhone('')).toBeNull()
    expect(toWaPhone('1234')).toBeNull()
  })
})
