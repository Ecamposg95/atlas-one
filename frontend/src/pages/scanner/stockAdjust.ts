/**
 * Traduce un CONTEO a un MOVIMIENTO de inventario.
 *
 * `POST /api/inventory/adjust` recibe un delta con signo (positivo entrada,
 * negativo salida — app/schemas/inventory.py:AdjustmentCreate). Pero en el
 * pasillo nadie piensa en deltas: se cuenta lo que hay en el anaquel. Esta
 * función hace la traducción, y la pantalla muestra el movimiento resultante
 * ANTES de aplicarlo, porque queda firmado en el kardex.
 */

export type AdjustmentKind = 'entrada' | 'salida' | 'sin-cambio'

export interface Adjustment {
  /** Con signo, tal como lo espera el backend. */
  delta: number
  kind: AdjustmentKind
  /** Magnitud, para redactar el mensaje sin repetir el signo. */
  abs: number
}

/** Stock es Numeric en la BD; 4 decimales evitan que 2.5-2.1 dé 0.39999999999999997. */
const round = (n: number) => Math.round(n * 10000) / 10000

/**
 * `null` cuando lo contado no sirve como conteo (vacío, no numérico, negativo):
 * el caller no debe mandar nada al backend en ese caso.
 */
export function computeAdjustment(
  current: number | null | undefined,
  counted: number,
): Adjustment | null {
  if (!Number.isFinite(counted) || counted < 0) return null

  const have = Number.isFinite(current as number) ? (current as number) : 0
  const delta = round(counted - have)

  if (delta === 0) return { delta: 0, kind: 'sin-cambio', abs: 0 }
  return { delta, kind: delta > 0 ? 'entrada' : 'salida', abs: Math.abs(delta) }
}
