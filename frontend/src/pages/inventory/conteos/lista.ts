import type { EstadoFila, FilaLista } from '../../../api/conteos'

export type FiltroLista = 'pendientes' | 'revisados' | 'todos'

const plano = (s: string | null | undefined) =>
  (s ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()

/** "Revisados" incluye las filas con diferencia: ya se escanearon, solo no cuadran. */
export function filtrarLista(filas: FilaLista[], filtro: FiltroLista, busqueda: string, resaltada?: string | null): FilaLista[] {
  const q = plano(busqueda.trim())
  return filas.filter((f) => {
    // La fila recién leída se queda a la vista aunque el filtro ya no la incluya (en su lugar).
    if (resaltada && f.producto.variant_id === resaltada) return true
    if (filtro === 'pendientes' && f.estado !== 'pendiente') return false
    if (filtro === 'revisados' && f.estado === 'pendiente') return false
    if (!q) return true
    const p = f.producto
    return [p.nombre, p.marca, p.sku, p.barcode, p.modelo].some((c) => plano(c).includes(q))
  })
}

export function contarPorEstado(filas: FilaLista[]): { pendientes: number; revisados: number; total: number } {
  const pendientes = filas.filter((f) => f.estado === 'pendiente').length
  return { pendientes, revisados: filas.length - pendientes, total: filas.length }
}

export function iconoEstado(estado: EstadoFila): { icono: string; clase: string; texto: string } {
  if (estado === 'revisado') return { icono: 'fa-circle-check', clase: 'text-emerald-400', texto: 'Revisado' }
  if (estado === 'diferencia') return { icono: 'fa-triangle-exclamation', clase: 'text-amber-400', texto: 'Con diferencia' }
  return { icono: 'fa-circle', clase: 'text-slate-500', texto: 'Pendiente' }
}
