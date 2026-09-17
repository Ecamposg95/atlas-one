/**
 * Comisión por pago con tarjeta — espejo en pantalla del servicio del backend.
 *
 * Funciones puras (sin React ni axios) para que `vitest` las pruebe: el
 * proyecto solo corre `src/**\/*.test.ts` con `environment: 'node'`.
 *
 * El número que se COBRA y se PERSISTE lo calcula `app/services/card_surcharge.py`
 * con `Decimal`; esto es lo que ve el cajero antes de confirmar. Las dos
 * implementaciones redondean a centavos hacia arriba en el medio, así que la
 * pantalla y el cargo coinciden al centavo. Si divergen, el cajero cobra un
 * importe y el ticket imprime otro, con el cliente delante.
 *
 * Regla (diseño §4):
 *     base    = max(0, total − pagos que NO son tarjeta)
 *     amount  = redondear(base × pct / 100)
 *     cardDue = base + amount
 *     totalDue = total + amount
 */

export interface CardSurcharge {
  /** Importe sobre el que se cobra la comisión. */
  base: number
  /** Porcentaje efectivamente aplicado (0 si no aplicó). */
  pct: number
  /** La comisión, en pesos. */
  amount: number
  /** Lo que debe pasar por la terminal: `base + amount`. */
  cardDue: number
  /** Lo que el cliente entrega en total: `total + amount`. */
  totalDue: number
}

type Numerico = number | string | null | undefined

/** Número redondeado a centavos. Entrada inválida → 0. */
function cents(value: Numerico): number {
  const n = Number(value)
  if (!Number.isFinite(n)) return 0
  return Math.round(n * 100) / 100
}

export function surchargeFor(
  total: Numerico,
  nonCardPaid: Numerico,
  pct: Numerico,
): CardSurcharge {
  const totalQ = cents(total)
  const pctQ = cents(pct)
  const neutro: CardSurcharge = { base: 0, pct: 0, amount: 0, cardDue: 0, totalDue: totalQ }

  if (!(pctQ > 0)) return neutro

  // `base` nunca negativa: un billete grande tecleado como efectivo no puede
  // regalarle al cliente una comisión al revés.
  const base = cents(totalQ - cents(nonCardPaid))
  if (!(base > 0)) return neutro

  // `round(base × pct) / 100` es exactamente `round(base × pct / 100, 2)`, y
  // evita el error de coma flotante de dividir antes de redondear.
  const amount = Math.round(base * pctQ) / 100
  if (!(amount > 0)) return neutro

  return {
    base,
    pct: pctQ,
    amount,
    cardDue: cents(base + amount),
    totalDue: cents(totalQ + amount),
  }
}

/** `3.5`, `2.75`, `3`. Sin ceros de relleno, igual que la etiqueta del ticket. */
export function formatPct(pct: Numerico): string {
  const n = Number(pct)
  if (!Number.isFinite(n)) return '0'
  return String(Number(n.toFixed(2)))
}
