import type { CompareMode } from '../../../types/reportsMoney'

export const COMPARE_OPTIONS: { key: CompareMode; label: string }[] = [
  { key: 'none', label: 'Sin comparar' },
  { key: 'prev', label: 'vs periodo anterior' },
  { key: 'yoy', label: 'vs año pasado' },
]

export function compareLabel(mode: CompareMode): string {
  return COMPARE_OPTIONS.find((o) => o.key === mode)?.label ?? 'Sin comparar'
}

/** Tono del delta. `lowerIsBetter` para cifras donde crecer es malo (faltantes, devoluciones). */
export function deltaTone(pct: number | null | undefined, lowerIsBetter = false): 'up' | 'down' | 'flat' {
  if (pct === null || pct === undefined || pct === 0) return 'flat'
  const good = lowerIsBetter ? pct < 0 : pct > 0
  return good ? 'up' : 'down'
}

/** Texto de la celda Δ. Sin referencia va un guion: 0% sería mentira. */
export function fmtDeltaCell(pct: number | null | undefined): { text: string; tone: 'up' | 'down' | 'flat' } {
  if (pct === null || pct === undefined) return { text: '—', tone: 'flat' }
  if (pct === 0) return { text: '=', tone: 'flat' }
  const abs = Math.abs(pct).toFixed(1)
  return { text: pct > 0 ? `▲ ${abs}%` : `▼ ${abs}%`, tone: pct > 0 ? 'up' : 'down' }
}

/** Bajo 768 px la columna Δ desaparece y el delta se pinta debajo de la cifra. */
export function showDeltaColumns(width: number): boolean {
  return width >= 768
}
