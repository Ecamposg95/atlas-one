/** Regla del backend (app/routers/sales.py): total_paid > total × 10 → 422 "Sobrepago anómalo". */
export const OVERPAY_FACTOR = 10

export function cashPaymentValidity(received: number, total: number) {
  const r = Number.isFinite(received) ? received : 0
  // Misma tolerancia que el backend: tolerance = Decimal("0.01") en sales.py.
  const short = r < total - 0.01
  const overpay = total > 0 && r > total * OVERPAY_FACTOR
  return { ok: !short && !overpay, short, overpay }
}
