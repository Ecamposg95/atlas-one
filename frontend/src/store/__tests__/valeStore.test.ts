import { describe, it, expect } from 'vitest'
import { repartoConVale } from '../valeStore'

describe('repartoConVale', () => {
  it('sin vale se cobra todo por el medio de siempre', () => {
    expect(repartoConVale(250, null)).toEqual({ aplica: 0, porCobrar: 250 })
  })
  it('el vale cubre lo que alcanza y el resto queda por cobrar', () => {
    expect(repartoConVale(250, { code: 'A', balance: 100 })).toEqual({ aplica: 100, porCobrar: 150 })
  })
  it('un vale mayor al total solo aplica el total (el resto se queda en el vale)', () => {
    expect(repartoConVale(80.5, { code: 'A', balance: 100 })).toEqual({ aplica: 80.5, porCobrar: 0 })
  })
})
