import { useEffect, useState, useCallback } from 'react'
import { salesApi } from '../../api/sales'
import { DaxCard } from '../../components/ui/DaxCard'
import { Spinner } from '../../components/ui/Spinner'
import { Badge } from '../../components/ui/Badge'
import { Modal } from '../../components/ui/Modal'
import { CabeceraPagina } from '../../components/ui/CabeceraPagina'
import { ListaTarjetas } from '../../components/ui/ListaTarjetas'
import { TarjetaFila } from '../../components/ui/TarjetaFila'
import { useEsTelefono } from '../../hooks/useIsMobile'
import type { SalesDocument } from '../../types/sales'
import { saleLabel } from '../../types/sales'
import { formatCurrency } from '../../utils/currency'
import { ErrorState } from '../../components/ui/ErrorState'

const fechaHora = (s: string) =>
  new Date(s).toLocaleString('es-MX', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })

export function Seguimiento() {
  const [orders, setOrders] = useState<SalesDocument[]>([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<SalesDocument | null>(null)
  const [loadError, setLoadError] = useState(false)
  const esTelefono = useEsTelefono()

  const load = useCallback(async () => {
    setLoading(true)
    setLoadError(false)
    try {
      const res = await salesApi.list({ status: 'PENDING', limit: 100 })
      setOrders(res.items ?? [])
    } catch { setLoadError(true) } finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [])

  return (
    <div className="space-y-5">
      <CabeceraPagina
        titulo={<div className="flex items-center gap-3">
          <i className="fa-solid fa-clipboard-check text-indigo-400 text-xl" />
          <h1 className="text-2xl font-black text-white">Pedidos</h1>
        </div>}
        acciones={<>
          <span className="text-slate-500 text-xs">{orders.length} pedidos</span>
          <button onClick={load} className="dax-btn-secondary text-xs">
            <i className="fa-solid fa-rotate-right" /> Actualizar
          </button>
        </>}
      />

      <DaxCard padding={false}>
        {loadError ? (
          <ErrorState onRetry={load} />
        ) : esTelefono ? (
          <ListaTarjetas cargando={loading} vacio={orders.length === 0} textoVacio="Sin pedidos abiertos" className="p-3">
            {orders.map((s) => (
              <TarjetaFila key={s.id}
                titulo={saleLabel(s)}
                subtitulo={`${s.branch_name ?? '—'} · ${fechaHora(s.created_at)} · ${s.customer_name ?? 'Público general'}`}
                importe={<span className="text-emerald-400">{formatCurrency(s.total_amount)}</span>}
                estado={<Badge variant="blue">{s.status}</Badge>}
                onClick={() => setSelected(s)}
              />
            ))}
          </ListaTarjetas>
        ) : loading ? <Spinner text="Cargando pedidos..." /> : orders.length === 0 ? (
          <div className="p-12 text-center">
            <i className="fa-solid fa-circle-check text-emerald-600 text-3xl mb-3 block" />
            <p className="text-slate-600">Sin pedidos abiertos</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="dax-table w-full">
              <thead>
                <tr>
                  <th>Folio</th>
                  <th>Sucursal</th>
                  <th>Fecha</th>
                  <th>Cliente</th>
                  <th className="text-right">Total</th>
                  <th>Estado</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {orders.map((s) => (
                  <tr key={s.id}>
                    <td className="font-mono text-indigo-400 text-xs">{saleLabel(s)}</td>
                    <td className="text-xs text-slate-400">{s.branch_name ?? '—'}</td>
                    <td className="text-xs text-slate-400">{fechaHora(s.created_at)}</td>
                    <td className="text-sm">{s.customer_name ?? <span className="text-slate-600 italic">Público general</span>}</td>
                    <td className="text-right font-semibold text-emerald-400 tabular-nums">{formatCurrency(s.total_amount)}</td>
                    <td><Badge variant="blue">{s.status}</Badge></td>
                    <td>
                      <button onClick={() => setSelected(s)} aria-label={`Ver ${saleLabel(s)}`} className="dax-btn-icon text-slate-500 hover:text-white text-xs">
                        <i className="fa-solid fa-eye" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </DaxCard>

      {/* Detalle */}
      <Modal open={!!selected} onClose={() => setSelected(null)} size="lg"
        title={<span>Pedido <span className="font-mono text-indigo-400">{selected ? saleLabel(selected) : ''}</span></span>}>
        {selected && (
          <>
            <div className="space-y-2 text-sm mb-4">
              <div className="flex justify-between"><span className="text-slate-500">Sucursal</span><span>{selected.branch_name ?? '—'}</span></div>
              <div className="flex justify-between"><span className="text-slate-500">Cliente</span><span>{selected.customer_name ?? 'Público general'}</span></div>
              <div className="flex justify-between"><span className="text-slate-500">Fecha</span><span>{new Date(selected.created_at).toLocaleString('es-MX')}</span></div>
            </div>

            {esTelefono ? (
              <ul className="divide-y divide-slate-700/40 text-xs mb-4">
                {selected.lines?.map((line, i) => (
                  <li key={i} className="py-2 flex justify-between gap-3">
                    <span className="min-w-0">
                      <span className="block font-semibold text-white truncate">{line.description ?? line.sku ?? '—'}</span>
                      <span className="block text-slate-500 tabular-nums">{line.quantity} × {formatCurrency(Number(line.unit_price))}</span>
                    </span>
                    <span className="font-semibold tabular-nums shrink-0">{formatCurrency(Number(line.total_line))}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <table className="dax-table w-full text-xs mb-4">
                <thead><tr><th>Producto</th><th className="text-right">Cant.</th><th className="text-right">Precio</th><th className="text-right">Total</th></tr></thead>
                <tbody>
                  {selected.lines?.map((line, i) => (
                    <tr key={i}>
                      <td>{line.description ?? line.sku ?? '—'}</td>
                      <td className="text-right">{line.quantity}</td>
                      <td className="text-right">{formatCurrency(Number(line.unit_price))}</td>
                      <td className="text-right font-semibold">{formatCurrency(Number(line.total_line))}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}

            <div className="flex justify-between font-black text-white border-t border-slate-700/50 pt-3">
              <span>Total</span><span className="text-emerald-400">{formatCurrency(selected.total_amount)}</span>
            </div>
          </>
        )}
      </Modal>
    </div>
  )
}
