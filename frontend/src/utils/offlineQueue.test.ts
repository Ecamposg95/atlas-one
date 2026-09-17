import { describe, it, expect } from 'vitest'

import { droppedSaleMessage } from './offlineQueue'

// Una venta encolada que el backend rechaza con 4xx se BORRA de la cola: ese
// cobro ya ocurrió en el mundo real (el cliente pagó) y nunca va a quedar
// registrado. Antes solo se hacía `console.warn`, así que el dinero se perdía
// en silencio. El caso que lo dispara en producción es el 422 por un
// porcentaje de comisión cambiado mientras el POS estaba sin red.

const venta = (payments: unknown) => ({
  id: 'abc-123',
  payload: { payments },
  enqueued_at: 0,
  attempts: 1,
})

describe('droppedSaleMessage', () => {
  it('nombra el monto cobrado y el motivo del rechazo', () => {
    const msg = droppedSaleMessage(
      venta([{ method: 'CARD', amount: 1035 }]),
      { response: { status: 422, data: { detail: 'Pagos insuficientes: recibido 1000.00 vs total 1000.00 (incluye comisión tarjeta 35.00)' } } },
    )
    expect(msg).toContain('1,035.00')
    expect(msg).toContain('comisión tarjeta')
    expect(msg).toContain('No se pudo registrar')
  })

  it('suma todos los renglones de un pago mixto', () => {
    const msg = droppedSaleMessage(
      venta([{ method: 'CASH', amount: 600 }, { method: 'CARD', amount: 517.5 }]),
      { response: { status: 400, data: { detail: 'Caja cerrada' } } },
    )
    expect(msg).toContain('1,117.50')
    expect(msg).toContain('Caja cerrada')
  })

  it('sin detalle usable cae a un motivo genérico con el código HTTP', () => {
    const msg = droppedSaleMessage(venta([{ method: 'CASH', amount: 50 }]), { response: { status: 409 } })
    expect(msg).toContain('50.00')
    expect(msg).toContain('409')
  })

  it('aguanta un payload sin pagos', () => {
    const msg = droppedSaleMessage(
      { id: 'x', payload: null, enqueued_at: 0, attempts: 0 },
      { response: { status: 422, data: { detail: 'Sin productos' } } },
    )
    expect(msg).toContain('Sin productos')
    expect(msg).not.toContain('NaN')
  })
})
