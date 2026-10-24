import type { AgruparValuacion, ValuacionInventario } from '../api/reports'
import { porcentaje } from './porcentaje'

export const ETIQUETA_GRUPO: Record<AgruparValuacion, string> = {
  sucursal: 'Sucursal',
  departamento: 'Departamento',
  marca: 'Marca',
}

/** Celda CSV: comillas si trae coma, comilla o salto de línea (RFC 4180). */
function celda(v: string | number): string {
  const s = typeof v === 'number' ? String(v) : v
  return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}

/**
 * CSV del desglose + fila TOTAL. Números crudos (sin "$" ni separador de
 * miles) para que Excel los sume. "% del valor" = parte del valor a venta
 * sobre el total consultado (100.0 en TOTAL; 0.0 si no hay nada). Sin la
 * columna de costo cuando el rol no la ve (`ve_costo=false`): un gerente no
 * exporta lo que no ve en pantalla. Empieza con BOM: sin él Excel en Windows
 * lee los acentos como basura.
 */
export function csvValuacion(d: ValuacionInventario): string {
  const cabecera = [ETIQUETA_GRUPO[d.agrupar], 'Piezas', 'SKUs', 'Valor a venta', '% del valor']
  if (d.ve_costo) cabecera.push('Valor a costo')
  cabecera.push('Piezas sin costo')
  const total = d.totales.valor_venta

  const fila = (nombre: string, piezas: number, skus: number, venta: number, pct: number, costo: number | null, sinCosto: number) => {
    const cols: (string | number)[] = [nombre, piezas, skus, venta.toFixed(2), pct.toFixed(1)]
    if (d.ve_costo) cols.push((costo ?? 0).toFixed(2))
    cols.push(sinCosto)
    return cols.map(celda).join(',')
  }

  const lineas = [cabecera.map(celda).join(',')]
  for (const g of d.grupos) {
    lineas.push(fila(g.nombre, g.piezas, g.skus, g.valor_venta, porcentaje(g.valor_venta, total), g.valor_costo, g.piezas_sin_costo))
  }
  const t = d.totales
  lineas.push(fila('TOTAL', t.piezas, t.skus, t.valor_venta, total > 0 ? 100 : 0, t.valor_costo, t.piezas_sin_costo))
  return '﻿' + lineas.join('\r\n')
}

/** Descarga `csv` como archivo (mismo mecanismo que `reportsApi.exportCsv`). */
export function descargarCsv(csv: string, nombre: string): void {
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = nombre
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}
