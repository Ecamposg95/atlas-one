import { create } from 'zustand'
import type { CartItem, CartItemPrice, CartItemPackaging } from '../types/sales'
import type { ParkedTicket } from '../api/sales'
import type { CashSession } from '../types/cash'
import { priceForQty } from '../pages/pos/cartTiers'

/** Estructura mínima leída por applyCajaToAll para cada producto del carrito */
export interface ProductWithCajaInfo {
  prices?: CartItemPrice[]
  packaging_units?: CartItemPackaging[]
}

interface POSStore {
  // Carrito
  cart: CartItem[]
  requiresInvoice: boolean
  isProcessing: boolean
  globalDiscount: number // % aplicado a todo el ticket, además del descuento por línea
  tip: number // propina en pesos (gastro)

  // Sesión de caja
  activeSession: CashSession | null

  // Cliente
  customerName: string | null
  customerId: number | null

  // Tickets pausados (parked_tickets — snapshot de carrito sin afectar stock)
  parkedTickets: ParkedTicket[]
  currentParkedId: string | null

  // Impresora local (agente)
  printerName: string | null

  // Carrito actions
  addItem: (item: CartItem) => void
  updateQty: (cartKey: string, qty: number) => void
  removeItem: (cartKey: string) => void
  setDiscount: (cartKey: string, discount: number) => void
  setPrice: (cartKey: string, price: number) => void
  setForcedTier: (cartKey: string, tier: string | null) => void
  replaceItem: (cartKey: string, newItem: CartItem) => void
  clearCart: () => void
  setRequiresInvoice: (val: boolean) => void
  setIsProcessing: (val: boolean) => void
  setGlobalDiscount: (pct: number) => void
  setTip: (amount: number) => void

  // Sesión
  setSession: (session: CashSession | null) => void

  // Cliente
  setCustomer: (id: number | null, name: string | null) => void

  // Bulk caja
  applyCajaToAll: (sources: Map<string, ProductWithCajaInfo>) => { applied: number; total: number }
  restoreAutoTier: () => void

  // Tickets pausados
  setParkedTickets: (tickets: ParkedTicket[]) => void
  setCurrentParkedId: (id: string | null) => void

  // Impresora
  setPrinterName: (name: string | null) => void

  // Computed
  subtotal: () => number              // suma de líneas sin descuento global
  discountedSubtotal: () => number    // subtotal * (1 - globalDiscount/100)
  globalDiscountAmount: () => number  // monto absoluto del descuento global
  tax: () => number                   // IVA sobre el subtotal con descuento global
  total: () => number
  itemCount: () => number
}

/** Clave efectiva de un ítem del carrito */
const itemKey = (c: CartItem): string => c.cart_key ?? c.product_id

const LS_PRINTER_KEY = 'atlas_pos_printer'

/**
 * Selecciona el tier con el `unit_price` más bajo entre los `prices` del
 * producto. Ignora `min_quantity` por completo — la lógica de "Aplicar caja
 * a todo" fuerza el precio sin importar la cantidad agregada al carrito.
 *
 * Devuelve `null` si el producto no tiene tiers (sólo precio base).
 */
const pickCheapestTier = (prices?: CartItemPrice[] | null): CartItemPrice | null => {
  if (!prices || prices.length === 0) return null
  return prices.reduce((min, p) =>
    Number(p.unit_price) < Number(min.unit_price) ? p : min,
  )
}

export const usePOSStore = create<POSStore>((set, get) => ({
  cart: [],
  requiresInvoice: false,
  isProcessing: false,
  globalDiscount: 0,
  tip: 0,
  activeSession: null,
  customerName: null,
  customerId: null,
  parkedTickets: [],
  currentParkedId: null,
  printerName: localStorage.getItem(LS_PRINTER_KEY) ?? null,

  addItem: (item: CartItem) => {
    const key = item.cart_key ?? item.product_id
    // Ensure base_price is set so updateQty can restore the price when
    // quantity falls back below all tier thresholds.
    const itemWithBase: CartItem = item.base_price != null ? item : { ...item, base_price: item.price }
    const existing = get().cart.find((c: CartItem) => itemKey(c) === key)
    if (existing) {
      const newQty = existing.quantity + itemWithBase.quantity
      // Package items (vendido por caja) keep their box price fixed — never re-evaluate piece tiers.
      let effectivePrice = existing.price
      if (existing.unit_kind !== 'package') {
        effectivePrice = existing.base_price ?? existing.price
        if (existing.prices && existing.prices.length > 0) {
          const qualifying = existing.prices
            .filter((t) => t.min_quantity <= newQty)
            .sort((a, b) => b.min_quantity - a.min_quantity)
          if (qualifying.length > 0) effectivePrice = qualifying[0].unit_price
        }
      }
      set((s: POSStore) => ({
        cart: s.cart.map((c: CartItem) =>
          itemKey(c) === key
            ? { ...c, price: effectivePrice, quantity: newQty, subtotal: newQty * effectivePrice * (1 - c.discount / 100) }
            : c
        ),
      }))
    } else {
      set((s: POSStore) => ({ cart: [...s.cart, itemWithBase] }))
    }
  },

  updateQty: (cartKey: string, qty: number) => {
    if (qty <= 0) { get().removeItem(cartKey); return }
    set((s: POSStore) => ({
      cart: s.cart.map((c: CartItem) => {
        if (itemKey(c) !== cartKey) return c
        // priceForQty respeta lo que no debe recalcularse: el ítem vendido por
        // caja mantiene su precio de caja, y el precio pactado a mano por la
        // cajera (forcedPriceTier) sobrevive al cambio de cantidad. Antes solo
        // se exceptuaba unit_kind === 'package', así que subir la cantidad de
        // una línea con precio forzado la devolvía al escalón automático — y el
        // flag seguía puesto, de modo que nada la restauraba después.
        const effectivePrice = priceForQty(c, qty)
        return {
          ...c,
          price: effectivePrice,
          quantity: qty,
          subtotal: qty * effectivePrice * (1 - c.discount / 100),
        }
      }),
    }))
  },

  removeItem: (cartKey: string) =>
    set((s: POSStore) => ({ cart: s.cart.filter((c: CartItem) => itemKey(c) !== cartKey) })),

  setDiscount: (cartKey: string, discount: number) =>
    set((s: POSStore) => ({
      cart: s.cart.map((c: CartItem) =>
        itemKey(c) === cartKey
          ? { ...c, discount, subtotal: c.quantity * c.price * (1 - discount / 100) }
          : c
      ),
    })),

  setPrice: (cartKey: string, price: number) =>
    set((s: POSStore) => ({
      cart: s.cart.map((c: CartItem) =>
        itemKey(c) === cartKey
          ? { ...c, price, subtotal: c.quantity * price * (1 - c.discount / 100) }
          : c
      ),
    })),

  // Persiste el flag de tier forzado en el ítem mismo, no solo en el Map de
  // CartPanel. Sobrevive al park/resume porque se serializa en cart_json.
  setForcedTier: (cartKey: string, tier: string | null) =>
    set((s: POSStore) => ({
      cart: s.cart.map((c: CartItem) =>
        itemKey(c) === cartKey ? { ...c, forcedPriceTier: tier } : c
      ),
    })),

  replaceItem: (cartKey: string, newItem: CartItem) =>
    set((s: POSStore) => ({
      cart: s.cart.map((c: CartItem) => itemKey(c) === cartKey ? newItem : c),
    })),

  clearCart: () =>
    set({ cart: [], customerName: null, customerId: null, requiresInvoice: false, currentParkedId: null, globalDiscount: 0, tip: 0 }),

  applyCajaToAll: (sources: Map<string, ProductWithCajaInfo>) => {
    let applied = 0
    const cart = get().cart
    const total = cart.length
    const next: CartItem[] = cart.map((item) => {
      // Skip ::caja:: items already structured by toggleCaja — esa lógica vive aparte
      if (typeof item.cart_key === 'string' && item.cart_key.includes('::caja::')) {
        return item
      }
      const source = sources.get(item.product_id)
      if (!source) return item

      const prices = source.prices ?? item.prices
      const cheapest = pickCheapestTier(prices)
      // No hay tiers configurados → producto solo tiene precio base, no cuenta como aplicado
      if (!cheapest) return item

      const tierPrice = Number(cheapest.unit_price)
      const basePrice = item.base_price ?? Number(item.price)
      // Si el tier más barato no es estrictamente menor al base, no hay nada que aplicar
      // (caso edge: tiers mal configurados con precios > base)
      if (tierPrice >= basePrice) return item

      applied += 1
      return {
        ...item,
        // unit_kind queda en 'piece' — la lógica nueva no reestructura a paquete
        // quantity queda igual — no se cambia por bulk action
        // discount queda igual — preserva el descuento por línea
        base_price: item.base_price ?? Number(item.price),
        price: tierPrice,
        cajaForcedByBulk: true,
        subtotal: Number(item.quantity) * tierPrice * (1 - item.discount / 100),
        prices,
      }
    })
    set({ cart: next })
    return { applied, total }
  },

  restoreAutoTier: () => {
    set((s: POSStore) => ({
      cart: s.cart.map((item) => {
        if (!item.cajaForcedByBulk) return item
        // Bajo la lógica nueva, applyCajaToAll nunca cambia quantity ni unit_kind,
        // sólo el price. El restore solo necesita devolver el precio base y limpiar
        // el flag — el useEffect de auto-tier en CartPanel re-evalúa por qty si aplica.
        const restoredPrice = item.base_price ?? Number(item.price)
        return {
          ...item,
          cajaForcedByBulk: false,
          price: restoredPrice,
          subtotal: Number(item.quantity) * restoredPrice * (1 - item.discount / 100),
        }
      }),
    }))
  },

  setRequiresInvoice: (val: boolean) => set({ requiresInvoice: val }),
  setIsProcessing: (val: boolean) => set({ isProcessing: val }),
  setGlobalDiscount: (pct: number) => {
    const clamped = Math.max(0, Math.min(100, Number.isFinite(pct) ? pct : 0))
    set({ globalDiscount: clamped })
  },
  setTip: (amount: number) => set({ tip: Math.max(0, Number.isFinite(amount) ? amount : 0) }),
  setSession: (session: CashSession | null) => set({ activeSession: session }),
  setCustomer: (id: number | null, name: string | null) => set({ customerId: id, customerName: name }),
  setParkedTickets: (tickets: ParkedTicket[]) => set({ parkedTickets: tickets }),
  setCurrentParkedId: (id: string | null) => set({ currentParkedId: id }),
  setPrinterName: (name: string | null) => {
    if (name) localStorage.setItem(LS_PRINTER_KEY, name)
    else localStorage.removeItem(LS_PRINTER_KEY)
    set({ printerName: name })
  },

  subtotal: () => get().cart.reduce((acc: number, c: CartItem) => acc + c.subtotal, 0),
  discountedSubtotal: () => {
    const sub = get().cart.reduce((acc: number, c: CartItem) => acc + c.subtotal, 0)
    const gd = get().globalDiscount || 0
    return sub * (1 - gd / 100)
  },
  globalDiscountAmount: () => {
    const sub = get().cart.reduce((acc: number, c: CartItem) => acc + c.subtotal, 0)
    const gd = get().globalDiscount || 0
    return sub * (gd / 100)
  },
  tax: () => {
    if (!get().requiresInvoice) return 0
    const sub = get().cart.reduce((acc: number, c: CartItem) => acc + c.subtotal, 0)
    const gd = get().globalDiscount || 0
    return sub * (1 - gd / 100) * 0.16
  },
  total: () => {
    const sub = get().cart.reduce((acc: number, c: CartItem) => acc + c.subtotal, 0)
    const gd = get().globalDiscount || 0
    const discounted = sub * (1 - gd / 100)
    const goods = get().requiresInvoice ? discounted * 1.16 : discounted
    return goods + (get().tip || 0)
  },
  itemCount: () => get().cart.reduce((acc: number, c: CartItem) => acc + c.quantity, 0),
}))
