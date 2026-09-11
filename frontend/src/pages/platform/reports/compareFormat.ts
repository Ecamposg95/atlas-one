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

/** Texto de la celda Δ. Sin referencia va un guion: 0% sería mentira.
 *
 * Solo el texto: el color lo decide `deltaTone`, que es quien sabe si crecer
 * es bueno o malo. Devolver también un tono desde aquí daba dos respuestas
 * distintas a la misma pregunta, y la de aquí ignoraba `lowerIsBetter`.
 */
export function fmtDeltaCell(pct: number | null | undefined): string {
  if (pct === null || pct === undefined) return '—'
  if (pct === 0) return '='
  const abs = Math.abs(pct).toFixed(1)
  return pct > 0 ? `▲ ${abs}%` : `▼ ${abs}%`
}
