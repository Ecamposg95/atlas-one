// frontend/src/pages/inventory/conteos/__tests__/avance.test.ts
import { describe, it, expect } from 'vitest'

import { estadoConteo, num, porcentajeAvance, resumenSeleccion, seccionesReporte, seleccionInicial, seleccionTrasAplicar, textoCancelar, textoDiferencia } from '../avance'
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

describe('seleccionInicial', () => {
  const fila = (sku: string, sistema: string, contado: string, ajustada = false) => ({
    variant_id: sku, sku, nombre: sku, marca: null, talla: null, color: null, departamento: null,
    sistema, contado, diferencia: String(Number(contado) - Number(sistema)), corregida: false, ajustada,
  })
  const rep = {
    estado: 'CERRADO', generado_en: '', alcance: { sucursal: null, departamento: null }, totales: {},
    faltantes: [fila('P', '3', '1'), fila('N', '2', '0'), fila('Y', '2', '1', true)],
    sobrantes: [fila('S', '0', '1')], fuera_de_alcance: [fila('F', '1', '2')], desconocidos: [], ajustes: [], aplicado_en: null,
  } as never
  it('marca escaneadas con diferencia y sobrantes; deja fuera no vistas, fuera de depto y ya ajustadas', () => {
    expect([...seleccionInicial(rep)].sort()).toEqual(['P', 'S'])
  })
  it('resume la selección en tallas y piezas', () => {
    expect(resumenSeleccion(rep, new Set(['P', 'S', 'N']))).toEqual({ tallas: 3, menos: 4, mas: 1 })
  })
})

describe('seleccionTrasAplicar', () => {
  const f = (sku: string, ajustada: boolean) => ({ variant_id: sku, sku, nombre: sku, marca: null, talla: null, color: null, departamento: null, sistema: '3', contado: '1', diferencia: '-2', corregida: false, ajustada })
  it('quita las ya ajustadas y no re-marca las destildadas', () => {
    const r = { faltantes: [f('P', true), f('N', false), f('X', false)], sobrantes: [], fuera_de_alcance: [] } as never
    expect([...seleccionTrasAplicar(new Set(['P', 'N']), r)]).toEqual(['N'])
  })
})

describe('estadoConteo', () => {
  it('abierto en verde; cerrado y cancelado en gris, cada uno con su texto', () => {
    expect(estadoConteo('ABIERTO')).toEqual({ texto: 'Abierto', clase: 'text-emerald-400' })
    expect(estadoConteo('CERRADO')).toEqual({ texto: 'Cerrado', clase: 'text-slate-400' })
    expect(estadoConteo('CANCELADO')).toEqual({ texto: 'Cancelado', clase: 'text-slate-500' })
  })
})

describe('textoCancelar', () => {
  it('dice cuántas piezas se descartan (singular y plural) y que los ajustes en piso se conservan', () => {
    expect(textoCancelar(3)).toBe('Se descarta lo contado (3 piezas). Los ajustes ya hechos en piso se conservan. No se puede deshacer.')
    expect(textoCancelar(1)).toContain('(1 pieza)')
    expect(textoCancelar(0)).toContain('(0 piezas)')
  })
})
