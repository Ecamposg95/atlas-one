import { describe, it, expect } from 'vitest'
import { heroState, HERO_STATES } from '../heroState'

describe('heroState — banda + píldora del hero según el estado del turno', () => {
  it('turno abierto gana aunque también haya cerrado hoy', () => {
    expect(heroState(true, true).key).toBe('open')
  })
  it('cerrado hoy cuando no está abierto', () => {
    expect(heroState(false, true).key).toBe('closedToday')
  })
  it('sin caja abierta cuando ninguna de las dos aplica', () => {
    expect(heroState(false, false).key).toBe('none')
  })
  it('las tres bandas son tokens de Atlas ONE distintos, no hexadecimales fijos', () => {
    const bands = [HERO_STATES.open.band, HERO_STATES.closedToday.band, HERO_STATES.none.band]
    expect(new Set(bands).size).toBe(3)
    for (const b of bands) expect(b).toMatch(/^var\(--dax-[a-z-]+\)$/)
  })
  it('las tres píldoras llevan clase propia y ninguna paleta fija', () => {
    const pills = [HERO_STATES.open.pill, HERO_STATES.closedToday.pill, HERO_STATES.none.pill]
    expect(new Set(pills).size).toBe(3)
    for (const p of pills) {
      expect(p).toMatch(/^hero-pill hero-pill-(open|closed|none)$/)
      expect(p).not.toMatch(/emerald|orange|purple|text-white/)
    }
  })
})
