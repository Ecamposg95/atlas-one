import { useState, useEffect } from 'react'
import { salesApi } from '../../../api/sales'
import { returnsApi, returnLabel, MOTIVOS_DEVOLUCION } from '../../../api/returns'
import type { PiezasDelTicket } from '../../../api/returns'
import { printerApi } from '../../../api/printer'
import { usePOSStore } from '../../../store/posStore'
import { useEnabledModulesStore } from '../../../store/enabledModulesStore'
import { pinBloqueado } from '../../../utils/reimpresion'
import type { SalesDocument } from '../../../types/sales'
import { saleLabel } from '../../../types/sales'
import { formatCurrency } from '../../../utils/currency'
import { useEsTelefono } from '../../../hooks/useIsMobile'
import { esRolCaja } from '../../../utils/rolesCaja'
import { useAuthStore } from '../../../store/authStore'
import { errorDetailText } from '../../../utils/errorDetail'

interface ReturnLine {
  variant_id: string
  product_name: string
  max_qty: number
  /** Piezas de este producto ya devueltas (o en una solicitud pendiente). */
  ya_devuelto?: number
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

/** Resultado de registrar: lo mínimo para autorizar con PIN e imprimir. */
interface Registrada { id: string; status: string; total: number }

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
  const esTelefono = useEsTelefono()
  const esCajera = esRolCaja(useAuthStore((s) => s.user?.role))
  const [sale, setSale] = useState<SalesDocument | null>(initialSale ?? null)
  const [lines, setLines] = useState<ReturnLine[]>(initialSale ? buildLines(initialSale) : [])
  const [refundMethod, setRefundMethod] = useState<RefundMethod>(
    initialSale ? defaultRefundMethod(initialSale) : 'CASH'
  )
  const [reason, setReason] = useState('')
  // Motivo de catálogo (obligatorio); `reason` queda como nota opcional.
  const [motivo, setMotivo] = useState('')
  // Qué queda por devolver del ticket y con qué reglas (servidor).
  const [info, setInfo] = useState<PiezasDelTicket | null>(null)
  // Ya registrada: pendiente (pide PIN del gerente) o aprobada (comprobante).
  const [hecha, setHecha] = useState<Registrada | null>(null)
  const [pin, setPin] = useState('')
  const [autorizando, setAutorizando] = useState(false)
  const [imprimiendo, setImprimiendo] = useState(false)
  const printerName = usePOSStore((st) => st.printerName)
  const diasCaja = useEnabledModulesStore((st) => st.diasVentasCaja)
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

  // Con el ticket elegido se pregunta al servidor qué queda por devolver: las
  // piezas ya devueltas no se ofrecen y el importe es lo que se pagó por pieza.
  useEffect(() => {
    if (!sale) { setInfo(null); return }
    let vivo = true
    returnsApi.piezas(sale.id)
      .then((d) => {
        if (!vivo) return
        setInfo(d)
        setLines(d.piezas.map((pz) => ({
          variant_id: pz.variant_id,
          product_name: pz.descripcion ?? pz.sku ?? 'Producto',
          max_qty: Number(pz.disponible),
          ya_devuelto: Number(pz.devuelto) + Number(pz.en_tramite),
          quantity: 0,
          unit_price: Number(pz.precio_pagado),
          restock: true,
        })))
        // La caja reembolsa por donde se pagó el ticket.
        if (d.es_caja && d.metodos.length > 0) {
          setRefundMethod((m) => (d.metodos.includes(m) ? m : d.metodos[0] as RefundMethod))
        }
      })
      .catch((err: any) => {
        if (!vivo) return
        const estado = err?.response?.status
        // Fuera de plazo o de otra sucursal: no hay nada que devolver aquí.
        if (estado === 403 || estado === 404) {
          setError(errorDetailText(err?.response?.data?.detail, 'Este ticket no se puede devolver desde aquí.'))
          if (!initialSale) setSale(null)
          setLines([])
        }
        // Cualquier otro fallo: se sigue con las líneas del ticket; el servidor valida al registrar.
      })
    return () => { vivo = false }
  }, [sale?.id])

  const motivos = info?.motivos?.length ? info.motivos : MOTIVOS_DEVOLUCION
  const elegirMotivo = (code: string) => {
    setMotivo(code)
    const m = motivos.find((x) => x.code === code)
    // Un defecto por omisión va a merma; lo demás regresa a stock. Se puede cambiar por pieza.
    if (m) setLines((l) => l.map((line) => ({ ...line, restock: m.regresa_a_stock })))
  }
  const metodosVisibles: string[] = info?.es_caja && info.metodos.length > 0
    ? info.metodos
    : Object.keys(REFUND_METHOD_LABELS)
  const montoLibre = info?.es_caja ? Number(info.monto_libre ?? 0) : null

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
      if (!found) {
        // La cajera solo ve su plazo: un folio más viejo llega vacío, no "inexistente".
        setError(esCajera
          ? (diasCaja > 0
            ? `Ticket no encontrado. Solo aparecen ventas de tu sucursal de los últimos ${diasCaja} días; para más antiguas pide al gerente.`
            : 'Ticket no encontrado. Solo aparecen ventas de hoy; para días anteriores pide al gerente.')
          : 'Ticket no encontrado')
        return
      }
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
    if (!sale || selectedLines.length === 0 || !motivo) return
    setSubmitting(true)
    setError(null)
    try {
      const creada = await returnsApi.create({
        sale_id: sale.id,
        reason: reason.trim(),
        reason_code: motivo,
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
      // La caja se queda en el modal: aprobada → comprobante; pendiente → PIN del
      // gerente aquí mismo. Los demás roles la aprueban desde Devoluciones, como siempre.
      if (esCajera && creada?.id) {
        setHecha({ id: creada.id, status: creada.status, total: Number(creada.total_refunded) })
      } else {
        onSuccess()
      }
    } catch (err: any) {
      // Surface FastAPI `detail` (e.g. "Cantidad excede lo disponible…",
      // "Ya existe una devolución pendiente…") so the cashier can act.
      const detail = err?.response?.data?.detail
      setError(errorDetailText(detail, 'Error al registrar devolución'))
    } finally { setSubmitting(false) }
  }

  const autorizar = async () => {
    if (!hecha || !pin.trim() || autorizando) return
    setAutorizando(true)
    setError(null)
    try {
      const r = await returnsApi.autorizar(hecha.id, pin)
      setHecha({ id: r.id, status: r.status, total: Number(r.total_refunded) })
    } catch (err: any) {
      setError(pinBloqueado(err)
        ? errorDetailText(err?.response?.data?.detail, 'Demasiados intentos. Espera unos minutos.')
        : errorDetailText(err?.response?.data?.detail?.message ?? err?.response?.data?.detail, 'No se pudo autorizar la devolución.'))
    } finally {
      setPin('')
      setAutorizando(false)
    }
  }

  const imprimir = async () => {
    if (!hecha || !printerName || imprimiendo) return
    setImprimiendo(true)
    setError(null)
    try {
      const b64 = await printerApi.getDevolucionBase64(hecha.id)
      if (b64) await printerApi.printViaAgent(printerName, b64)
    } catch (err: any) {
      setError(errorDetailText(err?.response?.data?.detail, 'No se pudo imprimir el comprobante.'))
    } finally { setImprimiendo(false) }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 backdrop-blur-sm"
      style={{ background: 'var(--dax-modal-backdrop)' }}
      onClick={onClose}
    >
      <div className="dax-card dax-modal p-6 w-full max-w-lg max-h-[85vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-black text-white">Nueva Devolución</h3>
          <button onClick={onClose} className="dax-btn-icon text-slate-500 hover:text-white" aria-label="Cerrar">
            <i className="fa-solid fa-xmark text-lg" />
          </button>
        </div>

        {hecha && (
          <div data-testid="devolucion-hecha">
            <div className="rounded-xl p-4 mb-4 text-sm" style={{ background: 'var(--dax-elevated)', border: '1px solid var(--dax-border-dim)' }}>
              <div className="flex justify-between mb-1" style={{ color: 'var(--dax-text-muted)' }}>
                <span>Devolución</span><span className="font-mono">{returnLabel({ id: hecha.id, sale_id: '' })}</span>
              </div>
              <div className="flex justify-between font-bold" style={{ color: 'var(--dax-text)' }}>
                <span>{hecha.status === 'APPROVED' ? 'Devuelto' : 'Por devolver'}</span>
                <span>{formatCurrency(hecha.total)}</span>
              </div>
            </div>
            {hecha.status === 'APPROVED' ? (
              <p className="text-sm mb-4" style={{ color: 'var(--dax-success)' }}>
                <i className="fa-solid fa-circle-check mr-1.5" aria-hidden="true" />
                Devolución aprobada. Entrega el reembolso al cliente.
              </p>
            ) : (
              <div className="mb-4">
                <p className="text-sm mb-3" style={{ color: 'var(--dax-text)' }}>
                  Falta la autorización de un gerente. Puede teclear su PIN aquí, o aprobarla después desde Devoluciones.
                </p>
                <label htmlFor="devolucion-pin" className="block text-[10px] font-bold uppercase tracking-wider mb-1" style={{ color: 'var(--dax-text-muted)' }}>
                  PIN del gerente
                </label>
                <div className="flex gap-2">
                  <input
                    id="devolucion-pin" type="password" inputMode="numeric" autoComplete="off" autoFocus
                    value={pin}
                    onChange={(e) => setPin(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') autorizar() }}
                    className="dax-input flex-1"
                  />
                  <button type="button" onClick={autorizar} disabled={autorizando || !pin.trim()} className="dax-btn-primary disabled:opacity-50">
                    {autorizando ? <i className="fa-solid fa-spinner fa-spin" /> : 'Autorizar'}
                  </button>
                </div>
              </div>
            )}
            {error && <p className="text-red-400 text-sm mb-3" role="alert">{error}</p>}
            <div className={`flex gap-2 ${esTelefono ? 'dax-modal-footer -mx-6 px-6' : ''}`}>
              <button
                type="button" onClick={imprimir} disabled={imprimiendo || !printerName}
                className="dax-btn-secondary flex-1 justify-center disabled:opacity-40"
                title={printerName ? 'Imprimir comprobante' : 'Configura una impresora'}
              >
                {imprimiendo ? <i className="fa-solid fa-spinner fa-spin" /> : <><i className="fa-solid fa-print" /> Comprobante</>}
              </button>
              <button type="button" onClick={onSuccess} className="dax-btn-primary flex-1 justify-center">
                {hecha.status === 'APPROVED' ? 'Listo' : 'Dejar pendiente'}
              </button>
            </div>
          </div>
        )}

        {/* Selector de venta — solo cuando no viene pre-cargado y aún no se eligió */}
        {!hecha && !initialSale && !sale && (
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

        {!hecha && error && <p className="text-red-400 text-sm mb-3">{error}</p>}

        {!hecha && sale && info?.pendiente && (
          <div className="rounded-xl p-3 mb-4 text-sm" style={{ background: 'var(--dax-elevated)', border: '1px solid var(--dax-border-dim)', color: 'var(--dax-text)' }}>
            <p className="mb-2">
              Este ticket ya tiene una devolución pendiente por {formatCurrency(Number(info.pendiente.total))}.
              Hay que autorizarla o rechazarla antes de registrar otra.
            </p>
            <button
              type="button"
              onClick={() => setHecha({ id: info.pendiente!.id, status: 'PENDING', total: Number(info.pendiente!.total) })}
              className="dax-btn-secondary text-xs"
            >
              <i className="fa-solid fa-key" /> Autorizar con PIN del gerente
            </button>
          </div>
        )}

        {!hecha && sale && !info?.pendiente && (
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
                {metodosVisibles.map((m) => (
                  <option key={m} value={m}>{REFUND_METHOD_LABELS[m as RefundMethod]?.label ?? m}</option>
                ))}
              </select>
              {info?.es_caja && (
                <p className="text-[10px] mt-1" style={{ color: 'var(--dax-text-muted)' }}>
                  El reembolso va por donde se pagó el ticket.
                </p>
              )}
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
                    <span className="text-sm text-white flex-1">
                      {line.product_name}
                      {!!line.ya_devuelto && (
                        <span className="block text-[10px] text-amber-400">
                          {line.max_qty > 0 ? `Ya se devolvieron ${line.ya_devuelto}; quedan ${line.max_qty}` : 'Ya se devolvió completo'}
                        </span>
                      )}
                    </span>
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
              <select
                aria-label="Motivo"
                value={motivo}
                onChange={(e) => elegirMotivo(e.target.value)}
                className="dax-input text-sm w-full mb-2"
              >
                <option value="">Elige el motivo…</option>
                {motivos.map((m) => <option key={m.code} value={m.code}>{m.label}</option>)}
              </select>
              <input
                type="text"
                aria-label="Nota del motivo"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                className="dax-input"
                placeholder="Nota (opcional): cierre roto, pidió talla M..."
              />
            </div>

            {selectedLines.length > 0 && (
              <div className="flex justify-between text-sm font-bold pt-3 mb-4" style={{ color: 'var(--dax-text)', borderTop: '1px solid var(--dax-border-dim)' }}>
                <span>Total a reembolsar</span>
                <span className="text-red-400">{formatCurrency(totalRefund)}</span>
              </div>
            )}
            {selectedLines.length > 0 && montoLibre !== null && (
              <p className="text-[11px] -mt-2 mb-4" style={{ color: 'var(--dax-text-muted)' }}>
                {montoLibre > 0 && totalRefund <= montoLibre
                  ? 'Dentro de tu monto: se aprueba al registrar.'
                  : 'Va a pedir el PIN de un gerente.'}
              </p>
            )}

            {/* Este modal es compartido con el POS de la cajera, que no debe cambiar en
                escritorio: por eso `dax-modal-footer` (cuyo relleno movería el pie de hoy)
                solo se aplica en teléfono, donde Cancelar/Registrar quedan pegados al pie
                y visibles con el teclado abierto. Bajo 640 px el modal, también en el POS,
                pasa a hoja inferior por `dax-modal`: mejora aceptada. */}
            <div className={`flex gap-2 ${esTelefono ? 'dax-modal-footer -mx-6 px-6' : ''}`}>
              <button onClick={onClose} className="dax-btn-secondary flex-1">Cancelar</button>
              <button
                onClick={submit}
                disabled={submitting || selectedLines.length === 0 || !motivo}
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
