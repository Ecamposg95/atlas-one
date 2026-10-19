import { describe, it, expect } from 'vitest'
import { csvValuacion } from './valuacionCsv'
import type { ValuacionInventario } from '../api/reports'

const base: ValuacionInventario = {
  agrupar: 'marca', branch_id: null, ve_costo: true,
  totales: { piezas: 19, skus: 3, valor_venta: 10200, valor_costo: 2000, piezas_sin_costo: 14, skus_sin_costo: 2 },
  grupos: [
    { clave: '', nombre: 'Sin marca', piezas: 14, skus: 2, valor_venta: 5200, valor_costo: 0, piezas_sin_costo: 14 },
    { clave: 'abc', nombre: 'Dolce, Gabbana', piezas: 5, skus: 1, valor_venta: 5000, valor_costo: 2000, piezas_sin_costo: 0 },
  ],
}

const lineas = (csv: string) => csv.replace(/^﻿/, '').split('\r\n')

describe('csvValuacion', () => {
  it('empieza con BOM para que Excel lea UTF-8', () => {
    expect(csvValuacion(base).charCodeAt(0)).toBe(0xfeff)
  })

  it('cabecera según el criterio, una fila por grupo y TOTAL al final', () => {
    const l = lineas(csvValuacion(base))
    expect(l[0]).toBe('Marca,Piezas,SKUs,Valor a venta,Valor a costo,Piezas sin costo')
    expect(l[1]).toBe('Sin marca,14,2,5200.00,0.00,14')
    expect(l[3]).toBe('TOTAL,19,3,10200.00,2000.00,14')
    expect(l).toHaveLength(4)
  })

  it('entrecomilla nombres con coma o comillas', () => {
    const l = lineas(csvValuacion(base))
    expect(l[2]).toBe('"Dolce, Gabbana",5,1,5000.00,2000.00,0')
    const conComillas = { ...base, grupos: [{ ...base.grupos[1], nombre: 'Bolsa "XL"' }] }
    expect(lineas(csvValuacion(conComillas))[1]).toBe('"Bolsa ""XL""",5,1,5000.00,2000.00,0')
  })

  it('sin ve_costo no hay columna de costo (el gerente no exporta lo que no ve)', () => {
    const gerente: ValuacionInventario = {
      ...base, agrupar: 'departamento', ve_costo: false,
      totales: { ...base.totales, valor_costo: null },
      grupos: base.grupos.map((g) => ({ ...g, valor_costo: null })),
    }
    const l = lineas(csvValuacion(gerente))
    expect(l[0]).toBe('Departamento,Piezas,SKUs,Valor a venta,Piezas sin costo')
    expect(l[1]).toBe('Sin marca,14,2,5200.00,14')
    expect(l[3]).toBe('TOTAL,19,3,10200.00,14')
  })
})
