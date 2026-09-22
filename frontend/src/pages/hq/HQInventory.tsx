import { useState, useCallback } from 'react'
import { useLocation } from 'react-router-dom'
import { productsApi } from '../../api/products'
import { inventoryApi } from '../../api/inventory'
import { organizationApi, type Branch } from '../../api/organization'
import { DaxCard } from '../../components/ui/DaxCard'
import { Spinner } from '../../components/ui/Spinner'
import { toast } from '../../store/toastStore'
import { errorDetailText } from '../../utils/errorDetail'
import type { Product } from '../../types/products'
import { useEffect } from 'react'
import { formatCurrency } from '../../utils/currency'
import { expandVariantRows, initialInventoryQuery, type InventoryRow } from '../inventory/variantRows'

export function HQInventory() {
  const location = useLocation()
  const [search, setSearch] = useState('')
  const [products, setProducts] = useState<Product[]>([])
  const [branches, setBranches] = useState<Branch[]>([])
  const [loading, setLoading] = useState(false)
  const [selected, setSelected] = useState<InventoryRow | null>(null)
  const [kardex, setKardex] = useState<Awaited<ReturnType<typeof inventoryApi.getKardex>>>([])
  const [kardexLoading, setKardexLoading] = useState(false)
  const [adjustModal, setAdjustModal] = useState(false)
  const [adjQty, setAdjQty] = useState('')
  const [adjReason, setAdjReason] = useState('')
  const [adjBranch, setAdjBranch] = useState('')
  const [adjSaving, setAdjSaving] = useState(false)

  useEffect(() => {
    organizationApi.getBranches().then(setBranches).catch(() => {})
  }, [])

  const doSearch = useCallback(async (q: string): Promise<Product[]> => {
    if (!q.trim()) { setProducts([]); return [] }
    setLoading(true)
    try {
      const res = await productsApi.search(q, 0, 30)
      const items = res.items ?? []
      setProducts(items)
      return items
    } catch { setProducts([]); return [] } finally { setLoading(false) }
  }, [])

  // Un renglón por variante — con varias tallas, kardex y ajuste van a la que se eligió, no a la primera.
  const rows = expandVariantRows(products)

  const openDetail = async (row: InventoryRow) => {
    setSelected(row)
    setKardexLoading(true)
    try {
      const data = await inventoryApi.getKardex(row.variant.id)
      setKardex(data)
    } catch { setKardex([]) } finally { setKardexLoading(false) }
  }

  // Entrada con ?variant=<id>&q=<sku> (el "Ajustar" del editor de variantes, o
  // un enlace pegado): se siembra el buscador y se abre el kardex de ESA talla.
  // Solo al montar; de ahí en adelante manda lo que el usuario teclee.
  useEffect(() => {
    const { q, variant } = initialInventoryQuery(location.search)
    if (!q && !variant) return
    setSearch(q)
    doSearch(q).then((items) => {
      if (!variant) return
      const fila = expandVariantRows(items).find((r) => r.variant.id === variant)
      if (fila) openDetail(fila)
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleAdjust = async () => {
    if (!selected || !adjQty || !adjReason || !adjBranch) return
    setAdjSaving(true)
    try {
      await inventoryApi.createAdjustment({
        variant_id: selected.variant.id,
        quantity: parseInt(adjQty),
        branch_id: Number(adjBranch),
        reason: adjReason,
      })
      setAdjustModal(false); setAdjQty(''); setAdjReason(''); setAdjBranch('')
      // Recargar la tabla: sin esto la existencia del renglon seguia mostrando
      // la de antes del ajuste hasta que el usuario volvia a buscar.
      const frescos = await doSearch(search)
      const actualizado = expandVariantRows(frescos).find((r) => r.variant.id === selected.variant.id)
      if (actualizado) setSelected(actualizado)
      const data = await inventoryApi.getKardex(selected.variant.id)
      setKardex(data)
    } catch (e: any) {
      toast.error(errorDetailText(
        e?.response?.data?.detail,
        'No se pudo ajustar la existencia. No se guardó nada: revisa la cantidad y el motivo, y vuelve a intentar.',
      ))
    } finally { setAdjSaving(false) }
  }

  const movementColor = (type: string) =>
    type.includes('IN') || type === 'ADJUSTMENT_IN' ? 'text-emerald-400' : 'text-red-400'

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <i className="fa-solid fa-globe text-indigo-400 text-xl" />
        <h1 className="text-2xl font-black text-white">Existencias</h1>
      </div>

      <div className="flex gap-2">
        <input
          type="text" placeholder="Buscar producto por nombre o SKU..."
          value={search}
          onChange={(e) => { setSearch(e.target.value); doSearch(e.target.value) }}
          className="dax-input flex-1 text-sm" />
      </div>

      {loading && <Spinner text="Buscando..." />}

      {rows.length > 0 && !selected && (
        <DaxCard padding={false}>
          <div className="overflow-x-auto">
            <table className="dax-table w-full">
              <thead>
                <tr>
                  <th>SKU</th>
                  <th>Producto</th>
                  <th className="text-right">Precio</th>
                  <th className="text-right">Stock</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.variant.id}>
                    <td className="font-mono text-indigo-400 text-xs">{row.sku}</td>
                    <td className="text-white font-semibold">{row.label}</td>
                    {/* Precio de ESTA talla: `product.price` es el aplanado de la principal. */}
                    <td className="text-right text-slate-300">{formatCurrency(row.variant.price ?? 0)}</td>
                    <td className={`text-right font-bold ${row.qty <= 0 ? 'text-red-400' : 'text-emerald-400'}`}>
                      {row.qty}
                    </td>
                    <td>
                      <button onClick={() => openDetail(row)} className="dax-btn-secondary text-xs">
                        <i className="fa-solid fa-chart-line" /> Kardex
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </DaxCard>
      )}

      {selected && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-[10px] text-slate-500 uppercase tracking-widest">Kardex</p>
              <p className="text-lg font-black text-white">{selected.label}</p>
              <p className="text-xs font-mono text-indigo-400">{selected.sku}</p>
            </div>
            <div className="flex gap-2">
              <button onClick={() => setAdjustModal(true)} className="dax-btn-secondary text-xs">
                <i className="fa-solid fa-sliders" /> Ajustar
              </button>
              <button onClick={() => { setSelected(null); setKardex([]) }} className="dax-btn-secondary text-xs">
                <i className="fa-solid fa-xmark" /> Cerrar
              </button>
            </div>
          </div>

          <DaxCard padding={false}>
            {kardexLoading ? <Spinner text="Cargando kardex..." /> : kardex.length === 0 ? (
              <div className="p-12 text-center text-slate-600">Sin movimientos registrados</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="dax-table w-full">
                  <thead>
                    <tr>
                      <th>Fecha</th>
                      <th>Tipo</th>
                      <th className="text-right">Cantidad</th>
                      <th className="text-right">Saldo</th>
                      <th>Referencia</th>
                    </tr>
                  </thead>
                  <tbody>
                    {kardex.map((k) => (
                      <tr key={k.id}>
                        <td className="text-xs text-slate-400">
                          {new Date(k.created_at).toLocaleDateString('es-MX', { day: '2-digit', month: 'short' })}
                        </td>
                        <td className="text-xs">
                          <span className={`dax-badge ${movementColor(k.movement_type)}`}>{k.movement_type}</span>
                        </td>
                        <td className={`text-right font-bold tabular-nums ${movementColor(k.movement_type)}`}>
                          {k.qty_change > 0 ? '+' : ''}{k.qty_change}
                        </td>
                        <td className="text-right text-slate-400 text-xs tabular-nums">{k.qty_after}</td>
                        <td className="text-slate-500 text-xs font-mono">{k.reference ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </DaxCard>
        </div>
      )}

      {!loading && !selected && products.length === 0 && search && (
        <DaxCard><div className="p-12 text-center text-slate-600">Sin resultados para "{search}"</div></DaxCard>
      )}

      {!search && !selected && (
        <DaxCard><div className="p-12 text-center text-slate-600">Busca un producto para ver su kardex</div></DaxCard>
      )}

      {/* Modal ajuste */}
      {adjustModal && selected && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm" onClick={() => setAdjustModal(false)}>
          <div className="dax-card dax-modal p-6 w-full max-w-sm" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-black text-white">Ajuste de Inventario</h3>
              <button onClick={() => setAdjustModal(false)} className="dax-btn-icon text-slate-500 hover:text-white"><i className="fa-solid fa-xmark text-lg" /></button>
            </div>
            <p className="text-slate-400 text-sm mb-4">{selected.label}</p>
            <div className="space-y-3">
              <div>
                <label className="dax-label">Sucursal</label>
                <select value={adjBranch} onChange={(e) => setAdjBranch(e.target.value)} className="dax-input w-full">
                  <option value="">Seleccionar...</option>
                  {branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
                </select>
              </div>
              <div>
                <label className="dax-label">Cantidad (+ agregar / - restar)</label>
                <input type="number" value={adjQty} onChange={(e) => setAdjQty(e.target.value)}
                  placeholder="+10 o -5" className="dax-input w-full text-lg font-bold" autoFocus />
              </div>
              <div>
                <label className="dax-label">Motivo</label>
                <input value={adjReason} onChange={(e) => setAdjReason(e.target.value)}
                  placeholder="Conteo físico, merma, etc." className="dax-input w-full" />
              </div>
            </div>
            <div className="dax-modal-footer -mx-6 px-6 flex gap-2 mt-4">
              <button onClick={() => setAdjustModal(false)} className="dax-btn-secondary flex-1">Cancelar</button>
              <button onClick={handleAdjust} disabled={adjSaving || !adjQty || !adjReason || !adjBranch} className="dax-btn-primary flex-1 justify-center disabled:opacity-40">
                {adjSaving ? <i className="fa-solid fa-spinner fa-spin" /> : <><i className="fa-solid fa-check" /> Ajustar</>}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
