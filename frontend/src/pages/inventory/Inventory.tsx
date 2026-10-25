// frontend/src/pages/inventory/Inventory.tsx
import { useState, useCallback, useEffect, useRef } from 'react'
import { useLocation } from 'react-router-dom'
import { productsApi } from '../../api/products'
import { inventoryApi } from '../../api/inventory'
import { organizationApi, type Branch } from '../../api/organization'
import { useAuthStore } from '../../store/authStore'
import { DaxCard } from '../../components/ui/DaxCard'
import { Modal } from '../../components/ui/Modal'
import { TablaDesplazable } from '../../components/ui/TablaDesplazable'
import { Spinner } from '../../components/ui/Spinner'
import { useEsTelefono } from '../../hooks/useIsMobile'
import { CabeceraPagina } from '../../components/ui/CabeceraPagina'
import { ListaTarjetas } from '../../components/ui/ListaTarjetas'
import { TarjetaFila } from '../../components/ui/TarjetaFila'
import { toast } from '../../store/toastStore'
import { errorDetailText } from '../../utils/errorDetail'
import { tipoMovimiento } from '../../utils/enumsEspanol'
import { esRolHq } from '../../utils/rolesHq'
import type { Product } from '../../types/products'
import { formatCurrency } from '../../utils/currency'
import { expandVariantRows, initialInventoryQuery, type InventoryRow } from './variantRows'

/**
 * Inventario (`/inventory`): buscar → un renglón por variante con precio,
 * existencia e importe a venta; kardex y ajuste por sucursal. Para los roles
 * de oficina (Fase 3 del admin, spec 2026-10-23 §4.1) suma costo, importe a
 * costo, totales y la casilla "Solo sin costo" que vivían en `hq/HQInventory`
 * (borrada). Acepta `?q=&variant=` (el "Ajustar" del editor de variantes y los
 * enlaces del Inicio). Solo tokens `dax-*` (coloresPorTokens, LIMPIOS).
 */

const sinCosto = (r: InventoryRow) => !(Number(r.variant.cost) > 0)
const fechaCorta = (iso: string) => new Date(iso).toLocaleDateString('es-MX', { day: '2-digit', month: 'short' })
const colorMovimiento = (type: string) =>
  type.includes('IN') || type === 'ADJUSTMENT_IN' ? 'text-dax-success' : 'text-dax-danger'
const colorExistencia = (qty: number) => (qty <= 0 ? 'text-dax-danger' : 'text-dax-success')

export function Inventory() {
  const location = useLocation()
  const esTelefono = useEsTelefono()
  // Costo e importe a costo solo para quien ve costos (misma regla que la valuación: ADMIN/DUEÑO).
  const veCosto = esRolHq(useAuthStore((s) => s.user?.role))
  const usuarioBranchId = useAuthStore((s) => s.user?.branch_id) ?? null
  const usuarioBranchName = useAuthStore((s) => s.user?.branch_name) ?? null
  const sucursalActivaId = useAuthStore((s) => s.branch?.id) ?? null
  // Sucursal del kardex: el rol de oficina mira la activa (o la suya); el resto, siempre la suya.
  // Un admin sin sucursal propia vería un kardex vacío si no se pidiera una explícita.
  const sucursalKardex = (veCosto ? sucursalActivaId ?? usuarioBranchId : usuarioBranchId) ?? undefined
  const [soloSinCosto, setSoloSinCosto] = useState(false)
  const [search, setSearch] = useState('')
  const [products, setProducts] = useState<Product[]>([])
  const [branches, setBranches] = useState<Branch[]>([])
  const [loading, setLoading] = useState(false)
  const [errorBusqueda, setErrorBusqueda] = useState<string | null>(null)
  // Contador de peticiones: una respuesta vieja (otra búsqueda) no pisa a la nueva.
  const reqId = useRef(0)
  const [selected, setSelected] = useState<InventoryRow | null>(null)
  const [kardex, setKardex] = useState<Awaited<ReturnType<typeof inventoryApi.getKardex>>>([])
  const [kardexLoading, setKardexLoading] = useState(false)
  const [adjustModal, setAdjustModal] = useState(false)
  const [adjQty, setAdjQty] = useState('')
  const [adjReason, setAdjReason] = useState('')
  const [adjBranch, setAdjBranch] = useState('')
  const [adjSaving, setAdjSaving] = useState(false)
  // Debounce del buscador: una petición por pausa al teclear, no una por letra.
  const debounceBusqueda = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => () => { if (debounceBusqueda.current) clearTimeout(debounceBusqueda.current) }, [])
  const alTeclear = (valor: string) => {
    setSearch(valor)
    if (debounceBusqueda.current) clearTimeout(debounceBusqueda.current)
    // Borrar el texto limpia al instante (y descarta lo que venía en camino).
    if (!valor.trim()) { doSearch(valor); return }
    debounceBusqueda.current = setTimeout(() => doSearch(valor), 300)
  }

  // Todas las sucursales (también las que no venden): el ajuste puede ir a una bodega.
  useEffect(() => {
    organizationApi.getBranches().then(setBranches).catch(() => {})
  }, [])

  const doSearch = useCallback(async (q: string): Promise<Product[]> => {
    const mio = ++reqId.current
    setErrorBusqueda(null)
    if (!q.trim()) { setProducts([]); setLoading(false); return [] }
    setLoading(true)
    try {
      const res = await productsApi.search(q, 0, 30)
      const items = res.items ?? []
      if (mio !== reqId.current) return []
      setProducts(items)
      return items
    } catch (e: unknown) {
      if (mio !== reqId.current) return []
      // Un fallo no se disfraza de "Sin resultados".
      setProducts([])
      setErrorBusqueda(errorDetailText(
        (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail,
        'No se pudo buscar en el inventario. Vuelve a intentar en unos segundos.',
      ))
      return []
    } finally {
      if (mio === reqId.current) setLoading(false)
    }
  }, [])

  // Un renglón por variante — con varias tallas, kardex y ajuste van a la que se eligió, no a la primera.
  // "Solo sin costo" filtra lo buscado (máx. 30 productos): es para corregir mientras se busca; el
  // conteo completo de piezas sin costo vive en Valor de la tienda.
  const todas = expandVariantRows(products)
  const rows = veCosto && soloSinCosto ? todas.filter(sinCosto) : todas
  const importeVenta = (r: InventoryRow) => r.qty * Number(r.variant.price ?? 0)
  const importeCosto = (r: InventoryRow) => r.qty * Number(r.variant.cost ?? 0)
  const totales = rows.reduce(
    (t, r) => ({ piezas: t.piezas + r.qty, venta: t.venta + importeVenta(r), costo: t.costo + importeCosto(r) }),
    { piezas: 0, venta: 0, costo: 0 },
  )

  // Contador propio del kardex: abrir otra talla (o cerrar) deja sin efecto al kardex que venía en camino.
  const kardexReq = useRef(0)
  const openDetail = async (row: InventoryRow) => {
    const mio = ++kardexReq.current
    setSelected(row)
    setKardexLoading(true)
    try {
      const movimientos = await inventoryApi.getKardex(row.variant.id, sucursalKardex)
      if (mio === kardexReq.current) setKardex(movimientos)
    } catch { if (mio === kardexReq.current) setKardex([]) }
    finally { if (mio === kardexReq.current) setKardexLoading(false) }
  }

  // Entrada con ?variant=<id>&q=<sku> (el "Ajustar" del editor de variantes, el Inicio
  // o un enlace pegado): se siembra el buscador y se abre el kardex de ESA talla.
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

  // El backend fuerza la sucursal del usuario a quien no es ADMIN/DUEÑO (inventory.py, /adjust):
  // el select de esos roles queda fijo en la suya en vez de ofrecer una que se ignoraría.
  const sucursalAjuste = veCosto ? adjBranch : usuarioBranchId ? String(usuarioBranchId) : ''

  const handleAdjust = async () => {
    if (!selected || !adjQty || !adjReason || !sucursalAjuste) return
    setAdjSaving(true)
    const variantId = selected.variant.id
    const sucursalId = Number(sucursalAjuste)
    // El `try` cierra justo tras el POST: lo de después ya no puede decir "no se guardó nada".
    try {
      await inventoryApi.createAdjustment({
        variant_id: variantId,
        quantity: parseInt(adjQty),
        branch_id: sucursalId,
        reason: adjReason,
      })
    } catch (e: unknown) {
      toast.error(errorDetailText(
        (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail,
        'No se pudo ajustar la existencia. No se guardó nada: revisa la cantidad y el motivo, y vuelve a intentar.',
      ))
      setAdjSaving(false)
      return
    }
    toast.success('Ajuste guardado')
    setAdjustModal(false); setAdjQty(''); setAdjReason(''); setAdjBranch('')
    try {
      // Recargar la tabla: sin esto la existencia del renglón seguía mostrando
      // la de antes del ajuste hasta que el usuario volvía a buscar.
      const frescos = await doSearch(search)
      const actualizado = expandVariantRows(frescos).find((r) => r.variant.id === variantId)
      if (actualizado) setSelected(actualizado)
      // El kardex de la sucursal AJUSTADA (no la del usuario, que puede ser otra).
      setKardex(await inventoryApi.getKardex(variantId, sucursalId))
    } catch {
      toast.warning('Ajuste guardado; no se pudo refrescar el kardex')
    } finally { setAdjSaving(false) }
  }

  return (
    <div className="space-y-5">
      <CabeceraPagina
        titulo={
          <div className="flex items-center gap-3">
            <i className="fa-solid fa-boxes text-dax-accent-text text-xl" aria-hidden="true" />
            <h1 className="text-2xl font-black text-dax-text">Inventario</h1>
          </div>
        }
      />

      <div className="flex flex-wrap gap-2 items-center">
        <input
          type="text" placeholder="Buscar producto por nombre o SKU..."
          value={search}
          aria-label="Buscar producto por nombre o SKU"
          onChange={(e) => alTeclear(e.target.value)}
          className="dax-input flex-1 min-w-[12rem] text-sm" />
        {veCosto && (
          <label className="flex items-center gap-2 text-xs text-dax-muted max-md:min-h-[44px] cursor-pointer">
            <input type="checkbox" checked={soloSinCosto} onChange={(e) => setSoloSinCosto(e.target.checked)} />
            Solo sin costo
          </label>
        )}
      </div>

      {loading && <Spinner text="Buscando..." />}

      {/* Error de la búsqueda con reintento (tabla y tarjetas comparten el aviso). */}
      {errorBusqueda && !loading && !selected && (
        <DaxCard padding={false}>
          <div role="alert" className="p-8 text-center space-y-3">
            <p className="text-sm text-dax-danger">{errorBusqueda}</p>
            <button type="button" onClick={() => doSearch(search)} className="dax-btn-secondary text-xs">
              <i className="fa-solid fa-rotate-right" aria-hidden="true" /> Reintentar
            </button>
          </div>
        </DaxCard>
      )}

      {rows.length > 0 && !selected && (
        <DaxCard padding={false}>
          {esTelefono ? (
            <ListaTarjetas className="p-3">
              {/* Los totales de la tabla, en una tarjeta resumen para teléfono. */}
              <div data-testid="totales-telefono" className="rounded-lg bg-dax-elevated p-3 text-xs font-bold text-dax-text flex flex-wrap gap-x-4 gap-y-1">
                <span>Total de lo listado</span>
                <span className="tabular-nums">{totales.piezas} pzas</span>
                <span className="tabular-nums">{formatCurrency(totales.venta)} a venta</span>
                {veCosto && <span className="tabular-nums">{formatCurrency(totales.costo)} a costo</span>}
              </div>
              {rows.map((row) => (
                <TarjetaFila key={row.variant.id}
                  titulo={row.label}
                  subtitulo={<span className="font-mono text-dax-accent-text">{row.sku}</span>}
                  importe={formatCurrency(importeVenta(row))}
                  estado={<span className={`font-bold tabular-nums ${colorExistencia(row.qty)}`}>{row.qty} en stock</span>}
                  datos={[
                    { etiqueta: 'Precio', valor: formatCurrency(row.variant.price ?? 0) },
                    ...(veCosto ? [
                      { etiqueta: 'Costo', valor: sinCosto(row) ? <span className="text-dax-warning">sin costo</span> : formatCurrency(row.variant.cost ?? 0) },
                      { etiqueta: 'A costo', valor: formatCurrency(importeCosto(row)) },
                    ] : []),
                  ]}
                  acciones={<button type="button" onClick={() => openDetail(row)} className="dax-btn-secondary text-xs"><i className="fa-solid fa-chart-line" aria-hidden="true" /> Kardex</button>}
                />
              ))}
            </ListaTarjetas>
          ) : (
          <TablaDesplazable sangrado={false}>
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
                    <td className="font-mono text-dax-accent-text text-xs">{row.sku}</td>
                    <td className="text-dax-text font-semibold">{row.label}</td>
                    {/* Precio de ESTA talla: `product.price` es el aplanado de la principal. */}
                    <td className="text-right text-dax-muted tabular-nums">{formatCurrency(row.variant.price ?? 0)}</td>
                    {veCosto && (
                      <td className="text-right text-dax-muted tabular-nums">
                        {sinCosto(row) ? <span className="text-dax-warning text-xs font-bold">sin costo</span> : formatCurrency(row.variant.cost ?? 0)}
                      </td>
                    )}
                    <td className={`text-right font-bold tabular-nums ${colorExistencia(row.qty)}`}>{row.qty}</td>
                    <td className="text-right text-dax-muted tabular-nums">{formatCurrency(importeVenta(row))}</td>
                    {veCosto && <td className="text-right text-dax-muted tabular-nums">{formatCurrency(importeCosto(row))}</td>}
                    <td>
                      <button type="button" onClick={() => openDetail(row)} className="dax-btn-secondary text-xs">
                        <i className="fa-solid fa-chart-line" aria-hidden="true" /> Kardex
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="font-bold text-dax-text" data-testid="totales">
                  <td colSpan={veCosto ? 4 : 3}>Total de lo listado</td>
                  <td className="text-right tabular-nums">{totales.piezas}</td>
                  <td className="text-right tabular-nums">{formatCurrency(totales.venta)}</td>
                  {veCosto && <td className="text-right tabular-nums">{formatCurrency(totales.costo)}</td>}
                  <td></td>
                </tr>
              </tfoot>
            </table>
          </TablaDesplazable>
          )}
        </DaxCard>
      )}

      {selected && (
        <div className="space-y-3">
          <div className="flex max-md:flex-wrap items-center max-md:items-start justify-between gap-2">
            <div>
              <p className="text-[10px] text-dax-muted uppercase tracking-widest">Kardex</p>
              <p className="text-lg font-black text-dax-text">{selected.label}</p>
              <p className="text-xs font-mono text-dax-accent-text">{selected.sku}</p>
            </div>
            <div className="flex max-md:flex-wrap gap-2 max-md:[&>button]:min-h-[44px]">
              <button type="button" onClick={() => setAdjustModal(true)} className="dax-btn-secondary text-xs">
                <i className="fa-solid fa-sliders" aria-hidden="true" /> Ajustar
              </button>
              <button type="button" onClick={() => { setSelected(null); setKardex([]) }} className="dax-btn-secondary text-xs">
                <i className="fa-solid fa-xmark" aria-hidden="true" /> Cerrar
              </button>
            </div>
          </div>

          <DaxCard padding={false}>
            {esTelefono ? (
              <ListaTarjetas cargando={kardexLoading} vacio={kardex.length === 0} textoVacio="Sin movimientos registrados" className="p-3">
                {kardex.map((k) => (
                  <TarjetaFila key={k.id}
                    titulo={fechaCorta(k.created_at)}
                    subtitulo={<span className={`dax-badge ${colorMovimiento(k.movement_type)}`}>{tipoMovimiento(k.movement_type)}</span>}
                    importe={<span className={colorMovimiento(k.movement_type)}>{k.qty_change > 0 ? '+' : ''}{k.qty_change}</span>}
                    datos={[
                      { etiqueta: 'Saldo', valor: k.qty_after },
                      { etiqueta: 'Ref.', valor: <span className="font-mono">{k.reference ?? '—'}</span> },
                      { etiqueta: 'Por', valor: k.user_name },
                    ]}
                  />
                ))}
              </ListaTarjetas>
            ) : (
              kardexLoading ? <Spinner text="Cargando kardex..." /> : kardex.length === 0 ? (
                <div className="p-12 text-center text-dax-faint">Sin movimientos registrados</div>
              ) : (
                <TablaDesplazable sangrado={false}>
                  <table className="dax-table w-full">
                    <thead>
                      <tr>
                        <th>Fecha</th>
                        <th>Tipo</th>
                        <th className="text-right">Cantidad</th>
                        <th className="text-right">Saldo</th>
                        <th>Referencia</th>
                        <th>Por</th>
                      </tr>
                    </thead>
                    <tbody>
                      {kardex.map((k) => (
                        <tr key={k.id}>
                          <td className="text-xs text-dax-muted">{fechaCorta(k.created_at)}</td>
                          <td className="text-xs">
                            <span className={`dax-badge ${colorMovimiento(k.movement_type)}`}>{tipoMovimiento(k.movement_type)}</span>
                          </td>
                          <td className={`text-right font-bold tabular-nums ${colorMovimiento(k.movement_type)}`}>
                            {k.qty_change > 0 ? '+' : ''}{k.qty_change}
                          </td>
                          <td className="text-right text-dax-muted text-xs tabular-nums">{k.qty_after}</td>
                          <td className="text-dax-muted text-xs font-mono">{k.reference ?? '—'}</td>
                          <td className="text-dax-muted text-xs">{k.user_name}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </TablaDesplazable>
              )
            )}
          </DaxCard>
        </div>
      )}

      {!loading && !selected && !errorBusqueda && products.length === 0 && search && (
        <DaxCard><div className="p-12 text-center text-dax-faint">Sin resultados para "{search}"</div></DaxCard>
      )}

      {!search && !selected && !loading && (
        <DaxCard><div className="p-12 text-center text-dax-faint">Busca un producto para ver su kardex</div></DaxCard>
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
              <button type="button" onClick={() => setAdjustModal(false)} className="dax-btn-secondary flex-1">Cancelar</button>
              <button type="button" onClick={handleAdjust} disabled={adjSaving || !adjQty || !adjReason || !sucursalAjuste} className="dax-btn-primary flex-1 justify-center disabled:opacity-40">
                {adjSaving ? <i className="fa-solid fa-spinner fa-spin" aria-hidden="true" /> : <><i className="fa-solid fa-check" aria-hidden="true" /> Ajustar</>}
              </button>
            </>
          }
        >
          <p className="text-dax-muted text-sm mb-4">{selected.label}</p>
          <div className="space-y-3">
            <div>
              <label className="dax-label" htmlFor="ajuste-sucursal">Sucursal</label>
              <select id="ajuste-sucursal" value={sucursalAjuste} onChange={(e) => setAdjBranch(e.target.value)}
                disabled={!veCosto} className="dax-input w-full">
                <option value="">Seleccionar...</option>
                {/* Si la lista de sucursales aún no llega, la propia se ofrece igual para que el valor no quede huérfano. */}
                {!veCosto && usuarioBranchId && !branches.some((b) => b.id === usuarioBranchId) && (
                  <option value={usuarioBranchId}>{usuarioBranchName ?? `Sucursal ${usuarioBranchId}`}</option>
                )}
                {branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
              </select>
            </div>
            <div>
              <label className="dax-label" htmlFor="ajuste-cantidad">Cantidad (+ agregar / - restar)</label>
              <input id="ajuste-cantidad" type="number" value={adjQty} onChange={(e) => setAdjQty(e.target.value)}
                placeholder="+10 o -5" className="dax-input w-full text-lg font-bold" autoFocus />
            </div>
            <div>
              <label className="dax-label" htmlFor="ajuste-motivo">Motivo</label>
              <input id="ajuste-motivo" value={adjReason} onChange={(e) => setAdjReason(e.target.value)}
                placeholder="Conteo físico, merma, etc." className="dax-input w-full" />
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}
