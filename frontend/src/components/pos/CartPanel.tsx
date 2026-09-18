import { useState, useEffect, useMemo, useRef } from 'react'
import { usePOSStore } from '../../store/posStore'
import { toast } from '../../store/toastStore'
import { productsApi } from '../../api/products'
import type { CartItem } from '../../types/sales'
import type { Product } from '../../types/products'
import { ProductDetailModal } from './modals/ProductDetailModal'
import { CustomerModal } from './modals/CustomerModal'
import { PricePickerPopover } from './PricePickerPopover'
import { formatCurrency } from '../../utils/currency'
import { cartLineName } from './variantPicker'
import { confirm } from '../ui/ConfirmDialog'
import { autoTierTarget, forcedTierMap, cajaTierOf } from '../../pages/pos/cartTiers'
import { groupCart, type CartGroup } from '../../pages/pos/cartGroups'
import { useExchangeRateStore } from '../../store/exchangeRateStore'
import { usdSummary } from '../../utils/usd'

type PaymentMethod = 'CASH' | 'CARD' | 'TRANSFER' | 'MIXED'

interface Props {
  onPay: (method: PaymentMethod) => void
  onPark: () => void
  customerName: string | null
  onClearCustomer: () => void
  sessionLocked: boolean
  onOpenSession: () => void
}

export function CartPanel({ onPay, onPark, customerName, onClearCustomer, sessionLocked, onOpenSession }: Props) {
  const { cart, requiresInvoice, updateQty, removeItem, setDiscount, setPrice, setForcedTier,
          addItem, applyCajaToAll, restoreAutoTier,
          setRequiresInvoice, clearCart, isProcessing } = usePOSStore()
  const subtotal = usePOSStore((s) => s.subtotal())
  const tax = usePOSStore((s) => s.tax())
  const total = usePOSStore((s) => s.total())
  const itemCount = usePOSStore((s) => s.itemCount())
  const globalDiscount = usePOSStore((s) => s.globalDiscount)
  const globalDiscountAmount = usePOSStore((s) => s.globalDiscountAmount())
  const setGlobalDiscount = usePOSStore((s) => s.setGlobalDiscount)
  const tip = usePOSStore((s) => s.tip)
  const setTip = usePOSStore((s) => s.setTip)
  const discountedSubtotal = usePOSStore((s) => s.discountedSubtotal())
  // Equivalente en dólares del total. La carga la dispara POS.tsx; aquí solo
  // se lee. `null` (organización sin tipo de cambio) ⇒ no se pinta nada.
  const usdRate = useExchangeRateStore((s) => s.rate)
  const usdLine = usdSummary(total, usdRate)
  const [editingGlobalDisc, setEditingGlobalDisc] = useState(false)
  // El cliente se asigna desde aquí: el cajero no tenía dónde hacerlo.
  const [clienteAbierto, setClienteAbierto] = useState(false)
  const [globalDiscInput, setGlobalDiscInput] = useState('0')

  const ck = (item: CartItem) => item.cart_key ?? item.product_id

  // Editor único — un solo modo activo a la vez. Abrir descuento en fila A
  // cierra automáticamente el editor de precio en fila B.
  type EditingMode = 'price' | 'discount' | 'qty'
  const [editing, setEditing] = useState<{ key: string; mode: EditingMode } | null>(null)
  const editingPrice = editing?.mode === 'price' ? editing.key : null
  const editingDiscount = editing?.mode === 'discount' ? editing.key : null
  const editingQty = editing?.mode === 'qty' ? editing.key : null

  const [discountInput, setDiscountInput] = useState('')
  const [priceInput, setPriceInput] = useState('')
  const [qtyInput, setQtyInput] = useState('')

  // Single ref pointing at the trigger of the currently-open popover.
  // Only one popover is ever open at a time, so we don't need a ref-per-row.
  const activePriceTriggerRef = useRef<HTMLButtonElement | null>(null)

  // Precios forzados (inmunes al auto-tier): derivados del flag persistido en cada
  // ítem, que sobrevive al recargar y al park/resume porque va en cart_json. Antes
  // era estado + efecto y, al remontar, el efecto de auto-tier corría en el mismo
  // commit y leía el Map todavía vacío, así que pisaba el precio forzado (C-03).
  const forcedPrices = useMemo(() => forcedTierMap(cart), [cart])

  // Detail modal
  const [detailProduct, setDetailProduct] = useState<Product | null>(null)

  // Agrupar ítems por variante (o por product_id si no la hay) — ver cartGroups.ts
  const groups = useMemo((): CartGroup[] => groupCart(cart), [cart])

  // Auto-precio escalonado según total de unidades combinadas.
  // autoTierTarget salta los ítems con precio forzado leyendo el flag del propio
  // ítem, así que no depende de ningún estado que deba hidratarse antes.
  useEffect(() => {
    for (const group of groups) {
      const unit = group.unit
      if (!unit) continue
      const cajasQty = group.cajas.reduce((sum, c) => sum + c.quantity, 0)
      const target = autoTierTarget(unit, cajasQty)
      if (target !== null) setPrice(unit.cart_key ?? unit.product_id, target)
    }
  }, [cart]) // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-restructura: si piezas alcanza el equivalente a una caja completa,
  // convertir automáticamente → N cajas + resto piezas
  useEffect(() => {
    for (const group of groups) {
      const unit = group.unit
      if (!unit || group.cajas.length > 0) continue  // solo cuando no hay cajas activas
      if (unit.cajaForcedByBulk) continue  // user explicitly bulk-applied → no auto-restructure
      const cajaTier = cajaTierOf(unit)
      if (!cajaTier || cajaTier.min_quantity <= 0) continue
      if (unit.quantity < cajaTier.min_quantity) continue

      const unitsPerBox = cajaTier.min_quantity
      const cajasQty = Math.floor(unit.quantity / unitsPerBox)
      const remainder = unit.quantity % unitsPerBox
      const cartKey = ck(unit)
      // Precio por caja: si el tier está vinculado a un packaging_unit, usar
      // su package_price (precio total de la caja, P2). Fallback: unit_price *
      // units_per_box (asume tier per-piece).
      const linkedPkg = cajaTier.linked_package_id
        ? unit.packaging_units?.find(pk => pk.id === cajaTier.linked_package_id)
        : null
      const pricePerBox = linkedPkg?.package_price ?? cajaTier.unit_price * unitsPerBox

      // remainder === 0 deja la línea de piezas en cero y updateQty la elimina
      // del carrito, así que no hay flag que limpiar.
      updateQty(cartKey, remainder)
      addItem({
        product_id: unit.product_id,
        cart_key: `${unit.product_id}::caja::${cajaTier.id}`,
        unit_kind: 'package',
        base_price: pricePerBox,
        sku: unit.sku,
        name: unit.name,
        price: pricePerBox,
        quantity: cajasQty,
        discount: 0,
        subtotal: cajasQty * pricePerBox,
        stock: unit.stock,
        prices: unit.prices,
        packaging_units: unit.packaging_units,
      })
    }
  }, [cart]) // eslint-disable-line react-hooks/exhaustive-deps

  const isEmpty = cart.length === 0

  const openDetail = (item: CartItem) => {
    setDetailProduct({
      id: item.product_id,
      sku: item.sku,
      name: item.name,
      description: null,
      brand_id: null,
      brand_name: null,
      department: null,
      department_name: null,
      unit: null,
      cost: 0,
      price: item.price,
      stock: item.quantity,
      stock_total: item.quantity,
      image_url: null,
      is_active: true,
    })
    productsApi.getById(item.product_id).then(setDetailProduct).catch(() => {})
  }

  // Aplica precio y lo marca como forzado (inmune a auto-tier).
  // Persiste el flag en el ítem para sobrevivir al park/resume.
  const applyPrice = (cartKey: string, price: number, tierName: string) => {
    setPrice(cartKey, price)
    setForcedTier(cartKey, tierName)
    setEditing(null)
  }

  // Vuelve al modo automático: limpia el forzado y deja que el auto-tier recalcule
  const resetToAuto = (cartKey: string) => {
    setForcedTier(cartKey, null)
    setEditing(null)
    // Forzar re-evaluación del auto-tier vaciando y reponiendo el precio al base
    // (el useEffect se ejecutará en el próximo render del carrito)
  }

  // Vaciar el carrito es destructivo y no se puede deshacer: se pregunta antes,
  // porque el botón vive a un dedo de "Pausar" y de las filas del ticket.
  const confirmarLimpiar = async () => {
    const lineas = cart.length
    const ok = await confirm({
      title: 'Vaciar el carrito',
      message: lineas === 1
        ? 'Se quitará la única línea del ticket. No se puede deshacer.'
        : `Se quitarán las ${lineas} líneas del ticket. No se puede deshacer.`,
      confirmText: 'Vaciar',
      cancelText: 'Cancelar',
      variant: 'danger',
    })
    if (ok) clearCart()
  }

  const removeGroup = (group: CartGroup) => {
    if (group.unit) {
      removeItem(ck(group.unit))
    }
    group.cajas.forEach(c => removeItem(ck(c)))
  }

  const buildCajaItem = (source: CartItem, cajaTier: NonNullable<CartItem['prices']>[0]): CartItem => {
    // Si el tier está vinculado a un packaging_unit, usar su package_price.
    // Fallback: unit_price * min_quantity (per-piece tier).
    const linkedPkg = cajaTier.linked_package_id
      ? source.packaging_units?.find(pk => pk.id === cajaTier.linked_package_id)
      : null
    const pricePerBox = linkedPkg?.package_price ?? cajaTier.unit_price * cajaTier.min_quantity
    return {
      product_id: source.product_id,
      cart_key: `${source.product_id}::caja::${cajaTier.id}`,
      unit_kind: 'package',
      // base_price del ítem caja = precio de UNA caja (no del producto en piezas).
      // Si addItem detecta una caja existente y lleva re-evaluación de tier,
      // unit_kind='package' la salta; aún así base_price queda correcto si algo
      // intenta restaurar.
      base_price: pricePerBox,
      sku: source.sku,
      name: source.name,
      price: pricePerBox,
      quantity: 1,
      discount: 0,
      subtotal: pricePerBox,
      stock: source.stock,
      prices: source.prices,
      packaging_units: source.packaging_units,
    }
  }

  const toggleCaja = (group: CartGroup) => {
    const source = group.unit ?? group.cajas[0]
    const cajaTier = cajaTierOf(source)
    if (!cajaTier) return

    if (group.cajas.length > 0) {
      group.cajas.forEach(c => removeItem(ck(c)))
      return
    }

    // Guard: ¿cabe al menos 1 caja en el stock disponible?
    if (source.stock !== undefined && source.stock > 0) {
      if (cajaTier.min_quantity > source.stock) return
      // Si las piezas actuales + 1 caja exceden el stock, reducir piezas para hacer espacio
      const unitQty = group.unit?.quantity ?? 0
      const overage = unitQty + cajaTier.min_quantity - source.stock
      if (overage > 0 && group.unit) {
        const newQty = unitQty - overage
        if (newQty <= 0) {
          removeItem(ck(group.unit))
        } else {
          updateQty(ck(group.unit), newQty)
        }
      }
    }

    addItem(buildCajaItem(source, cajaTier))
  }

  // Componente interno para controles de cantidad
  // maxQty: límite calculado externamente (piezas para unit, cajas para caja-item)
  const QtyRow = ({ item, maxQty }: { item: CartItem; maxQty?: number }) => {
    const key = ck(item)
    return (
      <div className="flex items-center gap-2">
        <button
          onClick={() => updateQty(key, item.quantity - 1)}
          className="w-11 h-11 rounded-lg flex items-center justify-center text-base font-bold transition-all hover:scale-105 active:scale-95"
          style={{ background: 'var(--dax-danger-soft)', color: 'var(--dax-danger)', border: '1px solid color-mix(in srgb, var(--dax-danger) 35%, transparent)' }}
        >
          <i className="fa-solid fa-minus text-sm" />
        </button>
        {editingQty === key ? (
          <input
            type="number"
            value={qtyInput}
            onChange={(e) => setQtyInput(e.target.value)}
            onBlur={() => {
              const q = Math.min(Math.max(1, parseInt(qtyInput) || 1), maxQty ?? Infinity)
              updateQty(key, q)
              setEditing(null)
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter') (e.target as HTMLInputElement).blur()
              if (e.key === 'Escape') setEditing(null)
            }}
            className="w-20 text-center font-black text-xl rounded-lg px-1 py-2 outline-none"
            style={{ background: 'var(--dax-card)', border: '1px solid var(--dax-accent)', color: 'var(--dax-text)' }}
            min="1" max={maxQty ?? undefined} step="1"
            autoFocus
          />
        ) : (
          <span
            onClick={() => { setEditing({ key, mode: 'qty' }); setQtyInput(String(item.quantity)) }}
            className="w-20 text-center font-black text-xl cursor-text select-none tabular-nums"
            style={{ color: 'var(--dax-text)' }}
            title="Click para editar"
          >
            {item.quantity}
          </span>
        )}
        <button
          onClick={() => updateQty(key, item.quantity + 1)}
          disabled={maxQty !== undefined && item.quantity >= maxQty}
          className="w-11 h-11 rounded-lg flex items-center justify-center text-base font-bold transition-all hover:scale-105 active:scale-95 disabled:opacity-30 disabled:cursor-not-allowed"
          style={{ background: 'var(--dax-success-soft)', color: 'var(--dax-success)', border: '1px solid color-mix(in srgb, var(--dax-success) 35%, transparent)' }}
        >
          <i className="fa-solid fa-plus text-sm" />
        </button>
      </div>
    )
  }

  return (
    <div className="relative flex flex-col h-full" style={{ background: 'var(--dax-card)', borderLeft: '1px solid var(--dax-border-dim)' }}>
      {/* Header. `relative z-30` lo deja por encima del velo de caja cerrada
          (`absolute inset-0 z-20` más abajo), que si no se comía el clic en
          "Cliente" — y anotar el cliente no cobra nada. */}
      <div className="relative z-30 flex items-center justify-between px-4 py-3" style={{ borderBottom: '1px solid var(--dax-border-dim)' }}>
        <div className="flex items-center gap-2">
          <i className="fa-solid fa-shopping-cart text-indigo-400" />
          <span className="text-sm font-black" style={{ color: 'var(--dax-text)' }}>Carrito</span>
          {itemCount > 0 && (
            <span className="bg-dax-accent text-dax-on-accent text-[10px] font-black px-1.5 py-0.5 rounded-full">
              {itemCount}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {/* Siempre visible: se puede anotar el cliente con el carrito vacío
              y sin caja abierta (no cobra nada). */}
          {!customerName && (
            <button
              onClick={() => setClienteAbierto(true)}
              className="text-dax-muted hover:text-dax-accent text-sm min-h-[44px] flex items-center gap-1 transition-colors font-semibold"
              title="Asignar cliente a la venta"
            >
              <i className="fa-solid fa-user-plus text-[11px]" /> Cliente
            </button>
          )}
          {!isEmpty && (
            <button
              onClick={onPark}
              className="text-dax-warning hover:brightness-110 text-sm min-h-[44px] flex items-center gap-1 transition-colors font-semibold"
              title="Guardar como pedido pendiente"
            >
              <i className="fa-solid fa-pause text-[10px]" /> Pausar
            </button>
          )}
          {!isEmpty && (
            <button
              onClick={confirmarLimpiar}
              className="text-dax-muted hover:text-dax-danger text-sm min-h-[44px] flex items-center gap-1 transition-colors"
            >
              <i className="fa-solid fa-trash" /> Limpiar
            </button>
          )}
        </div>
      </div>

      {/* Cliente — solo visible cuando hay uno seleccionado */}
      {customerName && (
        <div className="relative z-30 px-4 py-2.5 flex items-center gap-2" style={{ borderBottom: '1px solid var(--dax-row-border)' }}>
          <i className="fa-solid fa-user text-dax-muted text-sm" />
          <button
            onClick={() => setClienteAbierto(true)}
            className="text-sm flex-1 truncate text-left font-medium min-h-[44px] hover:brightness-110 transition-colors"
            style={{ color: 'var(--dax-text)' }}
            title="Cambiar cliente"
          >
            {customerName}
          </button>
          <button onClick={onClearCustomer} className="text-dax-muted hover:text-dax-danger text-sm">
            <i className="fa-solid fa-xmark" />
          </button>
        </div>
      )}

      {/* Items */}
      <div className="flex-1 overflow-y-auto">
        {isEmpty ? (
          <div className="flex flex-col items-center justify-center h-full text-center p-8">
            <i className="fa-solid fa-shopping-cart text-dax-faint text-4xl mb-3" />
            <p className="text-dax-muted text-sm">Carrito vacío</p>
            <p className="text-dax-faint text-xs mt-1">Busca y agrega productos</p>
          </div>
        ) : (
          <div>
            {[...groups].reverse().map((group) => {
              const displayItem = group.unit ?? group.cajas[0]
              const cajaTier = cajaTierOf(displayItem)
              const hasCaja = !!cajaTier
              const cajaActive = group.cajas.length > 0
              const groupSubtotal = (group.unit?.subtotal ?? 0) + group.cajas.reduce((s, c) => s + c.subtotal, 0)
              const unitItem = group.unit
              const priceKey = unitItem ? ck(unitItem) : null
              const hasTiers = (unitItem?.prices?.length ?? 0) > 0

              // Total piezas: piezas sueltas + (cajas × unitsPerBox)
              const unitsPerBox = cajaTier?.min_quantity ?? 0
              const totalPiezas = (unitItem?.quantity ?? 0) + group.cajas.reduce((s, c) => s + c.quantity * unitsPerBox, 0)

              // Tier activo: el que coincide con el precio actual del ítem
              const activeTier = hasTiers
                ? unitItem!.prices!.find(t => Math.abs(t.unit_price - (unitItem?.price ?? 0)) < 0.01)
                : null
              const isForcedPrice = priceKey ? forcedPrices.has(priceKey) : false
              const forcedTierName = priceKey ? forcedPrices.get(priceKey) : undefined

              return (
                <div
                  key={group.key}
                  style={{ borderBottom: '1px solid var(--dax-row-border)' }}
                  className="px-4 pt-4 pb-4"
                >
                  {/* Línea 1: nombre + [×] */}
                  <div className="flex items-start gap-2 mb-1.5">
                    <button
                      onClick={() => openDetail(displayItem)}
                      className="flex-1 font-bold text-base leading-snug text-left hover:text-indigo-400 transition-colors truncate"
                      style={{ color: 'var(--dax-text)' }}
                      title="Ver detalles"
                    >
                      {cartLineName(displayItem.name, displayItem.variant_label)}
                    </button>
                    <button
                      onClick={() => removeGroup(group)}
                      className="text-dax-muted hover:text-dax-danger text-sm flex-shrink-0 min-h-[40px] min-w-[40px] flex items-center justify-center rounded-lg -mt-1"
                    >
                      <i className="fa-solid fa-xmark" />
                    </button>
                  </div>

                  {/* Línea 2: SKU + total piezas + tier badge + precio total */}
                  <div className="flex items-center gap-2 mb-2.5">
                    <p className="text-xs font-mono text-dax-muted">{displayItem.sku}</p>
                    {/* Talla de la línea: sin esto, dos tallas del mismo
                        producto eran dos renglones idénticos en el ticket. */}
                    {displayItem.variant_label && (
                      <span
                        className="text-[10px] font-black px-1.5 py-0.5 rounded flex-shrink-0"
                        style={{ background: 'var(--dax-accent-soft)', color: 'var(--dax-accent-text)' }}
                      >
                        {displayItem.variant_label}
                      </span>
                    )}
                    {/* Total piezas: siempre visible */}
                    <span className="flex items-center gap-1 text-xs font-semibold tabular-nums" style={{ color: 'var(--dax-text-muted)' }}>
                      <i className="fa-solid fa-cube text-[9px] opacity-60" />
                      {totalPiezas} pz
                    </span>
                    {/* Badge del tier — indigo normal si auto, ámbar si forzado */}
                    {(activeTier || isForcedPrice) && (
                      <span
                        className="text-[10px] font-bold px-1.5 py-0.5 rounded flex items-center gap-1"
                        style={{
                          background: isForcedPrice ? 'var(--dax-warning-soft)' : 'var(--dax-accent-soft)',
                          color: isForcedPrice ? 'var(--dax-warning)' : 'var(--dax-accent-text)',
                        }}
                      >
                        {isForcedPrice && <i className="fa-solid fa-bolt text-[8px]" />}
                        {forcedTierName ?? activeTier?.price_name}
                      </span>
                    )}
                    <span className="flex-1" />
                    <span className="font-black text-lg text-emerald-600 tabular-nums">{formatCurrency(groupSubtotal)}</span>
                  </div>

                  {/* Price-picker popover (portaled — replaces inline panel). */}
                  {priceKey && unitItem && (
                    <PricePickerPopover
                      open={editingPrice === priceKey}
                      triggerRef={activePriceTriggerRef}
                      basePrice={unitItem.base_price ?? unitItem.price}
                      currentPrice={unitItem.price}
                      tiers={unitItem.prices ?? []}
                      isForced={isForcedPrice}
                      priceInput={priceInput}
                      onPriceInputChange={setPriceInput}
                      onSelectTier={(price, name) => applyPrice(priceKey, price, name)}
                      onSelectFree={(price) => applyPrice(priceKey, price, 'Libre')}
                      onResetToAuto={() => resetToAuto(priceKey)}
                      onClose={() => setEditing(null)}
                    />
                  )}

                  {/* Editor de descuento */}
                  {priceKey && editingDiscount === priceKey && (
                    <div className="flex items-center gap-2 mb-2">
                      <span className="text-[10px]" style={{ color: 'var(--dax-text-muted)' }}>Descuento:</span>
                      <input
                        type="number"
                        value={discountInput}
                        onChange={(e) => setDiscountInput(e.target.value)}
                        onBlur={() => {
                          const d = Math.min(100, Math.max(0, parseFloat(discountInput) || 0))
                          setDiscount(priceKey, d)
                          setEditing(null)
                        }}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') (e.target as HTMLInputElement).blur()
                          if (e.key === 'Escape') setEditing(null)
                        }}
                        className="w-14 text-center text-xs rounded px-1 py-0.5 outline-none"
                        style={{ background: 'var(--dax-card)', border: '1px solid var(--dax-accent)', color: 'var(--dax-text)' }}
                        min="0" max="100" step="1"
                        autoFocus
                      />
                      <span className="text-xs text-dax-muted">%</span>
                      <button onClick={() => setEditing(null)} className="text-[9px] text-dax-muted hover:text-dax-text">✕</button>
                    </div>
                  )}

                  {/* Fila Unidades — siempre visible si hay producto en carrito
                      Cuando unit=null (todas piezas se convirtieron a cajas exactas):
                      se muestra fila fantasma "0 piezas" con solo [+] para reactivar */}
                  {(() => {
                    // Ícono de caja: cuando piezas ≥ min_quantity del tier Caja
                    const unitCajaTier = unitItem ? cajaTierOf(unitItem) : cajaTier
                    const boxEquiv = unitCajaTier && unitItem && unitItem.quantity >= unitCajaTier.min_quantity
                      ? Math.floor(unitItem.quantity / unitCajaTier.min_quantity)
                      : 0

                    // [+] de la fila fantasma: crea un nuevo ítem de unidades al precio base.
                    // Si la línea tiene talla, el ítem reconstruido la conserva (misma
                    // forma que ProductSearch: cart_key = variant_id). OJO: nunca copiar
                    // el `cart_key` de displayItem cuando es una caja — lleva '::caja::'
                    // y el ítem de piezas volvería a contarse como caja.
                    const addGhostUnit = () => addItem({
                      product_id: displayItem.product_id,
                      base_price: displayItem.base_price ?? displayItem.price,
                      sku: displayItem.sku,
                      name: displayItem.name,
                      price: displayItem.base_price ?? displayItem.price,
                      quantity: 1,
                      discount: 0,
                      subtotal: displayItem.base_price ?? displayItem.price,
                      stock: displayItem.stock,
                      prices: displayItem.prices,
                      ...(displayItem.variant_id
                        ? { variant_id: displayItem.variant_id, cart_key: displayItem.variant_id }
                        : {}),
                      ...(displayItem.variant_label ? { variant_label: displayItem.variant_label } : {}),
                    })

                    return (
                    <div className="flex items-center gap-2 mb-1">
                      {/* Label: icono pieza o badge equivalente a caja */}
                      <div className="flex items-center gap-1.5 w-16 flex-shrink-0">
                        {boxEquiv > 0 ? (
                          <span
                            className="flex items-center gap-1 text-[10px] font-bold px-1.5 py-0.5 rounded"
                            style={{ background: 'rgba(251,191,36,0.15)', color: '#fbbf24' }}
                            title={`Equivale a ${boxEquiv} ${unitCajaTier!.price_name}${boxEquiv > 1 ? 's' : ''}`}
                          >
                            <i className="fa-solid fa-box text-[9px]" />
                            ×{boxEquiv}
                          </span>
                        ) : (
                          <span className="flex items-center gap-1 text-xs font-semibold" style={{ color: 'var(--dax-text-muted)' }}>
                            <i className="fa-solid fa-cube text-[10px]" /> Pza
                          </span>
                        )}
                      </div>

                      {/* Controles de cantidad */}
                      {unitItem ? (
                        <QtyRow
                          item={unitItem}
                          maxQty={unitItem.stock !== undefined
                            ? unitItem.stock - group.cajas.reduce((s, c) => s + c.quantity * (cajaTier?.min_quantity ?? 1), 0)
                            : undefined}
                        />
                      ) : (
                        /* Fila fantasma: unidades = 0, solo [+] activo */
                        <div className="flex items-center gap-2">
                          <button disabled
                            className="w-11 h-11 rounded-lg flex items-center justify-center text-base font-bold opacity-20 cursor-not-allowed"
                            style={{ background: 'var(--dax-danger-soft)', color: 'var(--dax-danger)', border: '1px solid color-mix(in srgb, var(--dax-danger) 35%, transparent)' }}>
                            <i className="fa-solid fa-minus text-sm" />
                          </button>
                          <span className="w-20 text-center font-black text-xl tabular-nums opacity-30"
                            style={{ color: 'var(--dax-text)' }}>0</span>
                          <button
                            onClick={addGhostUnit}
                            disabled={
                              displayItem.stock !== undefined &&
                              displayItem.stock > 0 &&
                              totalPiezas >= displayItem.stock
                            }
                            className="w-11 h-11 rounded-lg flex items-center justify-center text-base font-bold transition-all hover:scale-105 active:scale-95 disabled:opacity-30 disabled:cursor-not-allowed"
                            style={{ background: 'var(--dax-success-soft)', color: 'var(--dax-success)', border: '1px solid color-mix(in srgb, var(--dax-success) 35%, transparent)' }}>
                            <i className="fa-solid fa-plus text-sm" />
                          </button>
                        </div>
                      )}

                      {/* Precio/u y descuento — solo cuando hay ítem de unidades */}
                      {unitItem && editingDiscount !== priceKey && (
                        <div className="flex items-center gap-1.5 ml-auto">
                          <button
                            ref={(el) => {
                              if (editingPrice === priceKey) activePriceTriggerRef.current = el
                            }}
                            onClick={() => {
                              if (editingPrice === priceKey) {
                                setEditing(null)
                              } else {
                                setEditing({ key: priceKey!, mode: 'price' })
                                setPriceInput(String(unitItem.price ?? 0))
                              }
                            }}
                            className="text-sm tabular-nums flex items-center gap-1.5 min-h-[40px] px-2 rounded-lg transition-colors hover:bg-dax-elevated"
                            style={{ color: hasTiers ? 'var(--dax-accent-text)' : 'var(--dax-text-muted)' }}
                            title="Cambiar precio / tier"
                          >
                            {hasTiers && <i className="fa-solid fa-tags text-[9px]" />}
                            {formatCurrency(unitItem.price)}/u
                          </button>
                          <button
                            onClick={() => { setEditing({ key: priceKey!, mode: 'discount' }); setDiscountInput(String(unitItem.discount || 0)) }}
                            className="text-sm tabular-nums min-h-[40px] min-w-[40px] px-2 rounded-lg transition-colors hover:bg-dax-elevated"
                            style={{ color: (unitItem.discount ?? 0) > 0 ? 'var(--dax-warning)' : 'var(--dax-text-muted)' }}
                            title="Descuento"
                          >
                            {(unitItem.discount ?? 0) > 0 ? `-${unitItem.discount}%` : '%'}
                          </button>
                        </div>
                      )}
                      {/* Espaciador cuando no hay unitItem */}
                      {!unitItem && <span className="flex-1" />}

                      {/* Botón CAJA — visible si hay tier de caja */}
                      {hasCaja && (() => {
                        // Puede activar caja si cabe al menos 1 caja en el stock total
                        // (independiente de cuántas piezas haya — toggleCaja reduce piezas si es necesario)
                        const canAddCaja = cajaActive ||
                          !displayItem.stock ||
                          (cajaTier?.min_quantity ?? 1) <= displayItem.stock
                        return (
                          <button
                            onClick={() => toggleCaja(group)}
                            disabled={!canAddCaja}
                            className="text-sm font-bold px-3 min-h-[40px] rounded-lg flex items-center gap-1.5 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                            style={{
                              background: cajaActive ? 'var(--dax-accent)' : 'var(--dax-accent-soft)',
                              border: '1px solid var(--dax-accent)',
                              color: cajaActive ? 'var(--dax-on-accent)' : 'var(--dax-accent-text)',
                            }}
                          >
                            <i className="fa-solid fa-boxes-stacked text-[10px]" />
                            {cajaActive ? `×${cajaTier!.min_quantity}` : 'Caja'}
                          </button>
                        )
                      })()}
                    </div>
                    )
                  })()}

                  {/* Filas caja */}
                  {group.cajas.map(cajaItem => {
                    // Recuperar el tier de caja por cart_key
                    const tierForCaja = displayItem.prices?.find(
                      p => `${group.productId}::caja::${p.id}` === cajaItem.cart_key
                    )
                    const unitsPerBox = tierForCaja?.min_quantity ?? cajaTier?.min_quantity ?? 1
                    // Precio implícito por pieza al comprar por caja + ahorro vs menudeo.
                    const unitPriceCaja = unitsPerBox > 0 ? cajaItem.price / unitsPerBox : 0
                    const basePz = displayItem.base_price ?? displayItem.price
                    const savingsPct = (basePz > 0 && unitPriceCaja > 0)
                      ? Math.round((1 - unitPriceCaja / basePz) * 100)
                      : 0
                    // Forzar precio por pieza en caja: paralelo al flujo de unit.
                    const cajaKey = ck(cajaItem)
                    const isCajaForced = forcedPrices.has(cajaKey)
                    // Auto-precio por caja: linked package > tier.unit_price * units.
                    const linkedPkg = tierForCaja?.linked_package_id
                      ? displayItem.packaging_units?.find(pk => pk.id === tierForCaja.linked_package_id)
                      : undefined
                    const autoBoxPrice = linkedPkg?.package_price ?? (tierForCaja?.unit_price ?? 0) * unitsPerBox
                    const autoPiecePrice = unitsPerBox > 0 ? autoBoxPrice / unitsPerBox : 0
                    return (
                      <div
                        key={cajaKey}
                        className="flex items-start gap-2 mt-2 pt-2"
                        style={{ borderTop: '1px dashed color-mix(in srgb, var(--dax-accent) 35%, transparent)' }}
                      >
                        <span className="flex items-center gap-1.5 w-16 flex-shrink-0 text-xs font-bold text-indigo-400 mt-1">
                          <i className="fa-solid fa-box-open text-[11px]" />
                          ×{unitsPerBox}
                        </span>
                        <div className="flex-1 mt-0.5">
                          <QtyRow
                            item={cajaItem}
                            maxQty={cajaItem.stock !== undefined
                              ? Math.max(0, Math.floor((cajaItem.stock - (group.unit?.quantity ?? 0)) / unitsPerBox))
                              : undefined}
                          />
                        </div>
                        <div className="flex flex-col items-end gap-0.5 ml-auto flex-shrink-0">
                          <div className="flex items-center gap-1.5">
                            <span
                              className="text-[10px] font-bold px-1.5 py-0.5 rounded"
                              style={{ background: 'var(--dax-accent-soft)', color: 'var(--dax-accent-text)' }}
                            >
                              Caja
                            </span>
                            <span className="text-xs tabular-nums font-semibold whitespace-nowrap text-dax-muted">
                              {formatCurrency(cajaItem.price)}/cja
                            </span>
                          </div>
                          {unitsPerBox > 0 && unitPriceCaja > 0 && (
                            <div className="flex items-center gap-1 text-[10px] tabular-nums font-mono whitespace-nowrap">
                              <button
                                ref={(el) => {
                                  if (editingPrice === cajaKey) activePriceTriggerRef.current = el
                                }}
                                onClick={() => {
                                  if (editingPrice === cajaKey) {
                                    setEditing(null)
                                  } else {
                                    setEditing({ key: cajaKey, mode: 'price' })
                                    setPriceInput(unitPriceCaja.toFixed(2))
                                  }
                                }}
                                className="flex items-center gap-1 transition-colors hover:opacity-80"
                                style={{ color: isCajaForced ? 'var(--dax-warning)' : 'var(--dax-text-muted)' }}
                                title="Forzar precio por pieza al vender caja"
                              >
                                {isCajaForced && <i className="fa-solid fa-bolt text-[8px]" />}
                                {formatCurrency(unitPriceCaja)}/pz
                              </button>
                              {savingsPct >= 1 && (
                                <span
                                  className="font-bold px-1 py-0.5 rounded"
                                  style={{ background: 'var(--dax-success-soft)', color: 'var(--dax-success)' }}
                                  title={`Ahorras ${formatCurrency(basePz - unitPriceCaja)} por pieza vs menudeo (${formatCurrency(basePz)}/pz)`}
                                >
                                  −{savingsPct}%
                                </span>
                              )}
                            </div>
                          )}
                        </div>
                        <button
                          onClick={() => {
                            setForcedTier(cajaKey, null)
                            removeItem(cajaKey)
                          }}
                          className="text-dax-muted hover:text-dax-danger text-sm flex-shrink-0 min-h-[40px] min-w-[40px] flex items-center justify-center rounded-lg"
                          title="Quitar cajas"
                        >
                          <i className="fa-solid fa-xmark" />
                        </button>

                        {/* Popover para forzar precio por pieza del caja */}
                        <PricePickerPopover
                          open={editingPrice === cajaKey}
                          triggerRef={activePriceTriggerRef}
                          basePrice={autoPiecePrice}
                          currentPrice={unitPriceCaja}
                          tiers={[]}
                          isForced={isCajaForced}
                          priceInput={priceInput}
                          onPriceInputChange={setPriceInput}
                          onSelectTier={(price) => applyPrice(cajaKey, price * unitsPerBox, 'Caja libre')}
                          onSelectFree={(price) => applyPrice(cajaKey, price * unitsPerBox, 'Caja libre')}
                          onResetToAuto={() => resetToAuto(cajaKey)}
                          onClose={() => setEditing(null)}
                        />
                      </div>
                    )
                  })}
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Totales */}
      <div className="px-4 pt-3 pb-2 space-y-1.5 text-base" style={{ borderTop: '1px solid var(--dax-border-dim)' }}>
        <div className="flex justify-between" style={{ color: 'var(--dax-text-muted)' }}>
          <span>Subtotal</span><span className="tabular-nums font-semibold">{formatCurrency(subtotal)}</span>
        </div>

        {/* Botones pareados: Descuento global | Aplicar caja a todo */}
        <div className="grid grid-cols-2 gap-2 mt-2">
          {/* Izquierda — Descuento global */}
          {editingGlobalDisc ? (
            <div
              className="rounded-lg px-2.5 py-2 flex items-center gap-1.5 bg-dax-warning-soft border border-dax-warning"
              title="Descuento global al ticket"
            >
              <i className="fa-solid fa-tag text-[10px] text-dax-text" />
              <input
                type="number"
                min="0"
                max="100"
                step="1"
                value={globalDiscInput}
                onChange={(e) => setGlobalDiscInput(e.target.value)}
                onBlur={() => {
                  const v = Math.min(100, Math.max(0, parseFloat(globalDiscInput) || 0))
                  setGlobalDiscount(v)
                  setEditingGlobalDisc(false)
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') (e.target as HTMLInputElement).blur()
                  if (e.key === 'Escape') setEditingGlobalDisc(false)
                }}
                className="flex-1 min-w-0 text-right text-xs rounded px-1 py-0.5 outline-none tabular-nums font-bold"
                style={{ background: 'var(--dax-card-solid)', border: '1px solid var(--dax-warning)', color: 'var(--dax-text)' }}
                autoFocus
              />
              <span className="text-xs font-bold text-dax-text">%</span>
            </div>
          ) : globalDiscount > 0 ? (
            <button
              onClick={() => {
                setEditingGlobalDisc(true)
                setGlobalDiscInput(String(globalDiscount || 0))
              }}
              className="rounded-lg px-2.5 py-2 bg-amber-500 border border-amber-400 hover:bg-amber-600 transition-colors text-xs font-bold flex items-center justify-center gap-1.5 shadow-sm"
              style={{ color: '#fff' }}
              title={`Descuento global -${globalDiscount}% (${formatCurrency(globalDiscountAmount)})`}
            >
              <i className="fa-solid fa-tag text-[10px]" style={{ color: '#fff' }} aria-hidden="true" />
              <span className="truncate">Desc. -{globalDiscount}%</span>
            </button>
          ) : (
            <button
              onClick={() => {
                setEditingGlobalDisc(true)
                setGlobalDiscInput(String(globalDiscount || 0))
              }}
              disabled={cart.length === 0}
              className="rounded-lg px-2.5 py-2 bg-amber-500/70 border border-amber-400 hover:bg-amber-500 disabled:opacity-40 disabled:cursor-not-allowed transition-colors text-xs font-bold flex items-center justify-center gap-1.5 shadow-sm"
              style={{ color: '#fff' }}
              title="Aplicar descuento global al ticket"
            >
              <i className="fa-solid fa-tag text-[10px]" style={{ color: '#fff' }} aria-hidden="true" />
              <span className="truncate">Descuento global</span>
            </button>
          )}

          {/* Derecha — Bulk caja: aplica precio caja a todo el carrito o restaura */}
          {(() => {
            const totalCount = cart.length
            const appliedCount = cart.filter((i) => i.cajaForcedByBulk === true).length
            const cajaModeApplied = appliedCount > 0
            return !cajaModeApplied ? (
              <button
                onClick={() => {
                  const sources = new Map()
                  cart.forEach((it) => {
                    sources.set(it.product_id, {
                      prices: it.prices,
                      packaging_units: it.packaging_units,
                    })
                  })
                  const { applied, total } = applyCajaToAll(sources)
                  if (applied === total && total > 0) {
                    toast.success(`Caja aplicada a los ${total} productos`)
                  } else if (applied === 0) {
                    toast.warning('Ningún producto tiene precio caja disponible')
                  } else {
                    toast.success(`Caja aplicada a ${applied} de ${total} productos. ${total - applied} quedan en su precio normal.`)
                  }
                }}
                disabled={cart.length === 0}
                className="rounded-lg px-2.5 py-2 bg-indigo-500/70 border border-indigo-400 hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed transition-colors text-xs font-bold flex items-center justify-center gap-1.5 shadow-sm"
                style={{ color: '#fff' }}
                title="Aplica precio caja a todos los productos del carrito que tengan tier caja configurado y cantidad suficiente. Sobreescribe precios manuales."
              >
                <i className="fa-solid fa-box text-[10px]" style={{ color: '#fff' }} aria-hidden="true" />
                <span className="truncate">Aplicar caja</span>
              </button>
            ) : (
              <button
                onClick={() => restoreAutoTier()}
                className="rounded-lg px-2.5 py-2 bg-emerald-500 border border-emerald-400 hover:bg-emerald-600 transition-colors text-xs font-bold flex items-center justify-center gap-1.5 shadow-sm"
                style={{ color: '#fff' }}
                title={`Caja aplicada en ${appliedCount}/${totalCount} — clic para restaurar`}
              >
                <i className="fa-solid fa-box text-[10px]" style={{ color: '#fff' }} aria-hidden="true" />
                <span className="truncate">Caja {appliedCount}/{totalCount}</span>
              </button>
            )
          })()}
        </div>

        {requiresInvoice && (
          <div className="flex justify-between text-dax-warning font-semibold">
            <span>IVA 16%</span><span className="tabular-nums">{formatCurrency(tax)}</span>
          </div>
        )}
        {/* Propina (gastro): quick % sobre el subtotal con descuento */}
        <div className="flex items-center justify-between gap-2 pt-1">
          <span className="text-xs uppercase tracking-wide" style={{ color: 'var(--dax-text-muted)' }}>
            Propina{tip > 0 && <span className="ml-1 tabular-nums" style={{ color: 'var(--p-accent)' }}>{formatCurrency(tip)}</span>}
          </span>
          <div className="flex items-center gap-1">
            {[0, 0.10, 0.15].map((pct) => {
              const amt = pct === 0 ? 0 : Math.round(discountedSubtotal * pct)
              const active = pct === 0 ? tip === 0 : tip > 0 && Math.abs(tip - amt) < 0.5
              return (
                <button
                  key={pct}
                  onClick={() => setTip(amt)}
                  className="text-xs font-bold px-2.5 py-1 rounded-lg transition-colors"
                  style={{
                    background: active ? 'var(--p-accent)' : 'var(--dax-elevated)',
                    color: active ? '#fff' : 'var(--dax-text-muted)',
                  }}
                >
                  {pct === 0 ? 'Sin' : `${pct * 100}%`}
                </button>
              )
            })}
          </div>
        </div>
        <div className="flex justify-between items-baseline font-black pt-2" style={{ borderTop: '1px solid var(--dax-row-border)', color: 'var(--dax-text)' }}>
          <span className="text-lg uppercase tracking-wide">Total</span>
          <span className="tabular-nums text-dax-text text-4xl">{formatCurrency(total)}</span>
        </div>
        {usdLine && (
          <div
            className="flex justify-end text-xs font-semibold tabular-nums pt-0.5"
            style={{ color: 'var(--dax-text-muted)' }}
            title="Equivalente informativo — el cobro es en pesos"
          >
            {usdLine}
          </div>
        )}
        <div className="flex items-center gap-2 pt-0.5">
          <button
            onClick={() => setRequiresInvoice(!requiresInvoice)}
            className={`flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-lg transition-colors ${
              requiresInvoice
                ? 'bg-dax-warning-soft text-dax-text border border-dax-warning'
                : 'text-dax-muted hover:text-dax-text'
            }`}
          >
            <i className={`fa-solid ${requiresInvoice ? 'fa-check-square' : 'fa-square'}`} />
            Factura (IVA)
          </button>
        </div>
      </div>

      {/* Botones de pago */}
      <div className="px-3 pb-3">
        <div className="grid gap-2" style={{ gridTemplateColumns: '1.4fr 1fr 1fr 1fr' }}>
          <button onClick={() => onPay('CASH')} disabled={isEmpty}
            className="flex flex-col items-center justify-center gap-1 min-h-[56px] px-2 rounded-2xl bg-dax-accent text-dax-on-accent font-bold shadow-lg shadow-black/10 hover:brightness-110 transition disabled:opacity-30 disabled:cursor-not-allowed">
            <i className="fa-solid fa-money-bill text-xl" aria-hidden="true" />
            <span className="text-sm font-bold">Efectivo</span>
          </button>
          <button onClick={() => onPay('CARD')} disabled={isEmpty}
            className="flex flex-col items-center justify-center gap-1 min-h-[56px] px-2 rounded-2xl bg-dax-elevated text-dax-text font-semibold border border-dax-border hover:brightness-95 dark:hover:brightness-125 transition disabled:opacity-30 disabled:cursor-not-allowed">
            <i className="fa-solid fa-credit-card text-xl" aria-hidden="true" />
            <span className="text-sm">Tarjeta</span>
          </button>
          <button onClick={() => onPay('TRANSFER')} disabled={isEmpty}
            className="flex flex-col items-center justify-center gap-1 min-h-[56px] px-2 rounded-2xl bg-dax-elevated text-dax-text font-semibold border border-dax-border hover:brightness-95 dark:hover:brightness-125 transition disabled:opacity-30 disabled:cursor-not-allowed">
            <i className="fa-solid fa-mobile-screen text-xl" aria-hidden="true" />
            <span className="text-sm">Transfer.</span>
          </button>
          <button onClick={() => onPay('MIXED')} disabled={isEmpty}
            className="flex flex-col items-center justify-center gap-1 min-h-[56px] px-2 rounded-2xl bg-dax-elevated text-dax-text font-semibold border border-dax-border hover:brightness-95 dark:hover:brightness-125 transition disabled:opacity-30 disabled:cursor-not-allowed">
            <i className="fa-solid fa-layer-group text-xl" aria-hidden="true" />
            <span className="text-sm">Mixto</span>
          </button>
        </div>
      </div>

      {/* Overlay: procesando. Sube a z-40 para seguir tapando el header, que
          ahora va en z-30: durante un cobro nada del carrito se toca. */}
      {isProcessing && (
        <div
          className="absolute inset-0 z-40 flex flex-col items-center justify-center gap-3 backdrop-blur-sm"
          style={{ background: 'rgba(0,0,0,0.55)' }}
        >
          <div className="flex flex-col items-center gap-2 px-6 py-4 rounded-2xl"
               style={{ background: 'var(--dax-card)', border: '1px solid var(--dax-border-dim)' }}>
            <i className="fa-solid fa-spinner fa-spin text-2xl" style={{ color: 'var(--dax-accent)' }} />
            <p className="text-xs font-black uppercase tracking-widest"
               style={{ color: 'var(--dax-text)' }}>
              Procesando...
            </p>
          </div>
        </div>
      )}

      {/* Overlay: caja cerrada */}
      {sessionLocked && (
        <div
          className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-3 backdrop-blur-sm"
          style={{ background: 'rgba(0,0,0,0.55)' }}
        >
          <div className="flex flex-col items-center gap-3 px-6 py-5 rounded-2xl"
               style={{ background: 'var(--dax-card)', border: '1px solid var(--dax-border-dim)' }}>
            <div className="w-14 h-14 rounded-full flex items-center justify-center"
                 style={{ background: 'var(--dax-accent-soft)' }}>
              <i className="fa-solid fa-lock text-2xl" style={{ color: 'var(--dax-accent)' }} />
            </div>
            <p className="text-sm font-black uppercase tracking-widest"
               style={{ color: 'var(--dax-text)' }}>
              Caja cerrada
            </p>
            <p className="text-xs text-center" style={{ color: 'var(--dax-text-muted)' }}>
              Abre un turno para comenzar a vender
            </p>
            <button
              onClick={onOpenSession}
              className="dax-btn-primary text-sm px-5 py-2 justify-center"
            >
              <i className="fa-solid fa-lock-open" /> Abrir Turno
            </button>
          </div>
        </div>
      )}

      <ProductDetailModal
        product={detailProduct}
        onClose={() => setDetailProduct(null)}
        canEdit={true}
      />

      {clienteAbierto && <CustomerModal onClose={() => setClienteAbierto(false)} />}
    </div>
  )
}
