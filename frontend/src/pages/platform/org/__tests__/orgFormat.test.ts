import { describe, expect, it } from 'vitest'
import {
  attentionChips,
  fmtCloseAt,
  fmtDelta,
  fmtMix,
  orgsQueNecesitanAtencion,
  sortRowsBySales,
  staleLabel,
} from '../orgFormat'
import type {
  AttentionLists,
  BranchOverviewRow,
  OverviewMix,
} from '../../../../types/platformOverview'

const mix = (o: Partial<OverviewMix>): OverviewMix => ({
  cash: 0,
  card: 0,
  transfer: 0,
  other: 0,
  cash_pct: null,
  card_pct: null,
  transfer_pct: null,
  other_pct: null,
  ...o,
})

describe('fmtDelta', () => {
  it('positivo, negativo, cero y sin referencia', () => {
    expect(fmtDelta(6.2)).toEqual({ text: '▲ 6.2%', tone: 'up' })
    expect(fmtDelta(-4)).toEqual({ text: '▼ 4.0%', tone: 'down' })
    expect(fmtDelta(0)).toEqual({ text: '=', tone: 'flat' })
    expect(fmtDelta(null)).toEqual({ text: '—', tone: 'flat' })
  })
})

describe('fmtMix', () => {
  it('efectivo contra el resto, redondeado', () => {
    expect(fmtMix(mix({ cash_pct: 84.4, card_pct: 10.1, transfer_pct: 5.5, other_pct: 0 }))).toBe(
      '84 / 16'
    )
  })
  it('sin datos', () => {
    expect(fmtMix(mix({}))).toBe('—')
  })
})

describe('staleLabel', () => {
  it('null por debajo de un minuto, "datos de hace N min" después', () => {
    const now = 1_000_000_000
    expect(staleLabel(null, now)).toBeNull()
    expect(staleLabel(now - 30_000, now)).toBeNull()
    expect(staleLabel(now - 3 * 60_000 - 10, now)).toBe('datos de hace 3 min')
  })
})

const vacia: AttentionLists = {
  no_cut: [],
  cut_difference: [],
  oldest_returns: [],
  cancelled_today: [],
}
const item = (orgId: number, orgName: string) => ({
  id: 1,
  name: 'Sucursal Centro',
  org_id: orgId,
  org_name: orgName,
  value: -221,
  detail: '',
})

describe('attentionChips', () => {
  it('sin nada que atender → sin chips', () => {
    expect(attentionChips(vacia)).toEqual([])
  })

  it('un chip por lista con conteo y tono', () => {
    const uno = item(1, 'Kaory')
    const chips = attentionChips({ ...vacia, no_cut: [uno, uno, uno], cut_difference: [uno] })
    expect(chips).toEqual([
      { key: 'no_cut', label: '3 sin corte >14 h', tone: 'warning' },
      { key: 'cut_difference', label: '1 corte con diferencia', tone: 'danger' },
    ])
  })

  it('cuando la lista viene recortada, el chip dice "N de TOTAL"', () => {
    const uno = item(1, 'Kaory')
    const chips = attentionChips(
      { ...vacia, cut_difference: [uno, uno] },
      { no_cut: 0, cut_difference: 23, oldest_returns: 0, cancelled_today: 0 }
    )
    expect(chips).toEqual([
      { key: 'cut_difference', label: '2 de 23 cortes con diferencia', tone: 'danger' },
    ])
  })

  it('sin recorte no dice "de": el total y lo mostrado coinciden', () => {
    const uno = item(1, 'Kaory')
    const chips = attentionChips(
      { ...vacia, no_cut: [uno] },
      { no_cut: 1, cut_difference: 0, oldest_returns: 0, cancelled_today: 0 }
    )
    expect(chips).toEqual([{ key: 'no_cut', label: '1 sin corte >14 h', tone: 'warning' }])
  })
})

describe('orgsQueNecesitanAtencion', () => {
  it('cuenta organizaciones distintas, no renglones', () => {
    expect(orgsQueNecesitanAtencion(vacia)).toBe(0)
    expect(
      orgsQueNecesitanAtencion({
        ...vacia,
        no_cut: [item(1, 'Kaory'), item(1, 'Kaory')],
        cut_difference: [item(2, 'Ginebra')],
      })
    ).toBe(2)
  })
})

describe('fmtCloseAt', () => {
  it('hoy → "hoy HH:MM"', () => {
    const now = new Date(2026, 8, 9, 10, 0)
    const iso = new Date(2026, 8, 9, 21, 14).toISOString()
    expect(fmtCloseAt(iso, now).startsWith('hoy ')).toBe(true)
  })

  it('ayer → "ayer HH:MM"', () => {
    const now = new Date(2026, 8, 9, 10, 0)
    const iso = new Date(2026, 8, 8, 21, 14).toISOString()
    expect(fmtCloseAt(iso, now).startsWith('ayer ')).toBe(true)
  })

  it('más viejo → "5 sep 21:14"', () => {
    const now = new Date(2026, 8, 9)
    const iso = new Date(2026, 8, 5, 21, 14).toISOString()
    expect(fmtCloseAt(iso, now)).toBe('5 sep 21:14')
  })

  it('sin fecha → "—"', () => {
    expect(fmtCloseAt(null)).toBe('—')
    expect(fmtCloseAt(undefined)).toBe('—')
  })
})

describe('sortRowsBySales', () => {
  const row = (id: number, sales: number) => ({ id, sales_today: sales } as BranchOverviewRow)
  it('descendente por venta de hoy sin mutar la entrada', () => {
    const input = [row(1, 10), row(2, 30), row(3, 20)]
    expect(sortRowsBySales(input).map((r) => r.id)).toEqual([2, 3, 1])
    expect(input.map((r) => r.id)).toEqual([1, 2, 3])
  })
})
