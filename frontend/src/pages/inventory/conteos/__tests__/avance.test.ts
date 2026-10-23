// frontend/src/pages/inventory/conteos/__tests__/avance.test.ts
import { describe, it, expect } from 'vitest'

import { num, porcentajeAvance, seccionesReporte, textoDiferencia } from '../avance'
import type { Reporte } from '../../../../api/conteos'

describe('porcentajeAvance', () => {
  it('es 0 sin esperadas y se acota a 100', () => {
    expect(porcentajeAvance(0, 0)).toBe(0)
    expect(porcentajeAvance(3, 0)).toBe(0)
    expect(porcentajeAvance(5, 10)).toBe(50)
    expect(porcentajeAvance(12, 10)).toBe(100)
  })
})

describe('textoDiferencia', () => {
  it('redacta faltan/sobra/cuadra', () => {
    expect(textoDiferencia(-3)).toBe('faltan 3')
    expect(textoDiferencia(-1)).toBe('falta 1')
    expect(textoDiferencia(1)).toBe('sobra 1')
    expect(textoDiferencia(2)).toBe('sobran 2')
    expect(textoDiferencia(0)).toBe('cuadra')
  })
})

describe('seccionesReporte', () => {
  const fila = (sku: string, diferencia: string) => ({
    variant_id: sku, sku, nombre: sku, marca: null, talla: null, color: null, departamento: null,
    sistema: '3', contado: '1', diferencia,
  })
  const reporte: Reporte = {
    estado: 'ABIERTO', generado_en: '2026-10-22T10:00:00Z',
    alcance: { sucursal: 'Roma', departamento: 'Playeras' },
    totales: { faltantes_piezas: '5', sobrantes_piezas: '1', fuera_de_alcance_piezas: '1', desconocidos: 2 },
    faltantes: [fila('A', '-3'), fila('B', '-2')],
    sobrantes: [fila('C', '1')],
    fuera_de_alcance: [fila('D', '0')],
    desconocidos: [{ codigo: 'X', contado: '1' }, { codigo: 'Y', contado: '1' }],
  }

  it('devuelve las cuatro secciones con título, conteo de filas y piezas', () => {
    const s = seccionesReporte(reporte)
    expect(s.map((x) => x.clave)).toEqual(['faltantes', 'sobrantes', 'fuera_de_alcance', 'desconocidos'])
    expect(s[0]).toMatchObject({ titulo: 'Faltantes', filas: 2, piezas: 5 })
    expect(s[1]).toMatchObject({ titulo: 'Sobrantes', filas: 1, piezas: 1 })
    expect(s[2]).toMatchObject({ titulo: 'Fuera de departamento', filas: 1, piezas: 1 })
    expect(s[3]).toMatchObject({ titulo: 'Desconocidos', filas: 2, piezas: 2 })
  })
})

describe('num', () => {
  it('convierte el Decimal en cadena y tolera vacíos', () => {
    expect(num('3.00')).toBe(3)
    expect(num(null)).toBe(0)
    expect(num('x')).toBe(0)
  })
})
