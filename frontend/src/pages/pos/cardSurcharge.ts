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

export type Numerico = number | string | null | undefined

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

/** Renglón de un pago mixto, en lo mínimo que hace falta para la comisión. */
export interface MixedPaymentLine {
  method: string
  amount: Numerico
}

export interface MixedSurcharge {
  /** ¿Hay al menos un renglón de tarjeta? Sin él el backend NO cobra comisión. */
  hasCard: boolean
  /** Suma de los renglones que NO son tarjeta: la base se descuenta de ahí. */
  nonCardPaid: number
  /** Lo que el backend va a cobrar de verdad con estos renglones. */
  charged: CardSurcharge
  /** Lo que costaría completar el faltante con tarjeta, exista o no el renglón. */
  projected: CardSurcharge
}

/**
 * Comisión de un pago mixto, con la misma condición que el backend.
 *
 * `app/services/card_surcharge.py::calcular_comision` devuelve CERO si ningún
 * pago es de tarjeta. El modal ignoraba esa condición y mostraba "Comisión" y
 * "Total a pagar" inflados en un mixto EFECTIVO+TRANSFERENCIA, pidiéndole al
 * cliente un dinero que la venta nunca iba a registrar (ni como comisión, ni
 * como cambio).
 *
 * Por eso van los dos números: `charged` es la verdad (lo que se cobra) y
 * `projected` es la hipótesis que alimenta el botón «Completar con tarjeta»,
 * que es justo el que crea el renglón de CARD que todavía no existe.
 */
export function mixedSurcharge(
  total: Numerico,
  lines: readonly MixedPaymentLine[],
  pct: Numerico,
): MixedSurcharge {
  const renglones = lines || []
  const hasCard = renglones.some((l) => String(l?.method || '').toUpperCase() === 'CARD')
  const nonCardPaid = cents(
    renglones
      .filter((l) => String(l?.method || '').toUpperCase() !== 'CARD')
      .reduce((s, l) => s + (Number(l?.amount) || 0), 0),
  )
  const projected = surchargeFor(total, nonCardPaid, pct)
  return {
    hasCard,
    nonCardPaid,
    charged: hasCard ? projected : surchargeFor(total, nonCardPaid, 0),
    projected,
  }
}

/**
 * ¿Este `detail` de error habla de la comisión por pago con tarjeta?
 *
 * `create_sale` añade "(incluye comisión tarjeta N)" al 422 de pagos
 * insuficientes cuando el servidor SÍ cobró comisión
 * (`app/routers/sales.py`). Si el POS mandó el importe sin ella, es porque su
 * caché del porcentaje quedó vieja: un POS abierto todo el día no se entera de
 * que Empresa cambió el número. La señal sirve para recargar el porcentaje y
 * pedirle a la cajera que reintente, en vez de dejarla repitiendo el mismo
 * cobro rechazado.
 *
 * Tolerante con la forma del `detail`: texto en los `HTTPException` y arreglo
 * de objetos en los 422 de validación de Pydantic.
 */
export function isCardSurchargeError(detail: unknown): boolean {
  let texto: string
  try {
    texto = typeof detail === 'string' ? detail : JSON.stringify(detail ?? '')
  } catch {
    return false
  }
  const plano = texto
    .toLowerCase()
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
  return plano.includes('comision tarjeta')
}
