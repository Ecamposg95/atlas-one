import { useState, useCallback } from 'react'
import { useLocation } from 'react-router-dom'
import { productsApi } from '../../api/products'
import { inventoryApi } from '../../api/inventory'
import { organizationApi, type Branch } from '../../api/organization'
import { DaxCard } from '../../components/ui/DaxCard'
import { Modal } from '../../components/ui/Modal'
import { useAuthStore } from '../../store/authStore'
import { Spinner } from '../../components/ui/Spinner'
import { useEsTelefono } from '../../hooks/useIsMobile'
import { CabeceraPagina } from '../../components/ui/CabeceraPagina'
import { ListaTarjetas } from '../../components/ui/ListaTarjetas'
import { TarjetaFila } from '../../components/ui/TarjetaFila'
import { toast } from '../../store/toastStore'
import { errorDetailText } from '../../utils/errorDetail'
import { tipoMovimiento } from '../../utils/enumsEspanol'
import type { Product } from '../../types/products'
import { useEffect } from 'react'
import { formatCurrency } from '../../utils/currency'
import { expandVariantRows, initialInventoryQuery, type InventoryRow } from '../inventory/variantRows'

const ADMIN_ROLES = new Set(['ADMINISTRADOR', 'DUEÑO'])
const sinCosto = (r: InventoryRow) => !(Number(r.variant.cost) > 0)

export function HQInventory() {
  const location = useLocation()
  const esTelefono = useEsTelefono()
  // SP6: costo e importe a costo solo para quien ve costos (misma regla que la valuación).
  const veCosto = ADMIN_ROLES.has(useAuthStore((s) => s.user?.role ?? ''))
  const [soloSinCosto, setSoloSinCosto] = useState(false)
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
  // "Solo sin costo" filtra lo buscado (máx. 30 productos): es para corregir mientras se busca; el
  // conteo completo de piezas sin costo vive en Valor de la tienda.
  const todas = expandVariantRows(products)
  const rows = soloSinCosto ? todas.filter(sinCosto) : todas
  const importeVenta = (r: InventoryRow) => r.qty * Number(r.variant.price ?? 0)
  const importeCosto = (r: InventoryRow) => r.qty * Number(r.variant.cost ?? 0)
  const totales = rows.reduce(
    (t, r) => ({ piezas: t.piezas + r.qty, venta: t.venta + importeVenta(r), costo: t.costo + importeCosto(r) }),
    { piezas: 0, venta: 0, costo: 0 },
  )

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
      <CabeceraPagina
        titulo={
          <div className="flex items-center gap-3">
            <i className="fa-solid fa-globe text-indigo-400 text-xl" />
            <h1 className="text-2xl font-black text-white">Existencias</h1>
          </div>
        }
      />

      <div className="flex flex-wrap gap-2 items-center">
        <input
          type="text" placeholder="Buscar producto por nombre o SKU..."
          value={search}
          onChange={(e) => { setSearch(e.target.value); doSearch(e.target.value) }}
          className="dax-input flex-1 min-w-[12rem] text-sm" />
        <label className="flex items-center gap-2 text-xs text-slate-300 max-md:min-h-[44px] cursor-pointer">
          <input type="checkbox" checked={soloSinCosto} onChange={(e) => setSoloSinCosto(e.target.checked)} />
          Solo sin costo
        </label>
      </div>

      {loading && <Spinner text="Buscando..." />}

      {rows.length > 0 && !selected && (
        <DaxCard padding={false}>
          {esTelefono ? (
            <ListaTarjetas className="p-3">
              {rows.map((row) => (
                <TarjetaFila key={row.variant.id}
                  titulo={row.label}
                  subtitulo={<span className="font-mono text-indigo-400">{row.sku}</span>}
                  importe={formatCurrency(importeVenta(row))}
                  estado={<span className={`font-bold tabular-nums ${row.qty <= 0 ? 'text-red-400' : 'text-emerald-400'}`}>{row.qty} en stock</span>}
                  datos={[
                    { etiqueta: 'Precio', valor: formatCurrency(row.variant.price ?? 0) },
                    ...(veCosto ? [
                      { etiqueta: 'Costo', valor: sinCosto(row) ? <span className="text-amber-400">sin costo</span> : formatCurrency(row.variant.cost ?? 0) },
                      { etiqueta: 'A costo', valor: formatCurrency(importeCosto(row)) },
                    ] : []),
                  ]}
                  acciones={<button onClick={() => openDetail(row)} className="dax-btn-secondary text-xs"><i className="fa-solid fa-chart-line" /> Kardex</button>}
                />
              ))}
            </ListaTarjetas>
          ) : (
          <div className="overflow-x-auto">
            <table className="dax-table w-full">
              <thead>
                <tr>
                  <th>SKU</th>
                  <th>Producto</th>
                  <th className="text-right">Precio</th>
                  {veCosto && <th className="text-right">Costo</th>}
                  <th className="text-right">Stock</th>
                  <th className="text-right">Importe venta</th>
                  {veCosto && <th className="text-right">Importe costo</th>}
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
                    {veCosto && (
                      <td className="text-right text-slate-300">
                        {sinCosto(row) ? <span className="text-amber-400 text-xs font-bold">sin costo</span> : formatCurrency(row.variant.cost ?? 0)}
                      </td>
                    )}
                    <td className={`text-right font-bold ${row.qty <= 0 ? 'text-red-400' : 'text-emerald-400'}`}>
                      {row.qty}
                    </td>
                    <td className="text-right text-slate-300 tabular-nums">{formatCurrency(importeVenta(row))}</td>
                    {veCosto && <td className="text-right text-slate-300 tabular-nums">{formatCurrency(importeCosto(row))}</td>}
                    <td>
                      <button onClick={() => openDetail(row)} className="dax-btn-secondary text-xs">
                        <i className="fa-solid fa-chart-line" /> Kardex
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="font-bold text-white" data-testid="totales">
                  <td colSpan={veCosto ? 4 : 3}>Total de lo listado</td>
                  <td className="text-right tabular-nums">{totales.piezas}</td>
                  <td className="text-right tabular-nums">{formatCurrency(totales.venta)}</td>
                  {veCosto && <td className="text-right tabular-nums">{formatCurrency(totales.costo)}</td>}
                  <td></td>
                </tr>
              </tfoot>
            </table>
          </div>
          )}
        </DaxCard>
      )}

      {selected && (
        <div className="space-y-3">
          <div className="flex max-md:flex-wrap items-center max-md:items-start justify-between gap-2">
            <div>
              <p className="text-[10px] text-slate-500 uppercase tracking-widest">Kardex</p>
              <p className="text-lg font-black text-white">{selected.label}</p>
              <p className="text-xs font-mono text-indigo-400">{selected.sku}</p>
            </div>
            <div className="flex max-md:flex-wrap gap-2 max-md:[&>button]:min-h-[44px]">
              <button onClick={() => setAdjustModal(true)} className="dax-btn-secondary text-xs">
                <i className="fa-solid fa-sliders" /> Ajustar
              </button>
              <button onClick={() => { setSelected(null); setKardex([]) }} className="dax-btn-secondary text-xs">
                <i className="fa-solid fa-xmark" /> Cerrar
              </button>
            </div>
          </div>

          <DaxCard padding={false}>
            {esTelefono ? (
              <ListaTarjetas cargando={kardexLoading} vacio={kardex.length === 0} textoVacio="Sin movimientos registrados" className="p-3">
              {kardex.map((k) => (
                <TarjetaFila key={k.id}
                  titulo={new Date(k.created_at).toLocaleDateString('es-MX', { day: '2-digit', month: 'short' })}
                  subtitulo={<span className={`dax-badge ${movementColor(k.movement_type)}`}>{tipoMovimiento(k.movement_type)}</span>}
                  importe={<span className={movementColor(k.movement_type)}>{k.qty_change > 0 ? '+' : ''}{k.qty_change}</span>}
                  datos={[
                    { etiqueta: 'Saldo', valor: k.qty_after },
                    { etiqueta: 'Ref.', valor: <span className="font-mono">{k.reference ?? '—'}</span> },
                  ]}
                />
              ))}
            </ListaTarjetas>
            ) : (
              kardexLoading ? <Spinner text="Cargando kardex..." /> : kardex.length === 0 ? (
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
                            <span className={`dax-badge ${movementColor(k.movement_type)}`}>{tipoMovimiento(k.movement_type)}</span>
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
              )
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

      {/* Ajuste de existencia: Modal del kit. */}
      {adjustModal && selected && (
        <Modal
          open
          onClose={() => setAdjustModal(false)}
          size="sm"
          title="Ajuste de inventario"
          footer={
            <>
              <button onClick={() => setAdjustModal(false)} className="dax-btn-secondary flex-1">Cancelar</button>
              <button onClick={handleAdjust} disabled={adjSaving || !adjQty || !adjReason || !adjBranch} className="dax-btn-primary flex-1 justify-center disabled:opacity-40">
                {adjSaving ? <i className="fa-solid fa-spinner fa-spin" /> : <><i className="fa-solid fa-check" /> Ajustar</>}
              </button>
            </>
          }
        >
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
        </Modal>
      )}
    </div>
  )
}
