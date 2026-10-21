import { useEffect, useState, useCallback } from 'react'
import { quotesApi, type Quote, type QuoteStats } from '../../api/quotes'
import { DaxCard } from '../../components/ui/DaxCard'
import { Spinner } from '../../components/ui/Spinner'
import { Badge } from '../../components/ui/Badge'
import { Modal } from '../../components/ui/Modal'
import { CabeceraPagina } from '../../components/ui/CabeceraPagina'
import { ListaTarjetas } from '../../components/ui/ListaTarjetas'
import { TarjetaFila } from '../../components/ui/TarjetaFila'
import { useEsTelefono } from '../../hooks/useIsMobile'
import { Link } from 'react-router-dom'
import { formatCurrency } from '../../utils/currency'
import { toast } from '../../store/toastStore'
import { confirm as confirmDialog } from '../../components/ui/ConfirmDialog'
import { ErrorState } from '../../components/ui/ErrorState'

const apiErrorMessage = (err: unknown, fallback: string) => {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return typeof detail === 'string' && detail.trim() ? detail : fallback
}

type Variante = 'green' | 'red' | 'blue' | 'yellow'
const statusVariant = (s: string): Variante =>
  s === 'PAID' ? 'green' : s === 'CANCELLED' ? 'red' : s === 'PENDING' ? 'blue' : 'yellow'

const quoteLabel = (q: Quote) =>
  q.series && q.folio ? `${q.series}-${String(q.folio).padStart(4, '0')}` : q.id.slice(0, 8)
const fecha = (s: string) => new Date(s).toLocaleDateString('es-MX', { day: '2-digit', month: 'short' })

export function Quotes() {
  const [quotes, setQuotes] = useState<Quote[]>([])
  const [stats, setStats] = useState<QuoteStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<Quote | null>(null)
  const [converting, setConverting] = useState<string | null>(null)
  const [loadError, setLoadError] = useState(false)
  const esTelefono = useEsTelefono()

  const load = useCallback(async () => {
    setLoading(true)
    setLoadError(false)
    try {
      const [listRes, statsRes] = await Promise.all([
        quotesApi.list({ limit: 100 }),
        quotesApi.getStats().catch(() => null),
      ])
      setQuotes(listRes?.items ?? [])
      if (statsRes) setStats(statsRes)
    } catch { setLoadError(true) } finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [])

  const handleConvert = async (q: Quote) => {
    const ok = await confirmDialog({
      title: `Convertir cotización ${quoteLabel(q)} a venta`,
      message: `Se creará la venta y el cobro se registrará en EFECTIVO por el total de ${formatCurrency(q.total_amount)}.`,
      variant: 'warning',
      confirmText: 'Convertir a venta',
    })
    if (!ok) return
    setConverting(q.id)
    try {
      const res = await quotesApi.convertToSale(q.id, 'CASH')
      toast.success(`Venta creada: ${res.new_folio}`)
      load(); setSelected(null)
    } catch (err) {
      toast.error(apiErrorMessage(err, 'No se pudo convertir la cotización a venta'))
    } finally { setConverting(null) }
  }

  const handleDelete = async (q: Quote) => {
    const ok = await confirmDialog({
      title: 'Eliminar cotización',
      message: `Se eliminará la cotización ${quoteLabel(q)} por ${formatCurrency(q.total_amount)}. Esta acción no se puede deshacer.`,
      variant: 'danger',
      confirmText: 'Eliminar',
    })
    if (!ok) return
    try {
      await quotesApi.delete(q.id); load(); setSelected(null)
    } catch (err) {
      toast.error(apiErrorMessage(err, 'No se pudo eliminar la cotización'))
    }
  }

  return (
    <div className="space-y-5">
      <CabeceraPagina
        titulo={<div className="flex items-center gap-3">
          <i className="fa-solid fa-file-invoice text-indigo-400 text-xl" />
          <h1 className="text-2xl font-black text-white">Cotizaciones</h1>
        </div>}
        accionPrincipal={<Link to="/quotes/new" className="dax-btn-primary text-xs">
          <i className="fa-solid fa-plus" /> Nueva Cotización
        </Link>}
      />

      {/* KPIs */}
      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[
            { label: 'Total cotizaciones', value: String(stats.total_count), icon: 'fa-file-invoice', color: 'text-white' },
            { label: 'Monto total', value: formatCurrency(stats.total_amount), icon: 'fa-coins', color: 'text-indigo-400' },
            { label: 'Pendientes', value: String(stats.pending_count), icon: 'fa-clock', color: 'text-amber-400' },
            { label: 'Monto pendiente', value: formatCurrency(stats.pending_amount), icon: 'fa-chart-bar', color: 'text-amber-400' },
          ].map((k) => (
            <DaxCard key={k.label}>
              <div className="flex items-center gap-2 mb-1">
                <i className={`fa-solid ${k.icon} text-slate-500 text-xs`} />
                <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">{k.label}</p>
              </div>
              <p className={`text-xl font-black tabular-nums ${k.color}`}>{k.value}</p>
            </DaxCard>
          ))}
        </div>
      )}

      {/* Lista */}
      <DaxCard padding={false}>
        {loadError ? (
          <ErrorState onRetry={load} />
        ) : esTelefono ? (
          <ListaTarjetas cargando={loading} vacio={quotes.length === 0} textoVacio="Sin cotizaciones" className="p-3">
            {quotes.map((q) => (
              <TarjetaFila key={q.id}
                titulo={quoteLabel(q)}
                subtitulo={`${fecha(q.created_at)} · ${q.customer_name ?? 'Sin cliente'}`}
                importe={formatCurrency(q.total_amount)}
                estado={<Badge variant={statusVariant(q.status)}>{q.status}</Badge>}
                onClick={() => setSelected(q)}
              />
            ))}
          </ListaTarjetas>
        ) : loading ? <Spinner text="Cargando cotizaciones..." /> : quotes.length === 0 ? (
          <div className="p-12 text-center text-slate-600">Sin cotizaciones</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="dax-table w-full">
              <thead>
                <tr>
                  <th>Folio</th>
                  <th>Fecha</th>
                  <th>Cliente</th>
                  <th className="text-right">Total</th>
                  <th>Estado</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {quotes.map((q) => (
                  <tr key={q.id}>
                    <td className="font-mono text-indigo-400 text-xs">{quoteLabel(q)}</td>
                    <td className="text-xs text-slate-400">{fecha(q.created_at)}</td>
                    <td className="text-sm text-slate-300">{q.customer_name ?? <span className="text-slate-600 italic">Sin cliente</span>}</td>
                    <td className="text-right font-semibold text-indigo-400 tabular-nums">{formatCurrency(q.total_amount)}</td>
                    <td><Badge variant={statusVariant(q.status)}>{q.status}</Badge></td>
                    <td>
                      <button onClick={() => setSelected(q)} aria-label={`Ver ${quoteLabel(q)}`} className="dax-btn-icon text-slate-500 hover:text-white text-xs">
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
        title={<span>Cotización <span className="font-mono text-indigo-400">{selected ? quoteLabel(selected) : ''}</span></span>}
        footer={selected?.status === 'PENDING' ? (
          <>
            <button
              onClick={() => handleConvert(selected)}
              disabled={converting === selected.id}
              className="dax-btn-primary flex-1 justify-center disabled:opacity-40">
              {converting === selected.id ? <i className="fa-solid fa-spinner fa-spin" /> : <><i className="fa-solid fa-cash-register" /> Convertir a Venta</>}
            </button>
            <button onClick={() => handleDelete(selected)} aria-label="Eliminar cotización" className="dax-btn-danger text-xs">
              <i className="fa-solid fa-trash" />
            </button>
          </>
        ) : undefined}>
        {selected && (
          <>
            <div className="space-y-2 text-sm mb-4">
              <div className="flex justify-between"><span className="text-slate-500">Cliente</span><span>{selected.customer_name ?? 'Sin cliente'}</span></div>
              <div className="flex justify-between"><span className="text-slate-500">Fecha</span><span>{new Date(selected.created_at).toLocaleString('es-MX')}</span></div>
              <div className="flex justify-between"><span className="text-slate-500">Estado</span><Badge variant={statusVariant(selected.status)}>{selected.status}</Badge></div>
            </div>

            {esTelefono ? (
              <ul className="divide-y divide-slate-700/40 text-xs mb-4">
                {(selected.lines ?? []).map((item) => (
                  <li key={item.id} className="py-2 flex justify-between gap-3">
                    <span className="min-w-0">
                      <span className="block font-semibold text-white truncate">{item.description ?? item.sku ?? '—'}</span>
                      <span className="block text-slate-500 tabular-nums">{item.quantity} × {formatCurrency(item.unit_price)}</span>
                    </span>
                    <span className="font-semibold tabular-nums shrink-0">{formatCurrency(item.total_line)}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <table className="dax-table w-full text-xs mb-4">
                <thead><tr><th>Producto</th><th className="text-right">Cant.</th><th className="text-right">Precio</th><th className="text-right">Total</th></tr></thead>
                <tbody>
                  {(selected.lines ?? []).map((item) => (
                    <tr key={item.id}>
                      <td>{item.description ?? item.sku ?? '—'}</td>
                      <td className="text-right">{item.quantity}</td>
                      <td className="text-right">{formatCurrency(item.unit_price)}</td>
                      <td className="text-right font-semibold">{formatCurrency(item.total_line)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}

            <div className="space-y-1 text-sm border-t border-slate-700/50 pt-3">
              <div className="flex justify-between text-slate-400"><span>Subtotal</span><span>{formatCurrency(selected.subtotal)}</span></div>
              {selected.tax_amount > 0 && <div className="flex justify-between text-slate-400"><span>IVA</span><span>{formatCurrency(selected.tax_amount)}</span></div>}
              <div className="flex justify-between font-black text-white text-base"><span>Total</span><span>{formatCurrency(selected.total_amount)}</span></div>
            </div>
          </>
        )}
      </Modal>
    </div>
  )
}
