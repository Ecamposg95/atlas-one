import { useEffect, useState, useCallback } from 'react'
import { salesApi } from '../../api/sales'
import { DaxCard } from '../../components/ui/DaxCard'
import { Spinner } from '../../components/ui/Spinner'
import { Badge } from '../../components/ui/Badge'
import type { SalesDocument } from '../../types/sales'
import { saleLabel } from '../../types/sales'
import { formatCurrency } from '../../utils/currency'
import { ErrorState } from '../../components/ui/ErrorState'

export function Seguimiento() {
  const [orders, setOrders] = useState<SalesDocument[]>([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<SalesDocument | null>(null)
  const [loadError, setLoadError] = useState(false)

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
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <i className="fa-solid fa-clipboard-check text-indigo-400 text-xl" />
          <h1 className="text-2xl font-black text-white">Pedidos</h1>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-slate-500 text-xs">{orders.length} pedidos</span>
          <button onClick={load} className="dax-btn-secondary text-xs">
            <i className="fa-solid fa-rotate-right" /> Actualizar
          </button>
        </div>
      </div>

      <DaxCard padding={false}>
        {loading ? <Spinner text="Cargando pedidos..." /> : loadError ? (
          <ErrorState onRetry={load} />
        ) : orders.length === 0 ? (
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
                    <td className="text-xs text-slate-400">
                      {new Date(s.created_at).toLocaleString('es-MX', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}
                    </td>
                    <td className="text-sm">{s.customer_name ?? <span className="text-slate-600 italic">Público general</span>}</td>
                    <td className="text-right font-semibold text-emerald-400 tabular-nums">{formatCurrency(s.total_amount)}</td>
                    <td><Badge variant="blue">{s.status}</Badge></td>
                    <td>
                      <button onClick={() => setSelected(s)} className="text-slate-500 hover:text-white text-xs">
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

      {/* Modal detalle */}
      {selected && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm" onClick={() => setSelected(null)}>
          <div className="dax-card p-6 w-full max-w-lg max-h-[80vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <div>
                <p className="text-[10px] text-slate-500 uppercase tracking-widest">Pedido</p>
                <p className="text-xl font-black text-indigo-400 font-mono">{saleLabel(selected)}</p>
              </div>
              <button onClick={() => setSelected(null)} className="text-slate-500 hover:text-white"><i className="fa-solid fa-xmark text-lg" /></button>
            </div>

            <div className="space-y-2 text-sm mb-4">
              <div className="flex justify-between"><span className="text-slate-500">Sucursal</span><span>{selected.branch_name ?? '—'}</span></div>
              <div className="flex justify-between"><span className="text-slate-500">Cliente</span><span>{selected.customer_name ?? 'Público general'}</span></div>
              <div className="flex justify-between"><span className="text-slate-500">Fecha</span><span>{new Date(selected.created_at).toLocaleString('es-MX')}</span></div>
            </div>

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

            <div className="flex justify-between font-black text-white border-t border-slate-700/50 pt-3">
              <span>Total</span><span className="text-emerald-400">{formatCurrency(selected.total_amount)}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
