/**
 * Ticket por WhatsApp (2026-11-04): en teléfono no hay agente de impresión, así
 * que la cajera le manda a la clienta el ticket como texto por `wa.me`. Todo
 * sale de la venta que ya devuelve el API (`GET /sales/{id}`); no hay endpoint
 * nuevo. El formato usa el *negritas* de WhatsApp y una línea por renglón.
 */
import type { SalesDocument } from '../types/sales'
import { saleLabel } from '../types/sales'
import { formatCurrency } from './currency'
import { toWaPhone } from './phone'

const METODOS: Record<string, string> = {
  CASH: 'Efectivo', CARD: 'Tarjeta', TRANSFER: 'Transferencia', OTHER: 'Otro',
}

const n = (v: unknown) => Number(v ?? 0) || 0

function fechaMx(iso: string): string {
  const d = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleString('es-MX', {
    timeZone: 'America/Mexico_City', day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

/** Texto del ticket listo para WhatsApp. `negocio` = nombre de la organización. */
export function textoTicketWhatsapp(venta: SalesDocument, negocio: string | null | undefined): string {
  const total = n(venta.total_amount)
  const comision = n(venta.card_surcharge_amount)
  const cobrado = total + comision
  const pagado = (venta.payments ?? []).reduce((a, p) => a + n(p.amount), 0)
  const efectivo = (venta.payments ?? []).some((p) => p.method === 'CASH')

  const lineas: string[] = []
  if (negocio?.trim()) lineas.push(`*${negocio.trim()}*`)
  if (venta.branch_name?.trim() && venta.branch_name.trim() !== negocio?.trim()) lineas.push(venta.branch_name.trim())
  lineas.push(`Ticket ${saleLabel(venta)} · ${fechaMx(venta.created_at)}`.replace(/ · $/, ''))
  lineas.push('')

  for (const l of venta.lines ?? []) {
    const qty = n(l.quantity)
    const cantidad = Number.isInteger(qty) ? String(qty) : qty.toFixed(2)
    const unitario = qty !== 1 ? ` (${formatCurrency(n(l.unit_price))} c/u)` : ''
    lineas.push(`${cantidad} × ${l.description || l.sku || 'Artículo'}${unitario} — ${formatCurrency(n(l.total_line))}`)
  }
  lineas.push('')

  if (n(venta.tax_amount) > 0) {
    lineas.push(`Subtotal: ${formatCurrency(n(venta.subtotal))}`)
    lineas.push(`IVA: ${formatCurrency(n(venta.tax_amount))}`)
  }
  if (comision > 0) lineas.push(`Comisión tarjeta: ${formatCurrency(comision)}`)
  lineas.push(`*Total: ${formatCurrency(cobrado)}*`)

  for (const p of venta.payments ?? []) {
    lineas.push(`Pagó con ${(METODOS[p.method] ?? p.method).toLowerCase()}: ${formatCurrency(n(p.amount))}`)
  }
  const diferencia = Math.round((pagado - cobrado) * 100) / 100
  if (efectivo && diferencia > 0) lineas.push(`Cambio: ${formatCurrency(diferencia)}`)
  if (diferencia < 0 && venta.customer_id) lineas.push(`Queda a crédito: ${formatCurrency(-diferencia)}`)
  if (venta.status === 'REFUNDED_PARTIAL' || venta.status === 'REFUNDED_TOTAL') {
    lineas.push('Este ticket tiene devoluciones.')
  }

  lineas.push('')
  lineas.push('¡Gracias por su compra!')
  return lineas.join('\n')
}

export type EnlaceWhatsapp = { ok: true; url: string } | { ok: false; error: string }

/**
 * `wa.me` con el texto. Sin número abre WhatsApp para elegir el chat; con
 * número debe ser marcable (10 dígitos MX o con lada 52), si no se avisa.
 */
export function enlaceWhatsapp(texto: string, telefono: string | null | undefined): EnlaceWhatsapp {
  const q = `?text=${encodeURIComponent(texto)}`
  if (!telefono?.trim()) return { ok: true, url: `https://wa.me/${q}` }
  const wa = toWaPhone(telefono)
  if (!wa) return { ok: false, error: 'Escribe un número de 10 dígitos' }
  return { ok: true, url: `https://wa.me/${wa}${q}` }
}
