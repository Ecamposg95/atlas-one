import { describe, it, expect } from 'vitest'

import { contarPorEstado, filtrarLista, iconoEstado } from '../lista'
import type { FilaLista } from '../../../../api/conteos'

const fila = (sku: string, nombre: string, estado: FilaLista['estado'], marca: string | null = null): FilaLista => ({
  producto: { variant_id: sku, product_id: 'p-' + sku, nombre, marca, marca_id: null, modelo: null, descripcion: null,
    precio: '100', talla: 'M', color: null, sku, barcode: sku, foto: null, departamento: 'Playeras' },
  sistema: '1', contado: estado === 'pendiente' ? '0' : '1', estado, corregida: false, line_id: estado === 'pendiente' ? null : 1,
})
const filas = [fila('A', 'Zegna · Playera', 'revisado', 'Zegna'), fila('B', 'Camisa', 'pendiente'), fila('C', 'Gorra', 'diferencia')]

describe('filtrarLista', () => {
  it('filtra por estado y "todos" deja todo', () => {
    expect(filtrarLista(filas, 'pendientes', '').map((f) => f.producto.sku)).toEqual(['B'])
    expect(filtrarLista(filas, 'revisados', '').map((f) => f.producto.sku)).toEqual(['A', 'C'])
    expect(filtrarLista(filas, 'todos', '')).toHaveLength(3)
  })
  it('busca por nombre, marca, SKU o código sin importar mayúsculas ni acentos', () => {
    expect(filtrarLista(filas, 'todos', 'zegna').map((f) => f.producto.sku)).toEqual(['A'])
    expect(filtrarLista(filas, 'todos', 'c').map((f) => f.producto.sku)).toEqual(['B', 'C'])
    expect(filtrarLista(filas, 'pendientes', 'gorra')).toEqual([])
  })
})

describe('contarPorEstado', () => {
  it('cuenta pendientes, revisados (incluye diferencia) y total', () => {
    expect(contarPorEstado(filas)).toEqual({ pendientes: 1, revisados: 2, total: 3 })
  })
})

describe('iconoEstado', () => {
  it('da paloma verde, alerta ámbar o círculo gris', () => {
    expect(iconoEstado('revisado')).toEqual({ icono: 'fa-circle-check', clase: 'text-emerald-400', texto: 'Revisado' })
    expect(iconoEstado('diferencia')).toEqual({ icono: 'fa-triangle-exclamation', clase: 'text-amber-400', texto: 'Con diferencia' })
    expect(iconoEstado('pendiente')).toEqual({ icono: 'fa-circle', clase: 'text-slate-500', texto: 'Pendiente' })
  })
})
