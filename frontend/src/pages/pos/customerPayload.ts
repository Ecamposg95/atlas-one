/**
 * Cliente de la venta, tal como viaja al backend y al snapshot de pausa.
 *
 * El POS mandaba solo `customer_id`, así que hasta una venta con cliente de
 * CRM se guardaba sin nombre y el historial decía "Público general". El nombre
 * libre (sin CRM) va en `customer_name` con `customer_id` ausente.
 */
export interface CustomerFields {
  customer_id?: number
  customer_name?: string
}

export function customerFields(customerId: number | null, customerName: string | null): CustomerFields {
  const out: CustomerFields = {}
  if (customerId != null) out.customer_id = customerId
  const name = (customerName ?? '').trim()
  if (name) out.customer_name = name
  return out
}

/** Cliente guardado en `cart_json` al pausar; `parkedCustomerId` viene aparte en el ticket. */
export function customerFromCartJson(
  cartJson: Record<string, unknown>,
  parkedCustomerId: number | null,
): { id: number | null; name: string | null } | null {
  const raw = cartJson.customer_name
  const name = typeof raw === 'string' && raw.trim() ? raw.trim() : null
  if (parkedCustomerId == null && !name) return null
  return { id: parkedCustomerId ?? null, name }
}
