/**
 * Equivalente en dólares del POS.
 *
 * Funciones puras (sin React ni axios) para que `vitest` las pruebe: el
 * proyecto solo corre `src/**\/*.test.ts` con `environment: 'node'`.
 *
 * El número que se PERSISTE (`sales_documents.usd_rate`) y el que se IMPRIME
 * los calcula el backend con `Decimal` (`app/services/exchange_rate.py`); esto
 * es solo para pintar en pantalla. Ambos redondean a centavos, así que el
 * ticket y la pantalla coinciden.
 */
import { formatCurrency } from './currency'

/** Pesos → dólares, redondeado a centavos. Tipo de cambio inválido → 0. */
export function usdEquivalent(
  amountMxn: number | string | null | undefined,
  rate: number | string | null | undefined,
): number {
  const monto = Number(amountMxn)
  const tasa = Number(rate)
  if (!Number.isFinite(monto) || !Number.isFinite(tasa) || tasa <= 0) return 0
  return Math.round((monto / tasa) * 100) / 100
}

/** `"USD 12.34"`. Entrada inválida → `"USD 0.00"`, nunca `"$NaN"`. */
export function formatUsd(value: number | string | null | undefined): string {
  // `Intl` en es-MX separa "USD" del monto con un espacio duro (U+00A0). Se
  // normaliza a un espacio normal para que el string sea comparable.
  return formatCurrency(value, { currency: 'USD', fallback: 'USD 0.00' }).replace(/ /g, ' ')
}

/** `"≈ USD 10.00 · T.C. 18.50"` para el pie del carrito. Sin tasa → `null`. */
export function usdSummary(
  amountMxn: number | string | null | undefined,
  rate: number | string | null | undefined,
): string | null {
  const tasa = Number(rate)
  if (!Number.isFinite(tasa) || tasa <= 0) return null
  return `≈ ${formatUsd(usdEquivalent(amountMxn, tasa))} · T.C. ${tasa.toFixed(2)}`
}
