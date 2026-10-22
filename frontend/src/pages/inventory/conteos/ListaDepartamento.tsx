import { useEffect, useMemo, useState } from 'react'

import type { FilaLista } from '../../../api/conteos'
import { ListaTarjetas } from '../../../components/ui/ListaTarjetas'
import { TarjetaFila } from '../../../components/ui/TarjetaFila'
import { useEsTelefono } from '../../../hooks/useIsMobile'
import { num } from './avance'
import { contarPorEstado, filtrarLista, iconoEstado, type FiltroLista } from './lista'

/**
 * Checklist del departamento: todas las tallas del catálogo con su paloma.
 * La pistola palomea desde la pantalla (ConteoSesion); aquí solo se muestra,
 * se filtra y se deja corregir la cantidad de las filas ya escaneadas. La
 * fila recién leída se resalta y se trae a la vista.
 */
export function ListaDepartamento({ filas, resaltada, onCantidad, onFicha }: {
  filas: FilaLista[]
  /** variant_id de la última lectura, para resaltar y hacer scroll. */
  resaltada: string | null
  onCantidad: (fila: FilaLista, qty: number) => void
  onFicha: (fila: FilaLista) => void
}) {
  const esTelefono = useEsTelefono()
  const [filtro, setFiltro] = useState<FiltroLista>('pendientes')
  const [busqueda, setBusqueda] = useState('')
  const visibles = useMemo(() => filtrarLista(filas, filtro, busqueda), [filas, filtro, busqueda])
  const n = contarPorEstado(filas)

  useEffect(() => {
    if (!resaltada) return
    document.getElementById(`fila-${resaltada}`)?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  }, [resaltada, filtro])

  const chip = (valor: FiltroLista, etiqueta: string, cuenta: number) => (
    <button type="button" onClick={() => setFiltro(valor)}
      className={filtro === valor ? 'dax-btn-primary text-xs' : 'dax-btn-secondary text-xs'}>
      {etiqueta} <span className="opacity-70">{cuenta}</span>
    </button>
  )

  const cantidad = (f: FilaLista) => f.line_id === null ? (
    <span className="text-slate-500">{num(f.contado)}</span>
  ) : (
    <input type="number" min={0} inputMode="numeric" className="dax-input w-16 text-center"
      defaultValue={num(f.contado)} key={`${f.line_id}-${f.contado}`}
      onBlur={(e) => {
        if (e.target.value.trim() === '') { e.target.value = String(num(f.contado)); return }
        const v = Number(e.target.value)
        if (Number.isFinite(v) && v >= 0 && v !== num(f.contado)) onCantidad(f, v)
      }} />
  )

  const estadoDe = (f: FilaLista) => {
    const e = iconoEstado(f.estado)
    return <span className={e.clase} title={e.texto}><i className={`fa-solid ${e.icono}`} /> {f.corregida && <i className="fa-solid fa-pen text-indigo-400" title="Ficha corregida" />}</span>
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        {chip('pendientes', 'Pendientes', n.pendientes)}
        {chip('revisados', 'Revisados', n.revisados)}
        {chip('todos', 'Todos', n.total)}
      </div>
      <input className="dax-input w-full" placeholder="Buscar en el departamento…" value={busqueda} onChange={(e) => setBusqueda(e.target.value)} />

      {esTelefono ? (
        <ListaTarjetas vacio={visibles.length === 0} textoVacio={filtro === 'pendientes' ? 'No queda nada pendiente.' : 'Sin filas.'}>
          {visibles.map((f) => (
            <div key={f.producto.variant_id} id={`fila-${f.producto.variant_id}`}
              className={f.producto.variant_id === resaltada ? 'ring-2 ring-indigo-400 rounded-md' : ''}>
              <TarjetaFila
                titulo={f.producto.nombre}
                subtitulo={[f.producto.sku, f.producto.talla, f.producto.color].filter(Boolean).join(' · ')}
                estado={estadoDe(f)}
                datos={[{ etiqueta: 'Sistema', valor: num(f.sistema) }, { etiqueta: 'Contado', valor: cantidad(f) }]}
                acciones={<button type="button" className="dax-btn-ghost text-xs" onClick={() => onFicha(f)}><i className="fa-solid fa-id-card" /> Ficha</button>}
              />
            </div>
          ))}
        </ListaTarjetas>
      ) : (
        <table className="w-full text-sm">
          <thead className="text-xs text-slate-400 uppercase">
            <tr><th className="p-2" /><th className="text-left p-2">Pieza</th><th className="text-left p-2">SKU</th><th className="text-right p-2">Sistema</th><th className="text-right p-2">Contado</th><th className="p-2" /></tr>
          </thead>
          <tbody>
            {visibles.length === 0 && <tr><td colSpan={6} className="p-4 text-center text-slate-500">{filtro === 'pendientes' ? 'No queda nada pendiente.' : 'Sin filas.'}</td></tr>}
            {visibles.map((f) => (
              <tr key={f.producto.variant_id} id={`fila-${f.producto.variant_id}`}
                className={`border-t border-slate-800 ${f.producto.variant_id === resaltada ? 'bg-indigo-500/10' : ''}`}>
                <td className="p-2 text-center">{estadoDe(f)}</td>
                <td className="p-2 text-white">{f.producto.nombre}</td>
                <td className="p-2 text-slate-400">{[f.producto.sku, f.producto.talla].filter(Boolean).join(' · ')}</td>
                <td className="p-2 text-right text-slate-300">{num(f.sistema)}</td>
                <td className="p-2 text-right">{cantidad(f)}</td>
                <td className="p-2 text-right"><button type="button" className="dax-btn-ghost text-xs" onClick={() => onFicha(f)}><i className="fa-solid fa-id-card" /> Ficha</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
