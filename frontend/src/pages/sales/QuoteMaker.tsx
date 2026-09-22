import { useState, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { productsApi } from '../../api/products'
import { customersApi, type Customer } from '../../api/customers'
import { quotesApi } from '../../api/quotes'
import { DaxCard } from '../../components/ui/DaxCard'
import type { Product } from '../../types/products'
import { formatCurrency } from '../../utils/currency'
import { toast } from '../../store/toastStore'

interface CartItem {
  product_id: string; sku: string; name: string
  price: number; quantity: number; discount: number; subtotal: number
}

export function QuoteMaker() {
  const navigate = useNavigate()
  const [productSearch, setProductSearch] = useState('')
  const [searchResults, setSearchResults] = useState<Product[]>([])
  const [cart, setCart] = useState<CartItem[]>([])
  const [customer, setCustomer] = useState<Customer | null>(null)
  const [customerSearch, setCustomerSearch] = useState('')
  const [customerResults, setCustomerResults] = useState<Customer[]>([])
  const [notes, setNotes] = useState('')
  const [saving, setSaving] = useState(false)
  const [showCustomerDrop, setShowCustomerDrop] = useState(false)
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const custTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const doProductSearch = useCallback(async (q: string) => {
    if (!q.trim()) { setSearchResults([]); return }
    try {
      const res = await productsApi.search(q, 0, 10)
      // Backend ya filtra por visibilidad (active + active_in_branch) — no duplicar aquí.
      setSearchResults(res.items ?? [])
    } catch { setSearchResults([]) }
  }, [])

  const doCustSearch = useCallback(async (q: string) => {
    if (!q.trim()) { setCustomerResults([]); return }
    try {
      const data = await customersApi.search(q, 8)
      setCustomerResults(data)
      setShowCustomerDrop(true)
    } catch { setCustomerResults([]) }
  }, [])

  const addToCart = (p: Product) => {
    setCart((prev) => {
      const existing = prev.find((i) => i.product_id === p.id)
      if (existing) return prev.map((i) => i.product_id === p.id
        ? { ...i, quantity: i.quantity + 1, subtotal: (i.quantity + 1) * i.price * (1 - i.discount / 100) }
        : i
      )
      return [...prev, { product_id: p.id, sku: p.sku, name: p.name, price: p.price, quantity: 1, discount: 0, subtotal: p.price }]
    })
    setProductSearch(''); setSearchResults([])
  }

  const updateQty = (product_id: string, qty: number) => {
    if (qty <= 0) { removeItem(product_id); return }
    setCart((prev) => prev.map((i) => i.product_id === product_id
      ? { ...i, quantity: qty, subtotal: qty * i.price * (1 - i.discount / 100) } : i
    ))
  }

  const updateDiscount = (product_id: string, disc: number) => {
    setCart((prev) => prev.map((i) => i.product_id === product_id
      ? { ...i, discount: disc, subtotal: i.quantity * i.price * (1 - disc / 100) } : i
    ))
  }

  const removeItem = (product_id: string) => setCart((prev) => prev.filter((i) => i.product_id !== product_id))

  const subtotal = cart.reduce((s, i) => s + i.subtotal, 0)
  const total = subtotal

  const handleSave = async () => {
    if (cart.length === 0) return
    setSaving(true)
    try {
      const res = await quotesApi.create({
        doc_type: 'QUOTE',
        customer_id: customer?.id ?? null,
        items: cart.map((i) => ({ sku: i.sku, quantity: i.quantity, discount: i.discount || 0 })),
        payments: [],
        notes: notes.trim() || null,
      })
      toast.success(`Cotización creada: ${res.folio}`)
      navigate('/quotes')
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
      toast.error(typeof detail === 'string' && detail.trim() ? detail : 'No se pudo crear la cotización')
    } finally { setSaving(false) }
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <i className="fa-solid fa-file-invoice-dollar text-indigo-400 text-xl" />
          <h1 className="text-2xl font-black text-white">Nueva cotización</h1>
        </div>
        <button onClick={() => navigate('/quotes')} className="dax-btn-secondary text-xs">
          <i className="fa-solid fa-arrow-left" /> Volver
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Búsqueda de productos */}
        <div className="lg:col-span-2 space-y-3">
          <DaxCard>
            <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-3">Buscar Producto</p>
            <div className="relative">
              <input
                type="text" placeholder="Nombre, SKU o código..."
                value={productSearch}
                onChange={(e) => {
                  setProductSearch(e.target.value)
                  if (searchTimer.current) clearTimeout(searchTimer.current)
                  searchTimer.current = setTimeout(() => doProductSearch(e.target.value), 300)
                }}
                className="dax-input w-full"
                autoFocus />
              {searchResults.length > 0 && (
                <div className="absolute z-30 top-full left-0 right-0 mt-1 bg-slate-800 border border-slate-700 rounded-lg shadow-xl overflow-hidden">
                  {searchResults.map((p) => (
                    <button key={p.id} onClick={() => addToCart(p)}
                      className="w-full flex items-center justify-between px-3 py-2 hover:bg-slate-700/60 transition-colors text-left">
                      <div>
                        <p className="text-sm font-semibold text-white">{p.name}</p>
                        <p className="text-[10px] text-slate-500 font-mono">{p.sku}</p>
                      </div>
                      <div className="text-right">
                        <p className="text-emerald-400 font-bold text-sm">{formatCurrency(p.price ?? 0)}</p>
                        <p className="text-xs text-slate-500">Stock: {p.stock_total ?? 0}</p>
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </DaxCard>

          {/* Carrito */}
          <DaxCard padding={false}>
            {cart.length === 0 ? (
              <div className="p-12 text-center text-slate-600">
                <i className="fa-solid fa-cart-shopping text-3xl mb-3 block" />
                Sin artículos agregados
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="dax-table w-full">
                  <thead>
                    <tr>
                      <th>Producto</th>
                      <th className="text-right">Precio</th>
                      <th className="text-center">Cant.</th>
                      <th className="text-center">Desc.%</th>
                      <th className="text-right">Subtotal</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {cart.map((item) => (
                      <tr key={item.product_id}>
                        <td>
                          <p className="text-white font-semibold text-sm">{item.name}</p>
                          <p className="text-[10px] font-mono text-slate-500">{item.sku}</p>
                        </td>
                        <td className="text-right text-slate-300 tabular-nums">{formatCurrency(item.price)}</td>
                        <td className="text-center">
                          <div className="flex items-center justify-center gap-1">
                            <button onClick={() => updateQty(item.product_id, item.quantity - 1)} className="w-6 h-6 bg-slate-700 rounded text-xs hover:bg-slate-600">-</button>
                            <span className="w-8 text-center font-bold">{item.quantity}</span>
                            <button onClick={() => updateQty(item.product_id, item.quantity + 1)} className="w-6 h-6 bg-slate-700 rounded text-xs hover:bg-slate-600">+</button>
                          </div>
                        </td>
                        <td className="text-center">
                          <input type="number" min="0" max="100" value={item.discount}
                            onChange={(e) => updateDiscount(item.product_id, Math.min(100, Math.max(0, parseFloat(e.target.value) || 0)))}
                            className="w-16 dax-input text-center text-xs" />
                        </td>
                        <td className="text-right font-bold text-emerald-400 tabular-nums">{formatCurrency(item.subtotal)}</td>
                        <td>
                          <button onClick={() => removeItem(item.product_id)} className="text-slate-600 hover:text-red-400 text-xs">
                            <i className="fa-solid fa-xmark" />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </DaxCard>
        </div>

        {/* Panel derecho */}
        <div className="space-y-3">
          {/* Cliente */}
          <DaxCard>
            <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-3">Cliente</p>
            {customer ? (
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-semibold text-white">{customer.name}</p>
                  <p className="text-xs text-slate-500">{customer.phone ?? '—'}</p>
                </div>
                <button onClick={() => { setCustomer(null); setCustomerSearch('') }} className="text-slate-500 hover:text-red-400 text-xs">
                  <i className="fa-solid fa-xmark" />
                </button>
              </div>
            ) : (
              <div className="relative">
                <input type="text" placeholder="Buscar cliente..."
                  value={customerSearch}
                  onChange={(e) => {
                    setCustomerSearch(e.target.value)
                    if (custTimer.current) clearTimeout(custTimer.current)
                    custTimer.current = setTimeout(() => doCustSearch(e.target.value), 300)
                  }}
                  className="dax-input w-full text-sm" />
                {showCustomerDrop && customerResults.length > 0 && (
                  <div className="absolute z-30 top-full left-0 right-0 mt-1 bg-slate-800 border border-slate-700 rounded-lg shadow-xl overflow-hidden">
                    {customerResults.map((c) => (
                      <button key={c.id} onClick={() => { setCustomer(c); setCustomerSearch(''); setCustomerResults([]); setShowCustomerDrop(false) }}
                        className="w-full px-3 py-2 hover:bg-slate-700/60 text-left text-sm">
                        <p className="text-white font-semibold">{c.name}</p>
                        <p className="text-slate-500 text-xs">{c.phone ?? '—'}</p>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
          </DaxCard>

          {/* Notas */}
          <DaxCard>
            <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2">Notas</p>
            <textarea value={notes} onChange={(e) => setNotes(e.target.value)}
              rows={3} className="dax-input w-full text-sm resize-none" placeholder="Condiciones, validez, observaciones..." />
          </DaxCard>

          {/* Resumen */}
          <DaxCard>
            <div className="space-y-2 text-sm mb-4">
              <div className="flex justify-between text-slate-400">
                <span>Subtotal</span>
                <span className="tabular-nums">{formatCurrency(subtotal)}</span>
              </div>
              <div className="flex justify-between font-black text-white text-lg border-t border-slate-700/50 pt-2">
                <span>Total</span>
                <span className="tabular-nums text-emerald-400">{formatCurrency(total)}</span>
              </div>
            </div>
            <button
              onClick={handleSave}
              disabled={saving || cart.length === 0}
              className="dax-btn-primary w-full justify-center text-sm disabled:opacity-40">
              {saving ? <i className="fa-solid fa-spinner fa-spin" /> : <><i className="fa-solid fa-file-invoice" /> Crear Cotización</>}
            </button>
          </DaxCard>
        </div>
      </div>
    </div>
  )
}
