import { useEffect, useState, useCallback } from 'react'
import { salesApi, type SalesStats } from '../../api/sales'
import { printerApi } from '../../api/printer'
import { usePOSStore } from '../../store/posStore'
import { DaxCard } from '../../components/ui/DaxCard'
import { Spinner } from '../../components/ui/Spinner'
import { Badge } from '../../components/ui/Badge'
import type { SalesDocument } from '../../types/sales'
import { saleLabel } from '../../types/sales'
import { ReturnModal } from '../../components/pos/modals/ReturnModal'
import { ReprintPinModal } from '../../components/pos/modals/ReprintPinModal'
import { formatCurrency } from '../../utils/currency'
import { todayStr, daysAgoStr } from '../../utils/dates'
import { toast } from '../../store/toastStore'
import { mensajeReimpresion, pinBloqueado, pinIncorrecto, requierePin } from '../../utils/reimpresion'

const PRESETS = [
  { label: 'Hoy', start: () => todayStr(), end: () => todayStr() },
  { label: 'Ayer', start: () => daysAgoStr(1), end: () => daysAgoStr(1) },
  { label: 'Semana', start: () => daysAgoStr(7), end: () => todayStr() },
  { label: 'Mes', start: () => daysAgoStr(30), end: () => todayStr() },
]

const STATUS_LABELS: Record<string, string> = {
  PAID:             'Pagado',
  CANCELLED:        'Cancelado',
  REFUNDED_PARTIAL: 'Dev. parcial',
  REFUNDED_TOTAL:   'Dev. total',
  PENDING:          'Pendiente',
  DRAFT:            'Borrador',
}

const METHOD_LABELS: Record<string, string> = {
  CASH:         'Efectivo',
  CARD:         'Tarjeta',
  TRANSFER:     'Transferencia',
  STORE_CREDIT: 'Crédito tienda',
  CHECK:        'Cheque',
  MIXED:        'Mixto',
}


export function SalesHistory() {
  const printerName = usePOSStore(s => s.printerName)
  const [reprinting, setReprinting] = useState(false)
  const [sales, setSales] = useState<SalesDocument[]>([])
  const [stats, setStats] = useState<SalesStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [startDate, setStartDate] = useState(daysAgoStr(7))
  const [endDate, setEndDate] = useState(todayStr())
  const [page, setPage] = useState(0)
  const [total, setTotal] = useState(0)
  const [selected, setSel] = useState<SalesDocument | null>(null)
  const [returnSale, setReturnSale] = useState<SalesDocument | null>(null)
  // Venta cuya reimpresión espera el PIN de un supervisor (428 del backend).
  const [ventaPorAutorizar, setVentaPorAutorizar] = useState<SalesDocument | null>(null)
  const LIMIT = 100

  // Track 2 (POS bug-fix): por defecto historial muestra solo ventas
  // realizadas (PAID, REFUNDED_*) y CANCELLED. Excluye PENDING y DRAFT
  // porque son ventas a crédito abiertas / borradores que generan
  // confusión al cajero ("vendí o no?"). Toggle para incluirlos si hace
  // falta auditar.
  const [includeOpenStates, setIncludeOpenStates] = useState(false)

  /**
   * Reimprime un ticket. El backend exige rol gerencial o el PIN de un
   * supervisor (428) salvo que sea una venta propia recién cobrada, así que el
   * primer intento va sin PIN y solo se pide cuando hace falta.
   *
   * Devuelve el mensaje de error si el PIN no sirvió —el modal lo muestra y
   * deja reintentar— o null cuando ya no hay nada pendiente.
   */
  const reprintTicket = async (sale: SalesDocument, pin?: string): Promise<string | null> => {
    if (!printerName) {
      toast.error('Configura una impresora en /printer-settings primero')
      return null
    }
    setReprinting(true)
    try {
      const b64 = await printerApi.getTicketBase64(sale.id, pin)
      if (b64) await printerApi.printViaAgent(printerName, b64)
      toast.success('Ticket enviado a la impresora')
      setVentaPorAutorizar(null)
      return null
    } catch (e: unknown) {
      if (requierePin(e)) {
        setVentaPorAutorizar(sale)
        return null
      }
      // Un PIN equivocado deja el modal abierto para reintentar. El bloqueo por
      // intentos lo cierra: hay que esperar, insistir no sirve. Y cualquier otro
      // conflicto (venta cancelada, sin acceso) también lo cierra con aviso.
      if (pin && pinIncorrecto(e) && !pinBloqueado(e)) return mensajeReimpresion(e)
      toast.error(mensajeReimpresion(e))
      setVentaPorAutorizar(null)
      return null
    } finally {
      setReprinting(false)
    }
  }

  const load = useCallback(async (start: string, end: string, pg: number) => {
    setLoading(true)
    try {
      const params: Record<string, unknown> = {
        start_date: start,
        end_date: end,
        limit: LIMIT,
        skip: pg * LIMIT,
      }
      if (!includeOpenStates) {
        // Estados "cerrados" — ventas reales o devoluciones. Si el backend
        // no soporta este filtro, se filtra en cliente como fallback.
        params.statuses = 'PAID,REFUNDED_PARTIAL,REFUNDED_TOTAL,CANCELLED'
      }
      const [listRes, statsRes] = await Promise.allSettled([
        salesApi.list(params),
        salesApi.getStats({ start_date: start, end_date: end }),
      ])
      if (listRes.status === 'fulfilled') {
        let items = listRes.value?.items ?? []
        if (!includeOpenStates) {
          // Fallback cliente-side: excluir DRAFT/PENDING aunque el backend
          // no haya respetado el query param.
          items = items.filter((s) => !['PENDING', 'DRAFT'].includes(String(s.status)))
        }
        setSales(items)
        setTotal(listRes.value?.total ?? items.length)
      } else {
        setSales([])
      }
      setStats(statsRes.status === 'fulfilled' ? statsRes.value : null)
    } catch {
      setSales([])
    } finally {
      setLoading(false)
    }
  }, [includeOpenStates])

  useEffect(() => { load(startDate, endDate, page) }, [load, page])

  const applyPreset = (p: typeof PRESETS[0]) => {
    const s = p.start(), e = p.end()
    setStartDate(s); setEndDate(e); setPage(0); load(s, e, 0)
  }

  const pages = Math.ceil(total / LIMIT)

  // Estados reales del backend: PAID / CANCELLED / REFUNDED_* / PENDING / DRAFT
  const statusVariant = (s: string) =>
    s === 'PAID' ? 'green'
    : s === 'CANCELLED' ? 'red'
    : s.startsWith('REFUNDED') ? 'blue'
    : 'yellow' // PENDING / DRAFT / desconocidos

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <i className="fa-solid fa-history text-indigo-400 text-xl" />
        <h1 className="text-2xl font-black text-white">Historial de Ventas</h1>
      </div>

      {/* KPIs — 6 cards */}
      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          {[
            { label: 'Total', value: formatCurrency(stats.total_sales), icon: 'fa-coins', color: 'text-emerald-400' },
            { label: 'Transacciones', value: String(stats.total_transactions), icon: 'fa-receipt', color: 'text-white' },
            { label: 'Ticket promedio', value: formatCurrency(stats.average_ticket), icon: 'fa-chart-bar', color: 'text-indigo-400' },
            {
              label: 'Método top',
              value: (() => {
                const top = Object.entries(stats.payment_methods ?? {}).sort((a, b) => b[1] - a[1])[0]?.[0]
                return top ? (METHOD_LABELS[top] ?? top) : '—'
              })(),
              icon: 'fa-credit-card',
              color: 'text-slate-300',
            },
            {
              label: 'Devoluciones',
              value: `${stats.refund_count ?? 0} · ${formatCurrency(stats.refund_total ?? 0)}`,
              icon: 'fa-undo',
              color: 'text-rose-400',
            },
            {
              label: 'Hora pico',
              value: stats.peak_hour ?? '—',
              icon: 'fa-clock',
              color: 'text-purple-400',
            },
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

      {/* Filtros */}
      <div className="flex flex-wrap gap-2 items-center">
        {PRESETS.map((p) => (
          <button
            key={p.label}
            onClick={() => applyPreset(p)}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
              startDate === p.start() && endDate === p.end()
                ? 'bg-indigo-600 text-white'
                : 'bg-slate-700/50 text-slate-400 hover:text-white'
            }`}
          >
            {p.label}
          </button>
        ))}
        <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className="dax-input w-36 text-xs" />
        <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} className="dax-input w-36 text-xs" />
        <button onClick={() => { setPage(0); load(startDate, endDate, 0) }} className="dax-btn-primary text-xs">
          <i className="fa-solid fa-search" /> Filtrar
        </button>
        <label className="ml-2 flex items-center gap-1.5 text-[10px] text-slate-400 cursor-pointer">
          <input
            type="checkbox"
            checked={includeOpenStates}
            onChange={(e) => setIncludeOpenStates(e.target.checked)}
            className="rounded"
          />
          Incluir abiertas/borradores
        </label>
      </div>

      {/* Tabla */}
      <DaxCard padding={false}>
        {loading ? <Spinner text="Cargando ventas..." /> : sales.length === 0 ? (
          <div className="p-12 text-center text-slate-600">Sin ventas en este período</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="dax-table w-full">
              <thead>
                <tr>
                  <th>Folio</th>
                  <th>Fecha</th>
                  <th>Cliente</th>
                  <th className="text-right">Total</th>
                  <th>Pago</th>
                  <th>Estado</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {sales.map((s) => (
                  <tr
                    key={s.id}
                    onClick={() => setSel(s)}
                    className="cursor-pointer hover:bg-indigo-500/5 transition-colors"
                  >
                    <td className="font-mono text-indigo-400 text-xs">{saleLabel(s)}</td>
                    <td className="text-xs text-slate-400">
                      {new Date(s.created_at).toLocaleString('es-MX', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}
                    </td>
                    <td className="text-sm">{s.customer_name ?? <span className="text-slate-600 italic">Público general</span>}</td>
                    <td className="text-right font-semibold text-emerald-400">{formatCurrency(s.total_amount)}</td>
                    <td>
                      {s.payments?.map((p, i) => (
                        <span key={i} className="dax-badge dax-badge-blue mr-1">{METHOD_LABELS[p.method] ?? p.method}</span>
                      ))}
                    </td>
                    <td><Badge variant={statusVariant(s.status) as 'green' | 'red' | 'blue' | 'yellow'}>{STATUS_LABELS[s.status] ?? s.status}</Badge></td>
                    <td className="text-right">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={(e) => { e.stopPropagation(); setSel(s) }}
                          className="px-3 py-2 rounded-lg text-xs font-bold bg-indigo-500/15 text-indigo-300 hover:bg-indigo-500/25 transition-colors"
                          title="Ver detalle"
                        >
                          <i className="fa-solid fa-eye" /> Ver
                        </button>
                        <button
                          onClick={(e) => { e.stopPropagation(); reprintTicket(s) }}
                          disabled={!printerName}
                          className="px-3 py-2 rounded-lg text-xs font-bold bg-indigo-500/15 text-indigo-300 hover:bg-indigo-500/25 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                          title={printerName ? 'Reimprimir ticket' : 'Configura una impresora'}
                        >
                          <i className="fa-solid fa-print" /> Reimprimir
                        </button>
                        {(s.status === 'PAID' || s.status === 'REFUNDED_PARTIAL') && (
                          <button
                            onClick={(e) => { e.stopPropagation(); setReturnSale(s) }}
                            className="px-3 py-2 rounded-lg text-xs font-bold bg-rose-500/15 text-rose-300 hover:bg-rose-500/25 transition-colors"
                            title="Iniciar devolución"
                          >
                            <i className="fa-solid fa-undo" /> Devolver
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {pages > 1 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-slate-700/50">
            <button onClick={() => { const np = page - 1; setPage(np); load(startDate, endDate, np) }} disabled={page === 0} className="dax-btn-secondary text-xs disabled:opacity-40">← Anterior</button>
            <span className="text-slate-500 text-xs">Pág. {page + 1} / {pages} · {total} registros</span>
            <button onClick={() => { const np = page + 1; setPage(np); load(startDate, endDate, np) }} disabled={page >= pages - 1} className="dax-btn-secondary text-xs disabled:opacity-40">Siguiente →</button>
          </div>
        )}
      </DaxCard>

      {/* Modal detalle */}
      {selected && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm" onClick={() => setSel(null)}>
          <div className="dax-card p-6 w-full max-w-lg max-h-[80vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <div>
                <p className="text-[10px] text-slate-500 uppercase tracking-widest">Folio</p>
                <p className="text-xl font-black text-indigo-400 font-mono">{saleLabel(selected)}</p>
              </div>
              <button onClick={() => setSel(null)} className="text-slate-500 hover:text-white"><i className="fa-solid fa-xmark text-lg" /></button>
            </div>

            <div className="space-y-3 text-sm">
              <div className="flex justify-between"><span className="text-slate-500">Cliente</span><span>{selected.customer_name ?? 'Público general'}</span></div>
              <div className="flex justify-between"><span className="text-slate-500">Fecha</span><span>{new Date(selected.created_at).toLocaleString('es-MX')}</span></div>
              <div className="flex justify-between"><span className="text-slate-500">Estado</span><Badge variant={statusVariant(selected.status) as 'green' | 'red' | 'blue' | 'yellow'}>{STATUS_LABELS[selected.status] ?? selected.status}</Badge></div>
            </div>

            <div className="mt-4 border-t border-slate-700/50 pt-4">
              <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2">Artículos</p>
              <table className="dax-table w-full text-xs">
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
            </div>

            <div className="mt-4 border-t border-slate-700/50 pt-4 space-y-1 text-sm">
              <div className="flex justify-between text-slate-400"><span>Subtotal</span><span>{formatCurrency(Number(selected.subtotal))}</span></div>
              {Number(selected.tax_amount) > 0 && <div className="flex justify-between text-slate-400"><span>IVA</span><span>{formatCurrency(Number(selected.tax_amount))}</span></div>}
              <div className="flex justify-between font-black text-white text-base pt-1"><span>Total</span><span>{formatCurrency(selected.total_amount)}</span></div>
            </div>

            {/* Acciones */}
            <div className="mt-4 border-t border-slate-700/50 pt-4 flex flex-col gap-2">
              <button
                disabled={reprinting || !printerName}
                onClick={() => reprintTicket(selected)}
                className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl text-xs font-bold transition-colors disabled:opacity-40"
                style={{ background: printerName ? 'rgba(99,102,241,0.15)' : 'rgba(100,116,139,0.1)', color: printerName ? '#a5b4fc' : '#64748b' }}
                title={printerName ? 'Reimprimir vía agente local' : 'Configura una impresora en /printer-settings primero'}
              >
                {reprinting
                  ? <i className="fa-solid fa-spinner fa-spin" />
                  : <><i className="fa-solid fa-print" /> {printerName ? 'Reimprimir ticket' : 'Sin impresora configurada'}</>
                }
              </button>

              {(selected.status === 'PAID' || selected.status === 'REFUNDED_PARTIAL') && (
                <button
                  onClick={() => { setSel(null); setReturnSale(selected) }}
                  className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl text-xs font-bold transition-colors"
                  style={{ background: 'rgba(239,68,68,0.12)', color: '#f87171' }}
                >
                  <i className="fa-solid fa-undo" /> Registrar devolución
                </button>
              )}
            </div>
          </div>
        </div>
      )}
      {returnSale && (
        <ReturnModal
          initialSale={returnSale}
          onClose={() => setReturnSale(null)}
          onSuccess={() => { setReturnSale(null); load(startDate, endDate, page) }}
        />
      )}
      {ventaPorAutorizar && (
        <ReprintPinModal
          etiqueta={saleLabel(ventaPorAutorizar)}
          onCancel={() => setVentaPorAutorizar(null)}
          onSubmit={(pin) => reprintTicket(ventaPorAutorizar, pin)}
        />
      )}
    </div>
  )
}
