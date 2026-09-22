import type { LabelCandidate, LabelJobItem } from '../../api/labels'

/**
 * Aritmética del lote de etiquetas. Función pura, sin React ni red: es lo que
 * decide cuántas etiquetas salen del rollo, así que se prueba sola
 * (`lote.test.ts`).
 *
 * Los topes son los MISMOS que el backend (`app/modules/labels/schemas.py`).
 * Aquí se aplican para poder avisar ANTES de mandar la petición, no para
 * sustituir la validación: el servidor sigue siendo la autoridad.
 */

/** Máximo por renglón. Un error de dedo no vacía el rollo. */
export const MAX_COPIAS = 99
/** Máximo del trabajo entero. */
export const MAX_LOTE = 500

/** Copias por `variant_id`. */
export type MapaCopias = Record<string, number>

/**
 * Normaliza lo que el usuario teclea en la celda de copias.
 *
 * El rango de la celda es 0..99, no 1..99: el backend exige `copies >= 1`, y
 * **0 aquí significa "esta fila no se imprime"**. Hace falta porque
 * `copies_default` nace de la existencia y una prenda agotada llega con 0 —
 * mandarla con 1 imprimiría una etiqueta que nadie pidió.
 */
export function normalizarCopias(valor: string | number): number {
  const n = typeof valor === 'number' ? valor : Number.parseInt(valor, 10)
  if (!Number.isFinite(n)) return 0
  return Math.max(0, Math.min(MAX_COPIAS, Math.trunc(n)))
}

/** Copias de arranque: la sugerencia del backend (existencia topada en 99). */
export function copiasIniciales(items: LabelCandidate[]): MapaCopias {
  const mapa: MapaCopias = {}
  for (const it of items) mapa[it.variant_id] = normalizarCopias(it.copies_default)
  return mapa
}

/**
 * Filas sobre las que actúa una acción en lote.
 *
 * Sin selección el alcance es **todo lo visible**: con los filtros puestos, esa
 * es la intención evidente ("etiqueta este departamento"), y marcar 80 casillas
 * a mano para lograrlo sería castigo. Con selección, solo lo seleccionado.
 */
export function alcance(items: LabelCandidate[], seleccion: ReadonlySet<string>): LabelCandidate[] {
  if (seleccion.size === 0) return items
  return items.filter((it) => seleccion.has(it.variant_id))
}

/** "Usar existencia": devuelve las copias con la sugerencia del backend aplicada al alcance. */
export function usarExistencia(
  items: LabelCandidate[],
  copias: MapaCopias,
  seleccion: ReadonlySet<string>,
): MapaCopias {
  const siguiente = { ...copias }
  for (const it of alcance(items, seleccion)) {
    siguiente[it.variant_id] = normalizarCopias(it.copies_default)
  }
  return siguiente
}

/**
 * "Poner N a los seleccionados". A diferencia de "usar existencia", esta acción
 * SÍ exige selección: poner 5 a las 200 filas visibles no es algo que nadie
 * quiera por accidente.
 */
export function ponerN(
  items: LabelCandidate[],
  copias: MapaCopias,
  seleccion: ReadonlySet<string>,
  n: string | number,
): MapaCopias {
  if (seleccion.size === 0) return copias
  const valor = normalizarCopias(n)
  const siguiente = { ...copias }
  for (const it of items) {
    if (seleccion.has(it.variant_id)) siguiente[it.variant_id] = valor
  }
  return siguiente
}

export interface FilaOmitida {
  variant_id: string
  sku: string
  reason: string
}

export interface ResumenLote {
  /** Renglones listos para `POST /jobs`. */
  items: LabelJobItem[]
  /** Etiquetas que se van a imprimir (suma de copias). */
  etiquetas: number
  /** Filas que no se pueden imprimir, con su motivo. Se MUESTRAN, no se callan. */
  omitidas: FilaOmitida[]
  /** Filas imprimibles que el usuario dejó en 0 copias (decisión suya, no error). */
  sinCopias: number
  /** `true` cuando el lote pasa de MAX_LOTE: el backend lo rechazaría con 422. */
  excede: boolean
}

/**
 * Arma el lote a partir de la tabla: qué se manda, cuánto suma y qué queda fuera.
 *
 * Reglas, en este orden:
 * 1. Alcance = selección, o todo lo visible si no hay selección.
 * 2. `printable: false` → a `omitidas` con su motivo (nunca al trabajo).
 * 3. Copias en 0 → fuera del trabajo, pero no es un error: se cuenta aparte.
 */
export function construirLote(
  items: LabelCandidate[],
  copias: MapaCopias,
  seleccion: ReadonlySet<string>,
): ResumenLote {
  const jobItems: LabelJobItem[] = []
  const omitidas: FilaOmitida[] = []
  let etiquetas = 0
  let sinCopias = 0

  for (const it of alcance(items, seleccion)) {
    if (!it.printable) {
      omitidas.push({
        variant_id: it.variant_id,
        sku: it.sku,
        reason: it.reason ?? 'No se puede imprimir',
      })
      continue
    }
    const n = normalizarCopias(copias[it.variant_id] ?? it.copies_default)
    if (n < 1) { sinCopias += 1; continue }
    jobItems.push({ variant_id: it.variant_id, copies: n })
    etiquetas += n
  }

  return { items: jobItems, etiquetas, omitidas, sinCopias, excede: etiquetas > MAX_LOTE }
}

/**
 * Mensaje del tope, con la misma forma que el 422 del backend para que la
 * cajera lea lo mismo aquí y allá.
 */
export function mensajeExceso(etiquetas: number): string {
  return (
    `El lote suma ${etiquetas} etiquetas y el máximo es ${MAX_LOTE}. ` +
    'Quita renglones o baja las copias.'
  )
}

/** Resumen de una línea para el diálogo de confirmación. */
export function textoResumen(resumen: ResumenLote): string {
  const partes = [
    `${resumen.etiquetas} ${resumen.etiquetas === 1 ? 'etiqueta' : 'etiquetas'}`,
    `${resumen.items.length} ${resumen.items.length === 1 ? 'renglón' : 'renglones'}`,
  ]
  if (resumen.omitidas.length > 0) {
    partes.push(`${resumen.omitidas.length} sin código de barras`)
  }
  if (resumen.sinCopias > 0) {
    partes.push(`${resumen.sinCopias} en 0 copias`)
  }
  return partes.join(' · ')
}
