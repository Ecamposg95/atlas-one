import { describe, expect, it } from 'vitest'
import type { SalesDocument } from '../../types/sales'
import { enlaceWhatsapp, textoTicketWhatsapp } from '../ticketWhatsapp'

const venta = (extra: Partial<SalesDocument> = {}): SalesDocument => ({
  id: 'abc', doc_type: 'INVOICE', status: 'PAID', branch_id: 1, branch_name: 'HQ - Novedades Campanita',
  seller_id: 2, customer_id: null, customer_name: null, series: 'A', folio: 1,
  subtotal: 605, tax_amount: 0, total_amount: 605, requires_invoice: false,
  created_at: '2026-11-04T22:50:00Z',
  lines: [
    { id: 'l1', variant_id: 'v1', sku: 'JL7540', description: 'JL7540', quantity: 2, unit_price: 150, total_line: 300 },
    { id: 'l2', variant_id: 'v2', sku: 'FUN', description: 'Funda Grinch', quantity: 1, unit_price: 305, total_line: 305 },
  ],
  payments: [{ id: 'p1', method: 'CASH', amount: 700 }],
  ...extra,
} as SalesDocument)

describe('textoTicketWhatsapp', () => {
  it('arma negocio, sucursal, folio con hora de México, renglones, total, pago y cambio', () => {
    const t = textoTicketWhatsapp(venta(), 'Novedades Campanita')
    const l = t.split('\n')
    expect(l[0]).toBe('*Novedades Campanita*')
    expect(l[1]).toBe('HQ - Novedades Campanita')
    expect(l[2]).toMatch(/^Ticket A-0001 · 04\/11\/2026, 04:50/)
    expect(t).toContain('2 × JL7540 ($150.00 c/u) — $300.00')
    expect(t).toContain('1 × Funda Grinch — $305.00')
    expect(t).toContain('*Total: $605.00*')
    expect(t).toContain('Pagó con efectivo: $700.00')
    expect(t).toContain('Cambio: $95.00')
    expect(t).not.toContain('IVA')
    expect(l[l.length - 1]).toBe('¡Gracias por su compra!')
  })

  it('suma la comisión de tarjeta al total y muestra IVA solo si hay', () => {
    const t = textoTicketWhatsapp(venta({
      subtotal: 100, tax_amount: 16, total_amount: 116, card_surcharge_amount: 4.06,
      lines: [{ id: 'l', variant_id: 'v', sku: 'X', description: 'Vaso', quantity: 1, unit_price: 100, total_line: 100 }],
      payments: [{ id: 'p', method: 'CARD', amount: 120.06 }],
    }), 'Tienda')
    expect(t).toContain('IVA: $16.00')
    expect(t).toContain('Comisión tarjeta: $4.06')
    expect(t).toContain('*Total: $120.06*')
    expect(t).not.toContain('Cambio')
  })

  it('una venta fiada a cliente dice cuánto queda a crédito', () => {
    const t = textoTicketWhatsapp(venta({ customer_id: 9, status: 'PENDING', payments: [{ id: 'p', method: 'CASH', amount: 200 }] }), 'Tienda')
    expect(t).toContain('Queda a crédito: $405.00')
    expect(t).not.toContain('Cambio')
  })

  it('no repite la sucursal cuando se llama igual que el negocio', () => {
    const t = textoTicketWhatsapp(venta({ branch_name: 'Tienda' }), 'Tienda')
    expect(t.split('\n')[1]).toMatch(/^Ticket /)
  })
})

describe('enlaceWhatsapp', () => {
  it('sin número abre el selector de chat', () => {
    expect(enlaceWhatsapp('hola y adiós', '')).toEqual({ ok: true, url: 'https://wa.me/?text=hola%20y%20adi%C3%B3s' })
  })
  it('con 10 dígitos antepone la lada de México', () => {
    expect(enlaceWhatsapp('x', '55 1234-5678')).toEqual({ ok: true, url: 'https://wa.me/525512345678?text=x' })
  })
  it('un número incompleto no arma enlace', () => {
    expect(enlaceWhatsapp('x', '12345')).toEqual({ ok: false, error: 'Escribe un número de 10 dígitos' })
  })
})
