import { describe, expect, it } from 'vitest'
import { elegirSucursalParaImpresora } from './sucursalParaImpresora'

const hq = { id: 14, name: 'HQ - Novedades Kaory', branch_type: 'HQ', can_sell: false }
const tienda = { id: 15, name: 'Pino Suárez', branch_type: 'STORE', can_sell: true }
const roma = { id: 20, name: 'Eleven Fashion Roma', branch_type: 'STORE', can_sell: true }
const otra = { id: 21, name: 'Eleven Polanco', branch_type: 'STORE', can_sell: true }

describe('elegirSucursalParaImpresora', () => {
  it('con una sola sucursal que vende, es esa aunque la dueña esté asignada a la matriz', () => {
    // Kaory: Alicia está en la HQ (14, no vende) y la impresora vive en Pino Suárez.
    expect(elegirSucursalParaImpresora(14, [hq, tienda])).toBe(tienda)
  })

  it('con varias que venden, manda la sucursal asignada a la dueña', () => {
    expect(elegirSucursalParaImpresora(21, [roma, otra])).toBe(otra)
  })

  it('con varias que venden y sin sucursal asignada, no adivina', () => {
    expect(elegirSucursalParaImpresora(null, [roma, otra])).toBeNull()
  })

  it('con una sola sucursal, es esa aunque no venda', () => {
    expect(elegirSucursalParaImpresora(null, [hq])).toBe(hq)
  })

  it('sin sucursales no hay nada que elegir', () => {
    expect(elegirSucursalParaImpresora(20, [])).toBeNull()
  })
})
