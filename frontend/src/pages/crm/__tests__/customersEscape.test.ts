import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

/** El detalle del cliente es un overlay propio (cabecera con editar/eliminar):
 *  no pasa por ui/Modal, así que Escape y el RFC largo se cuidan a mano. */
const s = readFileSync(resolve(__dirname, '../Customers.tsx'), 'utf8')

describe('detalle del cliente (overlay propio)', () => {
  it('cierra con Escape mientras hay un cliente seleccionado', () => {
    expect(s).toMatch(/e\.key === 'Escape'/)
    expect(s).toMatch(/addEventListener\('keydown'/)
    expect(s).toMatch(/removeEventListener\('keydown'/)
  })
  it('Escape no cierra el detalle si encima hay un diálogo del kit (pago, formulario, confirmación)', () => {
    expect(s).toMatch(/querySelector\('\[role="dialog"\]'\)/)
  })
  it('el RFC no se sale de su tarjeta a 390', () => {
    expect(s).toMatch(/font-mono text-sm text-slate-400 break-all/)
  })
})
