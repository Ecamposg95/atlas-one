/** Periodos del cielo del saludo (spec 2026-09-08 §4.4 A1). Hora local del navegador. */
export type SkyPeriod = 'day' | 'sunset' | 'night'

export function skyPeriod(d: Date): SkyPeriod {
  const mins = d.getHours() * 60 + d.getMinutes()
  if (mins >= 6 * 60 && mins < 17 * 60) return 'day'
  if (mins >= 17 * 60 && mins < 19 * 60 + 30) return 'sunset'
  return 'night'
}

/** Curva del count-up: rápido al inicio, frena al llegar. */
export function easeOutCubic(t: number): number {
  const x = Math.min(1, Math.max(0, t))
  return 1 - Math.pow(1 - x, 3)
}
