/**
 * Corte de caja — CONTEO CIEGO.
 *
 * El monto esperado y la diferencia se ocultan mientras el turno está abierto,
 * aunque el cajero ya haya capturado su conteo; se muestran solo con el turno
 * cerrado, tomados de la respuesta del backend.
 *
 * Por qué: al abrir el modal de cierre se pre-llenaba el campo "contado" con
 * el esperado, así que bastaba dar clic para cerrar con diferencia $0.00.
 * Un faltante real quedaba enmascarado por el auto-cuadre y el control de caja
 * dejaba de detectar nada.
 *
 * No toca el backend ni el cálculo de `expected_cash`: cambia CUÁNDO y CÓMO
 * se muestra.
 *
 * Portado de Atlas-Rmazh (F2 · S13-fe).
 *
 * Desde 2026-11-21 es un ajuste de la tienda (`organization.conteo_ciego`,
 * encendido por omisión): `useConteoCiego()` lo lee y las pantallas se lo pasan
 * a estas funciones. Apagado, la caja ve el esperado y su desglose con el turno
 * abierto; el campo "contado" sigue sin pre-llenarse.
 */
import { useEnabledModulesStore } from '../store/enabledModulesStore'

/** ¿Rige el conteo ciego en esta tienda? Encendido mientras el contexto no carga. */
export function useConteoCiego(): boolean {
  return useEnabledModulesStore((s) => s.conteoCiego)
}

/** Valor enmascarado que ocupa el lugar del monto mientras rige el conteo ciego. */
export const BLIND_MASK = '****'

/** Nota corta que acompaña al valor enmascarado. */
export const BLIND_LABEL = 'Conteo ciego'

/**
 * ¿El texto capturado es un conteo numérico válido?
 *
 * Guard del botón de cierre: sin esto, un campo vacío o con basura se convertía
 * en `NaN` y podía cerrar el turno en $0.00 silenciosamente.
 */
export function isValidCount(counted: string): boolean {
  const t = (counted ?? '').trim()
  if (t === '') return false
  const n = Number(t)
  return Number.isFinite(n) && n >= 0
}

/**
 * El esperado y la diferencia se revelan solo con el turno YA cerrado.
 *
 * Antes se revelaban en cuanto el cajero tecleaba un conteo válido, y como el
 * campo seguía editable bastaba corregir el número hasta ver diferencia $0.
 */
export function shouldRevealExpected(closed: boolean, ciego = true): boolean {
  return closed || !ciego
}

/**
 * En el tablero de sucursal: el indicador "Efectivo esperado" se enmascara
 * mientras hay un turno abierto. Una vez cerrado no hay nada que adivinar.
 */
export function shouldShowExpectedKpi(hasOpenSession: boolean, ciego = true): boolean {
  return !hasOpenSession || !ciego
}
