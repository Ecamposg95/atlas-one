import { useEffect, useState, useCallback, useRef } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { cashApi } from '../../api/cash'
import { salesApi, parkedTicketsApi } from '../../api/sales'
import type { CartItem } from '../../types/sales'
import { saleLabel } from '../../types/sales'
import { printerApi } from '../../api/printer'
import { usePOSStore } from '../../store/posStore'
import { useAuthStore } from '../../store/authStore'
import type { CashSession } from '../../types/cash'

import { ProductSearch } from '../../components/pos/ProductSearch'
import { CartPanel } from '../../components/pos/CartPanel'
import { PendingOrders } from '../../components/pos/PendingOrders'
import { SessionModal } from '../../components/pos/modals/SessionModal'
import { CashPaymentModal } from '../../components/pos/modals/CashPaymentModal'
import { CardPaymentModal } from '../../components/pos/modals/CardPaymentModal'
import { TransferPaymentModal } from '../../components/pos/modals/TransferPaymentModal'
import { MixedPaymentModal } from '../../components/pos/modals/MixedPaymentModal'
import { ReturnModal } from '../../components/pos/modals/ReturnModal'
import { CashMovementModal } from '../../components/pos/modals/CashMovementModal'
import { CloseSessionModal } from '../../components/pos/modals/CloseSessionModal'
import { ProductDetailModal } from '../../components/pos/modals/ProductDetailModal'
import { formatCurrency } from '../../utils/currency'
import { errorDetailText } from '../../utils/errorDetail'
import {
  enqueueSale,
  listPending,
  flushPending,
  isNetworkError,
  type PendingSale,
} from '../../utils/offlineQueue'

type PayMethod = 'CASH' | 'CARD' | 'TRANSFER' | 'MIXED'
type LeftTab = 'products' | 'pending'
type Toast = { msg: string; type: 'success' | 'error' }

export function POS() {
  const { user } = useAuthStore()
  const store = usePOSStore()
  const total = usePOSStore((s) => s.total())
  const pendingCount = usePOSStore((s) => s.parkedTickets.length)
  const savedPrinterName = usePOSStore((s) => s.printerName)

  const [checkingSession, setCheckingSession] = useState(true)
  const [showSessionModal, setShowSessionModal] = useState(false)
  const [payModal, setPayModal] = useState<PayMethod | null>(null)
  const [returnModal, setReturnModal] = useState(false)
  const [leftTab, setLeftTab] = useState<LeftTab>('products')
  const [toast, setToast] = useState<Toast | null>(null)
  const [cashMovement, setCashMovement] = useState<'IN' | 'OUT' | null>(null)
  const [closingSession, setClosingSession] = useState(false)
  const [lastSaleId, setLastSaleId] = useState<string | null>(null)
  const [createProductOpen, setCreateProductOpen] = useState(false)
  const [productRefreshKey, setProductRefreshKey] = useState(0)
  const [offlineQueue, setOfflineQueue] = useState<PendingSale[]>([])
  const [showOfflineModal, setShowOfflineModal] = useState(false)
  const barraRef = useRef<HTMLDivElement>(null)

  const canEditProducts = !!user?.role && ['ADMINISTRADOR', 'DUEÑO', 'GERENTE', 'CAJERO'].includes(user.role)
  const { branch } = useAuthStore()
  const isBranch = !!branch && branch.branch_type !== 'HQ'

  const showToast = (msg: string, type: Toast['type'] = 'success') => {
    setToast({ msg, type })
    setTimeout(() => setToast(null), 3500)
  }

  // ----- Session check -----
  const checkSession = useCallback(async () => {
    setCheckingSession(true)
    try {
      const s = await cashApi.getStatus()
      store.setSession(s && s.status === 'OPEN' ? s : null)
    } catch {
      store.setSession(null)
    } finally {
      setCheckingSession(false)
    }
  }, [])

  useEffect(() => { checkSession() }, [checkSession])

  // Durante el cobro la barra superior queda inerte: un clic o un Tab a las
  // pestañas cambiaba de panel con el modal abierto y dejaba el ticket a medio
  // cobrar. `inert` la saca del orden de tabulación y del árbol de
  // accesibilidad, cosa que `pointer-events-none` no hace. Se aplica sobre el
  // nodo porque react-dom 18 descarta el atributo si se pasa como prop de JSX
  // (mismo motivo documentado en Layout.tsx para el cajón móvil).
  useEffect(() => {
    const el = barraRef.current
    if (!el) return
    if (payModal !== null) {
      el.setAttribute('inert', '')
    } else {
      el.removeAttribute('inert')
    }
  }, [payModal])

  // ----- Parked tickets polling — siempre activo sin importar el tab -----
  // Track 2 (POS bug-fix): pausados están en `parked_tickets`, NO crean
  // SalesDocument PENDING — pausar no descuenta stock ni consume folio.
  useEffect(() => {
    const fetchParked = async () => {
      try {
        const list = await parkedTicketsApi.list()
        store.setParkedTickets(list)
      } catch {}
    }
    fetchParked()
    const id = setInterval(fetchParked, 10_000)
    return () => clearInterval(id)
  }, [])

  // Convierte ítems del carrito a líneas de venta normalizadas.
  // Los ítems de caja (cart_key includes '::caja::') se expanden a piezas:
  //   quantity  → cajas × min_quantity (piezas reales para stock)
  //   unit_price → tier.unit_price     (precio por pieza)
  //   subtotal  → quantity × unit_price (conserva el valor monetario)
  // Si hay descuento global, se aplica al unit_price de cada línea antes de enviar
  // (distribuye proporcionalmente; el guard de descuento server-side de sales.py
  // evalúa sobre el precio final, por lo que descuentos combinados > 50% se rechazan).
  const buildSaleItems = () => {
    const gd = store.globalDiscount || 0
    const gdFactor = 1 - gd / 100
    return store.cart.map((c) => {
      if (c.cart_key?.includes('::caja::')) {
        const tierId = c.cart_key.split('::caja::')[1]
        const cajaTier = c.prices?.find((p) => p.id === tierId)
        if (cajaTier && cajaTier.min_quantity > 0) {
          const totalPiezas = c.quantity * cajaTier.min_quantity
          const unitPrice = cajaTier.unit_price * gdFactor
          return {
            product_id: c.product_id,
            sku: c.sku,
            name: c.name,
            unit_price: unitPrice,
            price: unitPrice,
            quantity: totalPiezas,
            discount: c.discount,
            subtotal: totalPiezas * unitPrice * (1 - c.discount / 100),
          }
        }
      }
      const unitPrice = c.price * gdFactor
      return {
        product_id: c.product_id,
        sku: c.sku,
        name: c.name,
        unit_price: unitPrice,
        price: unitPrice,
        quantity: c.quantity,
        discount: c.discount,
        subtotal: c.quantity * unitPrice * (1 - c.discount / 100),
      }
    })
  }

  /** Imprimir ticket nuevo vía agente local (fire-and-forget, no bloquea el POS) */
  const printViaAgent = (saleId: string) => {
    if (!savedPrinterName) return
    printerApi.getNewTicketBase64(saleId)
      .then(b64 => { if (b64) return printerApi.printViaAgent(savedPrinterName, b64) })
      .catch(() => {
        // La venta ya quedó registrada — solo avisamos al cajero para reimprimir manual.
        showToast('Ticket guardado pero no se pudo imprimir — verifica que el agente esté corriendo', 'error')
      })
  }

  /** Reimprimir último ticket (incluye leyenda COPIA) */
  const reprintViaAgent = (saleId: string) => {
    if (!savedPrinterName) return
    printerApi.getTicketBase64(saleId)
      .then(b64 => { if (b64) return printerApi.printViaAgent(savedPrinterName, b64) })
      .catch(() => {
        showToast('Ticket guardado pero no se pudo imprimir — verifica que el agente esté corriendo', 'error')
      })
  }

  // ----- Sale submission -----
  const submitSale = async (
    payments: { method: string; amount: number; reference?: string }[],
    opts: { print?: boolean } = {}
  ) => {
    const shouldPrint = opts.print ?? true
    if (store.isProcessing || store.cart.length === 0) return
    store.setIsProcessing(true)
    // Idempotencia: un identificador por INTENTO de cobro. La cola offline
    // reenvia este mismo payload, asi que un reintento llega con el mismo
    // valor y el backend devuelve la venta original en vez de duplicarla.
    const clientUuid =
      typeof crypto !== 'undefined' && 'randomUUID' in crypto
        ? crypto.randomUUID()
        : `${Date.now()}-${Math.random().toString(36).slice(2)}`
    const payload = {
      client_uuid: clientUuid,
      customer_id: store.customerId ?? undefined,
      items: buildSaleItems(),
      payments,
      doc_type: 'SALE',
      requires_invoice: store.requiresInvoice,
      // Wave-1: backend audita el descuento global y marca el parked CONVERTED.
      global_discount_pct: store.globalDiscount || 0,
      tip_amount: store.tip || 0,
      parked_ticket_id: store.currentParkedId ?? undefined,
    }
    try {
      const sale = await salesApi.create(payload)
      store.clearCart()
      const parkedId = store.currentParkedId
      if (parkedId) {
        parkedTicketsApi.remove(parkedId).catch(() => {})
        store.setCurrentParkedId(null)
        // Refrescar lista de pausados
        parkedTicketsApi.list().then((l) => store.setParkedTickets(l)).catch(() => {})
      }
      setPayModal(null)
      const saleId = sale.sale_id ?? null
      setLastSaleId(saleId)
      const folio = sale.folio ?? '—'
      const change = sale.change ?? 0
      const changeStr = change > 0 ? ` · Cambio: ${formatCurrency(change)}` : ''
      showToast(`Venta ${folio} registrada${changeStr}`)
      // Auto-imprimir vía agente local si hay impresora configurada,
      // salvo que el cajero haya apagado "Imprimir Ticket" en el modal.
      if (saleId && shouldPrint) printViaAgent(saleId)
    } catch (err: unknown) {
      // Red caída: encolar en IndexedDB y liberar el carrito para seguir operando.
      if (isNetworkError(err)) {
        try {
          await enqueueSale(payload)
          store.clearCart()
          setPayModal(null)
          const updated = await listPending()
          setOfflineQueue(updated)
          showToast('Venta guardada — se enviará al reconectar')
        } catch (e) {
          console.error('[POS] enqueueSale failed:', e)
          showToast('No se pudo guardar la venta offline', 'error')
        }
      } else {
        // El motivo del rechazo es lo único que la cajera puede accionar con el
        // dinero ya en la mano, así que se muestra tal cual. `detail` llega como
        // texto en los HTTPException de create_sale y como arreglo en los 422 de
        // validación de Pydantic: pintarlo crudo daba "[object Object]".
        const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
        showToast(errorDetailText(detail, 'Error al procesar la venta'), 'error')
      }
    } finally {
      store.setIsProcessing(false)
    }
  }

  // ----- Offline queue: flush + polling + online listener -----
  const refreshOfflineQueue = useCallback(async () => {
    try {
      setOfflineQueue(await listPending())
    } catch {}
  }, [])

  const runFlush = useCallback(async () => {
    try {
      const result = await flushPending((payload) => salesApi.create(payload as Parameters<typeof salesApi.create>[0]))
      if (result.sent > 0) {
        showToast(`${result.sent} venta(s) offline enviada(s)`)
      }
      await refreshOfflineQueue()
    } catch (e) {
      console.warn('[POS] flushPending error:', e)
    }
  }, [refreshOfflineQueue])

  useEffect(() => {
    // Initial flush + queue snapshot on mount
    refreshOfflineQueue()
    runFlush()
    const id = setInterval(runFlush, 30_000)
    const onOnline = () => runFlush()
    window.addEventListener('online', onOnline)
    return () => {
      clearInterval(id)
      window.removeEventListener('online', onOnline)
    }
  }, [runFlush, refreshOfflineQueue])

  // ----- Park (Pausar) -----
  // Snapshot del carrito a tabla `parked_tickets`. NO crea SalesDocument,
  // NO descuenta stock, NO consume folio. Hand-off entre PCs vía
  // `parkedTicketsApi.list/resume`.
  const parkSale = useCallback(async () => {
    if (store.isProcessing || store.cart.length === 0) return
    store.setIsProcessing(true)
    try {
      // Si veníamos editando un pausado existente, eliminamos el viejo y
      // creamos uno nuevo con el cart actual (más simple que un PATCH).
      const existingId = store.currentParkedId
      const cartJson: Record<string, unknown> = {
        items: store.cart,
        requires_invoice: store.requiresInvoice,
        global_discount: store.globalDiscount,
      }
      await parkedTicketsApi.park(cartJson, store.customerId, undefined)
      if (existingId) {
        parkedTicketsApi.remove(existingId).catch(() => {})
      }
      store.clearCart()
      showToast('Ticket pausado')
      // Refrescar lista inmediatamente
      parkedTicketsApi.list().then((l) => store.setParkedTickets(l)).catch(() => {})
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      showToast(detail ?? 'Error al pausar el ticket', 'error')
    } finally {
      store.setIsProcessing(false)
    }
  }, [store])

  // ----- Reprint last ticket -----
  const handleReprint = () => {
    if (!lastSaleId) return
    if (savedPrinterName) {
      reprintViaAgent(lastSaleId)
    } else {
      printerApi.reprintTicket(lastSaleId).catch(() => {})
    }
    showToast('Imprimiendo último ticket...')
  }

  // ----- Payment handlers -----
  const handleCashPay = async (received: number, printTicket: boolean) => {
    await submitSale([{ method: 'CASH', amount: received }], { print: printTicket })
  }

  const handleCardPay = async (reference: string) => {
    await submitSale([{ method: 'CARD', amount: total, reference }])
  }

  const handleTransferPay = async (reference: string) => {
    await submitSale([{ method: 'TRANSFER', amount: total, reference }])
  }

  const handleMixedPay = async (payments: { method: string; amount: number; reference?: string }[]) => {
    await submitSale(payments)
  }

  // ----- Load parked ticket into cart -----
  // El cart_json contiene `items` (lista completa de CartItems con
  // prices/packaging_units/cart_key/unit_kind), `requires_invoice` y
  // `global_discount`. Rehidratar tal cual para preservar caja-pricing,
  // tiers, descuentos y override manual de precio.
  const loadOrder = useCallback(async (parkedId: string) => {
    try {
      const parked = await parkedTicketsApi.resume(parkedId)
      const cartJson = (parked.cart_json ?? {}) as {
        items?: CartItem[]
        requires_invoice?: boolean
        global_discount?: number
      }
      const items = Array.isArray(cartJson.items) ? cartJson.items : []
      store.clearCart()
      for (const it of items) store.addItem(it)
      if (typeof cartJson.requires_invoice === 'boolean') {
        store.setRequiresInvoice(cartJson.requires_invoice)
      }
      if (typeof cartJson.global_discount === 'number') {
        store.setGlobalDiscount(cartJson.global_discount)
      }
      if (parked.customer_id) {
        // Nombre del cliente no viene en parked; el carrito lo recupera
        // si el usuario re-selecciona, pero el id se preserva.
        store.setCustomer(parked.customer_id, null)
      }
      store.setCurrentParkedId(parkedId)
      setLeftTab('products')
      showToast('Ticket reanudado')
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      showToast(detail ?? 'Error al reanudar el ticket', 'error')
    }
  }, [store])

  // Mesa → cobro: el plano de mesas navega a /pos?parked=<ticket> y aquí se
  // carga la cuenta directo al carrito (una sola vez; luego se limpia la URL).
  const [searchParams, setSearchParams] = useSearchParams()
  const parkedParamHandled = useRef(false)
  useEffect(() => {
    const pid = searchParams.get('parked')
    if (!pid || parkedParamHandled.current) return
    parkedParamHandled.current = true
    loadOrder(pid)
    const next = new URLSearchParams(searchParams)
    next.delete('parked')
    setSearchParams(next, { replace: true })
  }, [searchParams, setSearchParams, loadOrder])

  // ----- No session / loading -----
  if (checkingSession) {
    return (
      <div className="flex items-center justify-center h-full min-h-[60vh]">
        <div className="text-center">
          <i className="fa-solid fa-spinner fa-spin text-purple-400 text-3xl mb-3 block" />
          <p className="text-slate-400 text-sm">Verificando turno...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full relative">
      {/* Toast */}
      {toast && (
        <div className={`fixed top-4 right-4 z-50 px-4 py-2.5 rounded-xl shadow-xl text-sm font-semibold flex items-center gap-2 transition-all ${
          toast.type === 'success' ? 'bg-emerald-600 text-white' : 'bg-red-600 text-white'
        }`}>
          <i className={`fa-solid ${toast.type === 'success' ? 'fa-check' : 'fa-xmark'}`} />
          {toast.msg}
        </div>
      )}

      {/* Consolidated header — single bar. Inerte durante el cobro (ver efecto). */}
      <div
        ref={barraRef}
        className={`flex items-center gap-2 flex-wrap px-4 py-2 flex-shrink-0 transition-opacity ${
          payModal !== null ? 'opacity-50' : ''
        }`}
        style={{ background: 'var(--dax-surface)', borderBottom: '1px solid var(--dax-border-dim)' }}
      >
        {/* ← Mi día — solo en sucursal */}
        {isBranch && (
          <>
            <Link
              to="/atlas-pos"
              className="flex items-center gap-1.5 text-xs font-semibold transition-colors"
              style={{ color: 'var(--dax-text-muted)' }}
            >
              <i className="fa-solid fa-chevron-left text-[10px]" />
              Mi día
            </Link>
            <div className="w-px h-4 flex-shrink-0" style={{ background: 'var(--dax-border-dim)' }} />
          </>
        )}

        {/* Tabs: Productos / Pendientes — moved up from left panel */}
        <button
          onClick={() => setLeftTab('products')}
          className={`flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg transition-colors border ${
            leftTab === 'products'
              ? 'border-purple-500/60 text-white bg-purple-500/15'
              : 'border-transparent text-slate-500 hover:text-white hover:bg-white/5'
          }`}
        >
          <i className="fa-solid fa-barcode text-[10px]" /> Productos
        </button>
        <button
          onClick={() => setLeftTab('pending')}
          className={`flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg transition-colors border ${
            leftTab === 'pending'
              ? 'border-amber-500/60 text-white bg-amber-500/15'
              : 'border-transparent text-slate-500 hover:text-white hover:bg-white/5'
          }`}
        >
          <i className="fa-solid fa-clock text-[10px]" /> Pendientes
          {pendingCount > 0 && (
            <span className="bg-amber-500 text-black text-[10px] font-black px-1.5 py-0.5 rounded-full">
              {pendingCount}
            </span>
          )}
        </button>

        {/* Spacer */}
        <div className="flex-1" />

        {/* Botones de acción */}
        <div className="flex items-center gap-1.5 flex-wrap">
          <button
            onClick={() => setCashMovement('IN')}
            className="flex items-center gap-1.5 text-xs font-bold px-2.5 rounded-lg transition-colors active:scale-95"
            style={{
              minHeight: 34,
              background: 'rgba(16,185,129,0.12)',
              border: '1.5px solid rgba(16,185,129,0.45)',
              color: '#047857',
            }}
            title="Entrada de efectivo"
          >
            <i className="fa-solid fa-arrow-down text-xs" /> Entrada
          </button>
          <button
            onClick={() => setCashMovement('OUT')}
            className="flex items-center gap-1.5 text-xs font-bold px-2.5 rounded-lg transition-colors active:scale-95"
            style={{
              minHeight: 34,
              background: 'rgba(239,68,68,0.12)',
              border: '1.5px solid rgba(239,68,68,0.45)',
              color: '#b91c1c',
            }}
            title="Salida de efectivo"
          >
            <i className="fa-solid fa-arrow-up text-xs" /> Salida
          </button>
          <button
            onClick={() => setReturnModal(true)}
            className="flex items-center gap-1.5 text-xs font-bold px-2.5 rounded-lg transition-colors active:scale-95"
            style={{
              minHeight: 34,
              background: 'rgba(245,158,11,0.14)',
              border: '1.5px solid rgba(245,158,11,0.50)',
              color: '#b45309',
            }}
            title="Devoluciones"
          >
            <i className="fa-solid fa-rotate-left text-xs" /> Devolución
          </button>
          {canEditProducts && (
            <button
              onClick={() => setCreateProductOpen(true)}
              className="flex items-center gap-1.5 text-xs font-bold px-2.5 rounded-lg transition-colors active:scale-95"
              style={{
                minHeight: 34,
                background: 'rgba(13,148,136,0.14)',
                border: '1.5px solid rgba(13,148,136,0.50)',
                color: '#0f766e',
              }}
              title="Crear nuevo producto"
            >
              <i className="fa-solid fa-plus text-xs" /> Producto
            </button>
          )}
          {offlineQueue.length > 0 && (
            <button
              onClick={() => setShowOfflineModal(true)}
              className="flex items-center gap-1.5 text-xs font-bold px-2.5 rounded-lg transition-colors active:scale-95"
              style={{
                minHeight: 34,
                background: 'rgba(234,179,8,0.14)',
                border: '1.5px solid rgba(234,179,8,0.50)',
                color: '#a16207',
              }}
              title="Ventas pendientes de enviar"
            >
              <i className="fa-solid fa-cloud-arrow-up text-xs" />
              Offline
              <span className="bg-amber-500 text-black text-[10px] font-black px-1.5 py-0.5 rounded-full ml-0.5">
                {offlineQueue.length}
              </span>
            </button>
          )}
          <button
            onClick={async () => {
              if (!savedPrinterName) {
                showToast('Configura una impresora', 'error')
                return
              }
              let last
              try {
                last = await salesApi.getMyLast()
                if (!last) {
                  showToast('No hay venta reciente', 'error')
                  return
                }
              } catch (e: unknown) {
                const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
                showToast(detail ?? 'Error al reimprimir', 'error')
                return
              }
              try {
                const b64 = await printerApi.getTicketBase64(last.id)
                if (b64) await printerApi.printViaAgent(savedPrinterName, b64)
                showToast(`Reimprimiendo ${saleLabel(last)}`)
              } catch {
                // El error puede venir del backend (sin bytes) o del agente local.
                // En ambos casos la venta original existe — solo falla la impresión.
                showToast('Ticket guardado pero no se pudo imprimir — verifica que el agente esté corriendo', 'error')
              }
            }}
            className="flex items-center gap-1.5 text-xs font-bold px-2.5 rounded-lg transition-colors active:scale-95"
            style={{
              minHeight: 34,
              background: 'var(--dax-elevated)',
              border: '1.5px solid var(--dax-border-dim)',
              color: 'var(--dax-text-muted)',
            }}
            title="Reimprimir último ticket"
          >
            <i className="fa-solid fa-print text-xs" /> Reimprimir último
          </button>
          <div className="w-px h-4 flex-shrink-0" style={{ background: 'var(--dax-border-dim)' }} />
          <button
            onClick={() => setClosingSession(true)}
            className="flex items-center gap-1.5 text-xs font-semibold px-2.5 rounded-lg transition-colors hover:text-red-500"
            style={{ minHeight: 34, color: 'var(--dax-text-muted)' }}
            title="Cerrar turno"
          >
            <i className="fa-solid fa-lock text-xs" /> Cerrar turno
          </button>
        </div>
      </div>

      {/* Main layout: left | right — 40/60 split (cart dominant) */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left panel — productos + búsqueda */}
        <div className="flex-[40] flex flex-col min-w-0 overflow-hidden">
          {/* Tab content — tabs live in the consolidated header above */}
          <div className="flex-1 overflow-hidden">
            {leftTab === 'products' ? (
              <ProductSearch refreshKey={productRefreshKey} />
            ) : (
              <PendingOrders onLoadOrder={loadOrder} />
            )}
          </div>
        </div>

        {/* Right panel — cart 60% (dominante, atención del cajero) */}
        <div className="flex-[60] min-w-[420px] flex-shrink-0 flex flex-col overflow-hidden">
          <div className="flex-1 overflow-hidden">
            <CartPanel
              onPay={(method) => setPayModal(method)}
              onPark={parkSale}
              customerName={store.customerName}
              onClearCustomer={() => store.setCustomer(null, null)}
              sessionLocked={!store.activeSession}
              onOpenSession={() => setShowSessionModal(true)}
            />
          </div>
        </div>
      </div>

      {/* Payment modals */}
      {payModal === 'CASH' && (
        <CashPaymentModal
          total={total}
          onClose={() => setPayModal(null)}
          onConfirm={handleCashPay}
        />
      )}
      {payModal === 'CARD' && (
        <CardPaymentModal
          total={total}
          onClose={() => setPayModal(null)}
          onConfirm={handleCardPay}
        />
      )}
      {payModal === 'TRANSFER' && (
        <TransferPaymentModal
          total={total}
          onClose={() => setPayModal(null)}
          onConfirm={handleTransferPay}
        />
      )}
      {payModal === 'MIXED' && (
        <MixedPaymentModal
          total={total}
          onClose={() => setPayModal(null)}
          onConfirm={handleMixedPay}
        />
      )}
      {returnModal && (
        <ReturnModal
          onClose={() => setReturnModal(false)}
          onSuccess={() => { setReturnModal(false); showToast('Devolución registrada') }}
          activeSessionId={store.activeSession?.id}
        />
      )}
      {cashMovement && (
        <CashMovementModal
          type={cashMovement}
          onClose={() => setCashMovement(null)}
          onSuccess={(msg) => { setCashMovement(null); showToast(msg) }}
        />
      )}
      {closingSession && (
        <CloseSessionModal
          onClose={() => setClosingSession(false)}
          onConfirm={async (amount, notes) => {
            let closed
            try {
              closed = await cashApi.close(amount, notes || 'Cierre desde POS')
            } catch (err: any) {
              // El turno sigue ABIERTO en el servidor: no marcar la caja
              // como cerrada en la UI ni cerrar el modal en falso.
              const detail = err?.response?.data?.detail
              showToast(
                typeof detail === 'string' && detail.trim()
                  ? detail
                  : 'No se pudo cerrar el turno. Sigue abierto; verifica tu conexión e intenta de nuevo.',
                'error'
              )
              return
            }
            if (closed?.id) {
              if (savedPrinterName) {
                showToast('Imprimiendo corte de caja...')
                printerApi.getCashCutBase64(closed.id)
                  .then(b64 => b64 ? printerApi.printViaAgent(savedPrinterName, b64) : undefined)
                  .catch(() => {
                    showToast('Turno cerrado, pero no pude imprimir el corte. Verifica que el agente esté corriendo.', 'error')
                  })
              } else {
                showToast('Configura tu impresora local para imprimir el corte.', 'error')
              }
            }
            store.setSession(null)
            setClosingSession(false)
          }}
        />
      )}
      {showSessionModal && (
        <SessionModal
          onOpened={(s: CashSession) => {
            store.setSession(s)
            setShowSessionModal(false)
          }}
        />
      )}
      {createProductOpen && (
        <ProductDetailModal
          product={null}
          mode="create"
          canEdit={canEditProducts}
          onClose={() => setCreateProductOpen(false)}
          onSaved={() => {
            setCreateProductOpen(false)
            setProductRefreshKey(k => k + 1)
            showToast('Producto creado')
          }}
        />
      )}
      {showOfflineModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={() => setShowOfflineModal(false)}>
          <div
            className="w-full max-w-md rounded-xl shadow-2xl overflow-hidden"
            style={{ background: 'var(--dax-surface)', border: '1px solid var(--dax-border-dim)' }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="px-4 py-3 flex items-center justify-between" style={{ borderBottom: '1px solid var(--dax-border-dim)' }}>
              <div className="flex items-center gap-2 text-sm font-bold" style={{ color: 'var(--dax-text)' }}>
                <i className="fa-solid fa-cloud-arrow-up text-amber-500" />
                Ventas pendientes de enviar
                <span className="bg-amber-500 text-black text-[10px] font-black px-1.5 py-0.5 rounded-full">
                  {offlineQueue.length}
                </span>
              </div>
              <button
                onClick={() => setShowOfflineModal(false)}
                className="text-slate-400 hover:text-white text-sm"
                title="Cerrar"
              >
                <i className="fa-solid fa-xmark" />
              </button>
            </div>
            <div className="max-h-80 overflow-y-auto">
              {offlineQueue.length === 0 ? (
                <div className="p-6 text-center text-xs text-slate-400">Sin pendientes.</div>
              ) : (
                <ul className="divide-y" style={{ borderColor: 'var(--dax-border-dim)' }}>
                  {offlineQueue.map((p) => (
                    <li key={p.id} className="px-4 py-2.5 text-xs flex items-center justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="font-mono truncate" style={{ color: 'var(--dax-text)' }}>{p.id}</div>
                        <div className="text-slate-500">
                          {new Date(p.enqueued_at).toLocaleString('es-MX')}
                          {p.attempts > 0 && ` · ${p.attempts} intento(s)`}
                        </div>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div className="px-4 py-3 flex items-center justify-end gap-2" style={{ borderTop: '1px solid var(--dax-border-dim)' }}>
              <button
                onClick={runFlush}
                className="text-xs font-bold px-3 py-1.5 rounded-lg"
                style={{
                  background: 'rgba(99,102,241,0.14)',
                  border: '1.5px solid rgba(99,102,241,0.50)',
                  color: '#4338ca',
                }}
              >
                <i className="fa-solid fa-rotate mr-1.5" /> Reintentar ahora
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
