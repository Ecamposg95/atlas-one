/** Veredicto visual del cierre (A6). Solo presentación: el backend ya calculó `difference`. */
export type VerdictKind = 'ok' | 'over' | 'short'
export interface Verdict { kind: VerdictKind; label: string; className: string }

const TOLERANCIA = 1 // pesos: por debajo de $1 de diferencia se considera cuadrada

/**
 * `className` son clases propias (`.verdict-*` en styles/motion.css) que pintan
 * con `--dax-success` / `--dax-warning` / `--dax-danger`. No se devuelven clases
 * de paleta fija de Tailwind: la identidad visual la mandan los tokens.
 */
export function closeVerdict(difference: number): Verdict {
  const d = Number.isFinite(difference) ? difference : 0
  if (Math.abs(d) < TOLERANCIA) return { kind: 'ok', label: 'Caja cuadrada', className: 'verdict verdict-ok' }
  if (d > 0) return { kind: 'over', label: 'Sobrante', className: 'verdict verdict-over' }
  return { kind: 'short', label: 'Faltante', className: 'verdict verdict-short' }
}
