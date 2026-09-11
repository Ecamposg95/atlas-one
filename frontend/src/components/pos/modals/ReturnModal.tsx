import { useState, useEffect } from 'react'
import { salesApi } from '../../../api/sales'
import { returnsApi } from '../../../api/returns'
import type { SalesDocument } from '../../../types/sales'
import { saleLabel } from '../../../types/sales'
import { formatCurrency } from '../../../utils/currency'

interface ReturnLine {
  variant_id: string
  product_name: string
  max_qty: number
  quantity: number
  unit_price: number
  restock: boolean
}

interface Props {
  onClose: () => void
  onSuccess: () => void
  activeSessionId?: number | null
  initialSale?: SalesDocument        // pre-cargar desde /sales sin necesidad de buscar
}

// Mismos valores que `PaymentMethod` en app/models/sales.py (refund_method de
// app/routers/returns.py). Reusa el patrón de MixedPaymentModal.tsx.
type RefundMethod = 'CASH' | 'CARD' | 'TRANSFER' | 'OTHER'

const REFUND_METHOD_LABELS: Record<RefundMethod, { label: string; icon: string }> = {
  CASH: { label: 'Efectivo', icon: 'fa-money-bill' },
  CARD: { label: 'Tarjeta', icon: 'fa-credit-card' },
  TRANSFER: { label: 'Transferencia', icon: 'fa-mobile-screen' },
  OTHER: { label: 'Otro', icon: 'fa-ellipsis' },
}

// Por defecto el reembolso va por el mismo método con el que pagó el
// cliente. Si el ticket tuvo pago mixto (varios métodos distintos), no hay
// un "original" único — se cae a Efectivo, que el cajero puede cambiar.
function defaultRefundMethod(sale: SalesDocument): RefundMethod {
  const methods = new Set(sale.payments.map((p) => p.method))
  if (methods.size === 1) {
    const [m] = methods
    if (m === 'CASH' || m === 'CARD' || m === 'TRANSFER' || m === 'OTHER') return m
  }
  return 'CASH'
}

function buildLines(sale: SalesDocument): ReturnLine[] {
  return sale.lines.map((line) => ({
    variant_id: line.variant_id,
    product_name: line.description ?? line.sku ?? 'Producto',
    max_qty: line.quantity,
    quantity: 0,
    unit_price: Number(line.unit_price),
    restock: true,
  }))
}

export function ReturnModal({ onClose, onSuccess, activeSessionId, initialSale }: Props) {
  const [folio, setFolio] = useState('')
  const [sale, setSale] = useState<SalesDocument | null>(initialSale ?? null)
  const [lines, setLines] = useState<ReturnLine[]>(initialSale ? buildLines(initialSale) : [])
  const [refundMethod, setRefundMethod] = useState<RefundMethod>(
    initialSale ? defaultRefundMethod(initialSale) : 'CASH'
  )
  const [reason, setReason] = useState('')
  const [searching, setSearching] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Picker de ventas recientes (modo default cuando no llega initialSale)
  const [recent, setRecent] = useState<SalesDocument[]>([])
  const [recentLoading, setRecentLoading] = useState(false)
  const [pickerMode, setPickerMode] = useState<'recent' | 'folio'>('recent')

  // Si llega un initialSale después del montaje, sincronizar
  useEffect(() => {
    if (initialSale) {
      setSale(initialSale)
      setLines(buildLines(initialSale))
      setRefundMethod(defaultRefundMethod(initialSale))
    }
  }, [initialSale?.id])

  // Cargar ventas recientes del día (sucursal del usuario, status PAID/REFUNDED_PARTIAL)
  useEffect(() => {
    if (initialSale || sale) return
    let cancelled = false
    setRecentLoading(true)
    const today = new Date().toLocaleDateString('en-CA')
    salesApi.list({ start_date: today, end_date: today, limit: 30 })
      .then((res) => {
        if (cancelled) return
        const filtered = (res.items ?? []).filter(
          (s) => s.status === 'PAID' || s.status === 'REFUNDED_PARTIAL'
        )
        setRecent(filtered)
      })
      .catch(() => { if (!cancelled) setRecent([]) })
      .finally(() => { if (!cancelled) setRecentLoading(false) })
    return () => { cancelled = true }
  }, [initialSale, sale])

  const pickSale = (s: SalesDocument) => {
    setSale(s)
    setLines(buildLines(s))
    setRefundMethod(defaultRefundMethod(s))
    setError(null)
  }

  const search = async () => {
    if (!folio.trim()) return
    setSearching(true)
    setError(null)
    setSale(null)
    try {
      // Folio exacto: el backend ya tolera serie/ceros a la izquierda
      // ("A-540" y "A-0540" encuentran el mismo ticket) y respeta el
      // scoping de organización/sucursal — no hace falta re-filtrar aquí.
      const res = await salesApi.list({ folio_search: folio.trim(), limit: 5 })
      const found = res.items[0]
      if (!found) { setError('Ticket no encontrado'); return }
      if (found.status === 'CANCELLED') { setError('Este ticket fue cancelado'); return }
      setSale(found)
      setLines(buildLines(found))
      setRefundMethod(defaultRefundMethod(found))
    } catch { setError('Error al buscar el ticket') } finally { setSearching(false) }
  }

  const updateLine = (i: number, patch: Partial<ReturnLine>) =>
    setLines((l) => l.map((line, idx) => idx === i ? { ...line, ...patch } : line))

  const setLineQty = (i: number, raw: string) => {
    const n = raw === '' ? 0 : parseInt(raw, 10)
    if (isNaN(n)) return
    setLines((l) =>
      l.map((line, idx) =>
        idx === i ? { ...line, quantity: Math.max(0, Math.min(line.max_qty, n)) } : line
      )
    )
  }

  const returnAll = () =>
    setLines((l) => l.map((line) => ({ ...line, quantity: line.max_qty })))

  const clearAll = () =>
    setLines((l) => l.map((line) => ({ ...line, quantity: 0 })))

  const selectedLines = lines.filter((l) => l.quantity > 0)
  const totalRefund = selectedLines.reduce((s, l) => s + l.quantity * l.unit_price, 0)

  const submit = async () => {
    if (!sale || selectedLines.length === 0 || !reason.trim()) return
    setSubmitting(true)
    try {
      await returnsApi.create({
        sale_id: sale.id,
        reason,
        total_refunded: totalRefund,
        refund_method: refundMethod,
        cash_session_id: activeSessionId ?? null,
        items: selectedLines.map((l) => ({
          variant_id: l.variant_id,
          quantity: l.quantity,
          refund_amount: l.quantity * l.unit_price,
          is_inventory_reentry: l.restock,
        })),
      })
      onSuccess()
    } catch (err: any) {
      // Surface FastAPI `detail` (e.g. "Cantidad excede lo disponible…",
      // "Ya existe una devolución pendiente…") so the cashier can act.
      const detail = err?.response?.data?.detail
      setError(typeof detail === 'string' && detail.trim() ? detail : 'Error al registrar devolución')
    } finally { setSubmitting(false) }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 backdrop-blur-sm"
      style={{ background: 'var(--dax-modal-backdrop)' }}
      onClick={onClose}
    >
      <div className="dax-card p-6 w-full max-w-lg max-h-[85vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-black text-white">Nueva Devolución</h3>
          <button onClick={onClose} className="text-slate-500 hover:text-white">
            <i className="fa-solid fa-xmark text-lg" />
          </button>
        </div>

        {/* Selector de venta — solo cuando no viene pre-cargado y aún no se eligió */}
        {!initialSale && !sale && (
          <div className="mb-4">
            <div className="flex gap-1 mb-3 text-xs font-bold">
              <button
                onClick={() => setPickerMode('recent')}
                className={`px-3 py-1.5 rounded-lg transition-colors ${
                  pickerMode === 'recent'
                    ? 'bg-indigo-600 text-white'
                    : 'bg-slate-700/50 text-slate-400 hover:text-white'
                }`}
              >
                <i className="fa-solid fa-clock-rotate-left mr-1.5" /> Recientes
              </button>
              <button
                onClick={() => setPickerMode('folio')}
                className={`px-3 py-1.5 rounded-lg transition-colors ${
                  pickerMode === 'folio'
                    ? 'bg-indigo-600 text-white'
                    : 'bg-slate-700/50 text-slate-400 hover:text-white'
                }`}
              >
                <i className="fa-solid fa-magnifying-glass mr-1.5" /> Por folio
              </button>
            </div>

            {pickerMode === 'recent' ? (
              <div>
                {recentLoading ? (
                  <div className="text-center py-6 text-slate-500 text-xs">
                    <i className="fa-solid fa-spinner fa-spin mr-2" /> Cargando ventas del día...
                  </div>
                ) : recent.length === 0 ? (
                  <div className="text-center py-6 text-slate-500 text-xs">
                    No hay ventas del día disponibles para devolver. Usa "Por folio" si necesitas un ticket viejo.
                  </div>
                ) : (
                  <div className="max-h-64 overflow-y-auto space-y-1.5">
                    {recent.map((s) => (
                      <button
                        key={s.id}
                        onClick={() => pickSale(s)}
                        className="w-full flex items-center justify-between gap-3 px-3 py-2 rounded-lg text-left transition-colors hover:bg-indigo-500/10"
                        style={{ background: 'var(--dax-elevated)', border: '1px solid var(--dax-border-dim)' }}
                      >
                        <div className="flex-1 min-w-0">
                          <div className="font-mono text-xs text-indigo-400 font-bold">
                            {saleLabel(s)}
                          </div>
                          <div className="text-[10px] text-slate-500 truncate">
                            {s.customer_name ?? 'Público general'} · {new Date(s.created_at).toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' })}
                          </div>
                        </div>
                        <span className="text-xs font-bold text-emerald-400 tabular-nums flex-shrink-0">
                          {formatCurrency(s.total_amount)}
                        </span>
                        {s.status === 'REFUNDED_PARTIAL' && (
                          <span className="text-[9px] font-bold px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-400">
                            Parcial
                          </span>
                        )}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <div className="flex gap-2">
                <input
                  type="text"
                  value={folio}
                  onChange={(e) => setFolio(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') search() }}
                  className="dax-input flex-1 font-mono text-sm uppercase"
                  placeholder="Folio del ticket (ej: DAX-00001)"
                  autoFocus
                />
                <button onClick={search} disabled={searching} className="dax-btn-secondary text-sm">
                  {searching ? <i className="fa-solid fa-spinner fa-spin" /> : <i className="fa-solid fa-search" />}
                </button>
              </div>
            )}
          </div>
        )}

        {error && <p className="text-red-400 text-sm mb-3">{error}</p>}

        {sale && (
          <>
            {/* Info del ticket */}
            <div className="rounded-xl p-3 mb-4 text-sm" style={{ background: 'var(--dax-elevated)', border: '1px solid var(--dax-border-dim)' }}>
              <div className="flex justify-between text-slate-400 mb-1">
                <span>Folio</span><span className="font-mono text-indigo-400">{saleLabel(sale)}</span>
              </div>
              <div className="flex justify-between text-slate-400">
                <span>Total original</span><span className="text-emerald-400 font-semibold">{formatCurrency(sale.total_amount)}</span>
              </div>
            </div>

            {/* Método de reembolso — por defecto el mismo con el que pagó el cliente */}
            <div className="mb-4">
              <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1">
                Método de reembolso
              </label>
              <select
                value={refundMethod}
                onChange={(e) => setRefundMethod(e.target.value as RefundMethod)}
                className="dax-input text-sm w-full"
              >
                {(Object.keys(REFUND_METHOD_LABELS) as RefundMethod[]).map((m) => (
                  <option key={m} value={m}>{REFUND_METHOD_LABELS[m].label}</option>
                ))}
              </select>
            </div>

            {/* Items */}
            <div className="flex items-center justify-between mb-2">
              <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Artículos a devolver</p>
              <div className="flex gap-1.5">
                <button
                  onClick={returnAll}
                  type="button"
                  className="text-[10px] font-bold px-2 py-1 rounded-md bg-amber-500/15 text-amber-400 hover:bg-amber-500/25 transition-colors"
                  title="Devolver todas las piezas del ticket"
                >
                  <i className="fa-solid fa-check-double mr-1" /> Devolver todo
                </button>
                <button
                  onClick={clearAll}
                  type="button"
                  className="text-[10px] font-semibold px-2 py-1 rounded-md bg-slate-600/30 text-slate-300 hover:bg-slate-600/50 transition-colors"
                >
                  Limpiar
                </button>
              </div>
            </div>
            <div className="space-y-2 mb-4">
              {lines.map((line, i) => (
                <div key={i} className="rounded-lg p-3" style={{ background: 'var(--dax-elevated)' }}>
                  <div className="flex items-center justify-between gap-2 mb-2">
                    <span className="text-sm text-white flex-1">{line.product_name}</span>
                    <button
                      onClick={() => updateLine(i, { quantity: line.max_qty })}
                      type="button"
                      className="text-[10px] font-bold px-1.5 py-0.5 rounded text-amber-400 hover:bg-amber-500/15 transition-colors"
                      title="Devolver todas las piezas de este renglón"
                    >
                      Todas ({line.max_qty})
                    </button>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => updateLine(i, { quantity: Math.max(0, line.quantity - 1) })}
                        className="w-8 h-8 rounded-lg bg-slate-700 hover:bg-slate-600 text-white text-sm flex items-center justify-center"
                      >−</button>
                      <input
                        type="number"
                        min={0}
                        max={line.max_qty}
                        value={line.quantity}
                        onChange={(e) => setLineQty(i, e.target.value)}
                        onFocus={(e) => e.currentTarget.select()}
                        className="w-14 h-8 text-center font-bold text-white text-sm rounded-lg bg-slate-800 border border-slate-700 focus:border-indigo-500 focus:outline-none tabular-nums"
                      />
                      <button
                        onClick={() => updateLine(i, { quantity: Math.min(line.max_qty, line.quantity + 1) })}
                        className="w-8 h-8 rounded-lg bg-slate-700 hover:bg-slate-600 text-white text-sm flex items-center justify-center"
                      >+</button>
                    </div>
                    <button
                      onClick={() => updateLine(i, { restock: !line.restock })}
                      className={`text-xs font-semibold px-2 py-1 rounded-lg border transition-colors ${
                        line.restock
                          ? 'border-emerald-600/50 bg-emerald-600/10 text-emerald-400'
                          : 'border-red-600/50 bg-red-600/10 text-red-400'
                      }`}
                    >
                      {line.restock ? 'Regresa stock' : 'Merma'}
                    </button>
                    {line.quantity > 0 && (
                      <span className="ml-auto text-xs text-slate-400">
                        {formatCurrency(line.quantity * line.unit_price)}
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>

            {/* Motivo */}
            <div className="mb-4">
              <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1">
                Motivo <span className="text-red-400">*</span>
              </label>
              <input
                type="text"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                className="dax-input"
                placeholder="Ej: Producto defectuoso, cambio de talla..."
              />
            </div>

            {selectedLines.length > 0 && (
              <div className="flex justify-between text-sm font-bold pt-3 mb-4" style={{ color: 'var(--dax-text)', borderTop: '1px solid var(--dax-border-dim)' }}>
                <span>Total a reembolsar</span>
                <span className="text-red-400">{formatCurrency(totalRefund)}</span>
              </div>
            )}

            <div className="flex gap-2">
              <button onClick={onClose} className="dax-btn-secondary flex-1">Cancelar</button>
              <button
                onClick={submit}
                disabled={submitting || selectedLines.length === 0 || !reason.trim()}
                className="dax-btn-danger flex-1 justify-center disabled:opacity-50"
              >
                {submitting ? <i className="fa-solid fa-spinner fa-spin" /> : <><i className="fa-solid fa-undo" /> Registrar</>}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
