import { Fragment, useEffect, useState, useCallback, useRef } from 'react'
import { useLocation } from 'react-router-dom'
import { productsApi } from '../../api/products'
import { useAuthStore } from '../../store/authStore'
import { useBranchCountStore, esTiendaUnica } from '../../store/branchCountStore'
import { useIsBranchUser } from '../../components/branch/useIsBranchUser'
import { ProductsBranchView } from '../../components/branch/ProductsBranchView'
import { DaxCard } from '../../components/ui/DaxCard'
import { Spinner } from '../../components/ui/Spinner'
import { Badge } from '../../components/ui/Badge'
import type { Product, Department } from '../../types/products'
import { formatCurrency } from '../../utils/currency'
import { sortByName } from '../../utils/sortByName'
import { toast } from '../../store/toastStore'
import { Modal } from '../../components/ui/Modal'
import { FormularioProducto } from '../../components/products/FormularioProducto'
import { expandVariantRows, grupoDeVariantes, nombreDeVariante, priceRange, sumStock } from './variantRows'

const SINGULAR_GRUPO = { tallas: 'talla', colores: 'color', variantes: 'variante' } as const

const HQ_ROLES = ['ADMINISTRADOR', 'DUEÑO']
const CAN_EDIT_ROLES = ['ADMINISTRADOR', 'DUEÑO', 'GERENTE', 'CAJERO']

// ─── Import Modal ──────────────────────────────────────────────────────────────

function ImportModal({ onClose, onDone, isHQ }: { onClose: () => void; onDone: () => void; isHQ: boolean }) {
  const [file, setFile] = useState<File | null>(null)
  const [scope, setScope] = useState<'branch' | 'all' | 'selected'>('branch')
  const [result, setResult] = useState<{ created: number; updated: number; failed: number; errors: string[] } | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const handleUpload = async () => {
    if (!file) return
    setLoading(true); setError(null)
    try {
      const uploadScope = isHQ ? scope : 'branch'
      const res = await productsApi.uploadProducts(file, uploadScope)
      setResult(res)
      if (res.created > 0 || res.updated > 0) onDone()
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'Error al importar. Revisa el archivo.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm" onClick={onClose}>
      <div className="dax-card dax-modal p-6 w-full max-w-md" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-black text-white">Importar productos</h3>
          <button onClick={onClose} className="text-slate-500 hover:text-white"><i className="fa-solid fa-xmark text-lg" /></button>
        </div>

        {!result ? (
          <div className="space-y-4">
            <p className="text-slate-400 text-xs leading-relaxed">
              Sube un archivo Excel (.xlsx) o CSV con tus productos. Los productos nuevos se activarán automáticamente en tu sucursal.
            </p>

            {isHQ && (
              <div>
                <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-2">
                  Alcance de importación
                </label>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={() => setScope('all')}
                    className={`py-2 rounded-xl text-xs font-semibold border transition-colors ${
                      scope === 'all'
                        ? 'border-indigo-500 bg-indigo-600/20 text-white'
                        : 'border-slate-700/50 text-slate-400 hover:border-slate-600 hover:text-white'
                    }`}
                  >
                    <i className="fa-solid fa-globe mr-1.5" />
                    Todas las sucursales
                  </button>
                  <button
                    type="button"
                    onClick={() => setScope('branch')}
                    className={`py-2 rounded-xl text-xs font-semibold border transition-colors ${
                      scope === 'branch'
                        ? 'border-indigo-500 bg-indigo-600/20 text-white'
                        : 'border-slate-700/50 text-slate-400 hover:border-slate-600 hover:text-white'
                    }`}
                  >
                    <i className="fa-solid fa-building mr-1.5" />
                    Solo HQ
                  </button>
                </div>
              </div>
            )}

            <button
              onClick={async () => {
                try {
                  await productsApi.downloadTemplate()
                } catch {
                  toast.error('No se pudo descargar la plantilla. Reintenta en unos segundos.')
                }
              }}
              className="w-full flex items-center justify-center gap-2 py-2 rounded-xl text-xs font-semibold border border-slate-700 text-slate-400 hover:text-white hover:border-slate-500 transition-colors"
            >
              <i className="fa-solid fa-file-excel text-emerald-400" /> Descargar plantilla con productos actuales
            </button>

            <div
              onClick={() => fileRef.current?.click()}
              className={`border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-colors ${file ? 'border-indigo-500/50 bg-indigo-600/5' : 'border-slate-700 hover:border-slate-500'}`}
            >
              <input
                ref={fileRef}
                type="file"
                accept=".xlsx,.xlsm,.xls,.csv"
                className="hidden"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
              {file ? (
                <>
                  <i className="fa-solid fa-file-check text-indigo-400 text-2xl mb-2 block" />
                  <p className="text-white text-sm font-semibold">{file.name}</p>
                  <p className="text-slate-500 text-xs mt-0.5">{(file.size / 1024).toFixed(1)} KB</p>
                </>
              ) : (
                <>
                  <i className="fa-solid fa-cloud-arrow-up text-slate-500 text-2xl mb-2 block" />
                  <p className="text-slate-400 text-sm">Clic para seleccionar archivo</p>
                  <p className="text-slate-600 text-xs mt-0.5">.xlsx, .xls, .csv</p>
                </>
              )}
            </div>

            {error && <p className="text-red-400 text-xs bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">{error}</p>}

            <div className="flex gap-2">
              <button onClick={onClose} className="dax-btn-secondary flex-1">Cancelar</button>
              <button
                onClick={handleUpload}
                disabled={!file || loading}
                className="dax-btn-primary flex-1 justify-center disabled:opacity-40"
              >
                {loading ? <i className="fa-solid fa-spinner fa-spin" /> : <><i className="fa-solid fa-file-import" /> Importar</>}
              </button>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="grid grid-cols-3 gap-3 text-center">
              <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-xl p-3">
                <p className="text-2xl font-black text-emerald-400">{result.created}</p>
                <p className="text-[10px] text-slate-500 uppercase tracking-wider mt-0.5">Nuevos</p>
              </div>
              <div className="bg-indigo-500/10 border border-indigo-500/20 rounded-xl p-3">
                <p className="text-2xl font-black text-indigo-400">{result.updated}</p>
                <p className="text-[10px] text-slate-500 uppercase tracking-wider mt-0.5">Actualizados</p>
              </div>
              <div className={`${result.failed > 0 ? 'bg-red-500/10 border-red-500/20' : 'bg-slate-800 border-slate-700/50'} border rounded-xl p-3`}>
                <p className={`text-2xl font-black ${result.failed > 0 ? 'text-red-400' : 'text-slate-500'}`}>{result.failed}</p>
                <p className="text-[10px] text-slate-500 uppercase tracking-wider mt-0.5">Fallidos</p>
              </div>
            </div>

            {result.errors.length > 0 && (
              <div className="bg-red-500/5 border border-red-500/20 rounded-xl p-3 max-h-32 overflow-y-auto">
                <p className="text-[10px] font-bold text-red-400 uppercase tracking-wider mb-1.5">Errores</p>
                {result.errors.map((e, i) => (
                  <p key={i} className="text-red-300 text-xs">{e}</p>
                ))}
              </div>
            )}

            <button onClick={onClose} className="w-full dax-btn-primary justify-center">
              <i className="fa-solid fa-check" /> Cerrar
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Main Products Page ─────────────────────────────────────────────────────────

export function Products() {
  // Roles de sucursal (CAJERO/GERENTE) ven la vista simplificada con modales
  // y acciones por fila; HQ conserva la matriz multi-sucursal completa.
  if (useIsBranchUser()) return <ProductsBranchView />
  return <ProductsHQView />
}

// Separado para no romper Rules of Hooks: el return condicional de arriba
// no puede convivir con hooks en el mismo componente.
function ProductsHQView() {
  const location = useLocation()
  const { user } = useAuthStore()
  const isHQ = HQ_ROLES.includes(user?.role ?? '')
  const unaSolaSucursal = esTiendaUnica(useBranchCountStore((s) => s.count))
  const canEdit = CAN_EDIT_ROLES.includes(user?.role ?? '')

  const [products, setProducts] = useState<Product[]>([])
  const [departments, setDepartments] = useState<Department[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(0)
  const [search, setSearch] = useState('')
  const [deptId, setDeptId] = useState<string>('')
  const [loading, setLoading] = useState(true)
  const [viewMode, setViewMode] = useState<'list' | 'grid'>('list')
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Formulario único (components/products/FormularioProducto) dentro de un Modal.
  const [editor, setEditor] = useState<{ mode: 'create' } | { mode: 'edit'; productId: string } | null>(null)
  const [showImport, setShowImport] = useState(false)
  // Producto cuyo desglose por talla está abierto en la tabla.
  const [expandedVariantsId, setExpandedVariantsId] = useState<string | null>(null)
  // Tallas sin código de barras (se pide una vez al abrir la pantalla).
  const [codigosFaltantes, setCodigosFaltantes] = useState(0)
  const [generandoCodigos, setGenerandoCodigos] = useState(false)
  const [descargandoEtiquetas, setDescargandoEtiquetas] = useState(false)

  const LIMIT = 50

  const load = useCallback(async (q: string, dept: string, pg: number) => {
    setLoading(true)
    try {
      const params: Record<string, unknown> = { search: q, skip: pg * LIMIT, limit: LIMIT }
      if (dept) params.department_id = dept
      // CAJERO/GERENTE: NO enviamos branch_id ni active_in_branch — el backend
      // los deriva del JWT (defense in depth). Admins podrán usar un selector
      // de sucursal más adelante; por ahora ningún rol los envía desde aquí.
      const res = await productsApi.list(params)
      setProducts(res.items ?? [])
      setTotal(res.total ?? 0)
    } catch (e: any) {
      setProducts([])
      setTotal(0)
      const detail = e?.response?.data?.detail
      toast.error(typeof detail === 'string' ? detail : 'No se pudo cargar el catálogo. Reintenta.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    productsApi.getDepartments()
      .then((d) => setDepartments(sortByName(d)))
      .catch(() => toast.error('No se pudieron cargar los departamentos.'))
    // Silencioso a propósito: si el contador falla, el botón simplemente no
    // aparece — no es motivo para molestar con un toast al abrir el catálogo.
    productsApi.barcodesMissingCount()
      .then(setCodigosFaltantes)
      .catch(() => setCodigosFaltantes(0))
  }, [])

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      setPage(0)
      load(search, deptId, 0)
    }, 300)
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current) }
  }, [search, deptId, load])

  // Refetch list whenever we navigate back to this page (e.g., after saving
  // a product in ProductForm). location.key changes on every navigation event,
  // so this fires on mount and on any return from a child route.
  const isFirstRender = useRef(true)
  useEffect(() => {
    if (isFirstRender.current) { isFirstRender.current = false; return }
    load(search, deptId, page)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.key])

  const pages = Math.ceil(total / LIMIT)

  const openEdit = (p: Product) => setEditor({ mode: 'edit', productId: p.id })
  const handleSaved = () => { setEditor(null); load(search, deptId, page) }
  const handleNewProductClick = () => setEditor({ mode: 'create' })

  const descargarEtiquetas = async () => {
    setDescargandoEtiquetas(true)
    try {
      await productsApi.downloadLabelsCsv()
    } catch {
      toast.error('No se pudo descargar el CSV de etiquetas. Reintenta.')
    } finally {
      setDescargandoEtiquetas(false)
    }
  }

  const generarCodigos = async () => {
    setGenerandoCodigos(true)
    try {
      const n = await productsApi.assignMissingBarcodes()
      toast.success(`${n} códigos generados`)
    } catch (e: any) {
      const detail = e?.response?.data?.detail
      toast.error(typeof detail === 'string' ? detail : 'No se pudieron generar los códigos.')
      setGenerandoCodigos(false)
      return
    }
    // Refresco APARTE del try de arriba: los códigos ya se generaron, así que
    // si la relectura falla no debe salir un "no se pudieron generar" falso.
    // El código nuevo vive en la variante: hay que releer la lista para que el
    // desglose por talla lo muestre, y el contador para ocultar el botón.
    try {
      await load(search, deptId, page)
      setCodigosFaltantes(await productsApi.barcodesMissingCount())
    } catch {
      /* el catálogo se recarga solo al siguiente filtro o navegación */
    } finally {
      setGenerandoCodigos(false)
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <i className="fa-solid fa-barcode text-indigo-400 text-xl" />
          <h1 className="text-2xl font-black text-white">
            {isHQ ? 'Productos' : 'Consulta de productos'}
          </h1>
          {/* Con una sola tienda, "HQ Global" no nombra nada que la dueña
              reconozca: el alcance ya es "toda la tienda". El chip solo
              aparece cuando de verdad hay varias sucursales. */}
          {isHQ && !unaSolaSucursal && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-violet-600/20 text-violet-400 border border-violet-500/30 rounded text-[9px] font-black uppercase tracking-widest">
              <i className="fa-solid fa-building-shield text-[8px]" /> Todas las sucursales
            </span>
          )}
        </div>
        {/* Un solo ítem flex sin `flex-wrap` sumaba ~420 px de mínimo y
            desbordaba la página a 390 px: ahora envuelve y bajo `sm` los
            botones son solo icono (el texto vive en el `aria-label`). */}
        <div className="flex flex-wrap items-center gap-2 sm:gap-3 w-full sm:w-auto">
          <span className="text-slate-500 text-sm">{total.toLocaleString()} productos</span>
          {canEdit && (
            <>
              <button
                onClick={() => setShowImport(true)}
                aria-label="Importar productos"
                className="dax-btn-secondary dax-btn-icon text-xs flex items-center gap-1.5 whitespace-nowrap"
              >
                <i className="fa-solid fa-file-import" /> <span className="hidden sm:inline">Importar</span>
              </button>
              <button
                onClick={descargarEtiquetas}
                disabled={descargandoEtiquetas}
                className="dax-btn-secondary dax-btn-icon text-xs flex items-center gap-1.5 disabled:opacity-50 whitespace-nowrap"
                title="CSV con una fila por talla para la etiquetadora"
                aria-label="Descargar etiquetas CSV"
              >
                <i className={`fa-solid ${descargandoEtiquetas ? 'fa-spinner fa-spin' : 'fa-tags'}`} />{' '}
                <span className="hidden sm:inline">Etiquetas CSV</span>
              </button>
              {isHQ && codigosFaltantes > 0 && (
                <button
                  onClick={generarCodigos}
                  disabled={generandoCodigos}
                  className="dax-btn-secondary dax-btn-icon text-xs flex items-center gap-1.5 disabled:opacity-50 whitespace-nowrap"
                  title="Genera un código de barras propio para cada talla que no tenga"
                  aria-label={`Generar códigos de barras faltantes (${codigosFaltantes})`}
                >
                  <i className={`fa-solid ${generandoCodigos ? 'fa-spinner fa-spin' : 'fa-barcode'}`} />{' '}
                  <span className="hidden sm:inline">Generar códigos </span>({codigosFaltantes})
                </button>
              )}
              <button
                onClick={handleNewProductClick}
                aria-label="Nuevo producto"
                className="dax-btn dax-btn-icon text-xs flex items-center gap-1.5 whitespace-nowrap"
              >
                <i className="fa-solid fa-plus" /> <span className="hidden sm:inline">Nuevo producto</span>
              </button>
            </>
          )}
          <div className="flex items-center bg-slate-800 rounded-lg border border-slate-700/50 p-0.5">
            <button
              onClick={() => setViewMode('list')}
              className={`dax-btn-icon p-1.5 rounded-md transition-colors ${viewMode === 'list' ? 'bg-slate-700 text-white' : 'text-slate-400 hover:text-white'}`}
              title="Vista lista"
              aria-label="Vista lista"
            >
              <i className="fa-solid fa-list w-4 text-xs" />
            </button>
            <button
              onClick={() => setViewMode('grid')}
              className={`dax-btn-icon p-1.5 rounded-md transition-colors ${viewMode === 'grid' ? 'bg-slate-700 text-white' : 'text-slate-400 hover:text-white'}`}
              title="Vista cuadrícula"
              aria-label="Vista cuadrícula"
            >
              <i className="fa-solid fa-grip w-4 text-xs" />
            </button>
          </div>
        </div>
      </div>

      {/* Filtros */}
      <div className="flex gap-3 flex-wrap">
        <input
          type="text"
          placeholder="Buscar por nombre o SKU..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="dax-input max-w-xs"
        />
        <select
          value={deptId}
          onChange={(e) => { setDeptId(e.target.value); setPage(0) }}
          className="dax-input max-w-[200px]"
        >
          <option value="">Todos los departamentos</option>
          {departments.map((d) => (
            <option key={d.id} value={d.id}>{d.name}</option>
          ))}
        </select>
      </div>

      {/* Tabla */}
      <DaxCard padding={false}>
        {loading ? (
          <Spinner text="Cargando productos..." />
        ) : products.length === 0 ? (
          <div className="p-12 text-center text-slate-600">Sin resultados</div>
        ) : viewMode === 'grid' ? (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3 p-4">
            {products.map((p) => (
              <div key={p.id} className="bg-slate-800 rounded-xl p-3 flex flex-col gap-2 border border-slate-700/30 hover:border-indigo-500/30 transition-colors group relative">
                {p.image_url ? (
                  <img src={p.image_url} alt={p.name} className="w-full aspect-square object-contain rounded-lg bg-slate-700 p-1" />
                ) : (
                  <div className="w-full aspect-square bg-slate-700/50 rounded-lg flex items-center justify-center">
                    <i className="fa-solid fa-box text-slate-500 text-2xl" />
                  </div>
                )}
                <div className="flex-1">
                  <p className="text-white text-xs font-semibold line-clamp-2 leading-tight">{p.sale_name ?? p.name}</p>
                  <p className="text-slate-500 text-[10px] font-mono mt-0.5">{p.sku}</p>
                  {p.department_name && <p className="text-slate-600 text-[10px] mt-0.5 truncate">{p.department_name}</p>}
                </div>
                <div className="flex items-center justify-between">
                  {(() => {
                    // Con precio de sucursal (override) manda el override, igual
                    // que en la lista: el rango solo se muestra sin override.
                    const override = user?.branch_id
                      ? p.branch_statuses?.find(s => s.branch_id === user.branch_id)?.price_override
                      : null
                    const rango = priceRange(p.variants ?? [])
                    const mostrarRango = override == null && rango != null && !rango.uniforme
                    return (
                      <span className="text-emerald-400 text-xs font-bold">
                        {mostrarRango
                          ? `${formatCurrency(rango!.min)} – ${formatCurrency(rango!.max)}`
                          : formatCurrency(override ?? p.price ?? 0)}
                      </span>
                    )
                  })()}
                  {(() => {
                    const variantCount = p.variants?.length ?? 0
                    const qty = variantCount > 1
                      ? sumStock(p)
                      : (!isHQ && user?.branch_id && p.stock_levels?.length)
                        ? (p.stock_levels.find(s => s.branch_id === user.branch_id)?.qty_on_hand ?? p.stock ?? 0)
                        : (p.stock_total ?? p.stock ?? 0)
                    if (variantCount <= 1) {
                      return (
                        <span className={`dax-badge text-[10px] ${qty > 0 ? 'dax-badge-green' : 'dax-badge-red'}`}>
                          {qty}
                        </span>
                      )
                    }
                    const grupo = grupoDeVariantes(p.variants ?? [])
                    return (
                      <button
                        type="button"
                        // La cuadrícula no tiene dónde desplegar el desglose:
                        // se salta a la lista con ese producto ya abierto.
                        onClick={() => { setViewMode('list'); setExpandedVariantsId(p.id) }}
                        title={`Ver la existencia por ${SINGULAR_GRUPO[grupo]}`}
                        className="flex flex-col items-end group/tallas"
                      >
                        <span className={`dax-badge text-[10px] ${qty > 0 ? 'dax-badge-green' : 'dax-badge-red'}`}>
                          {qty}
                        </span>
                        <span className="text-slate-400 text-[10px] mt-0.5 group-hover/tallas:text-indigo-400">
                          de {variantCount} {grupo}
                        </span>
                      </button>
                    )
                  })()}
                </div>
                {/* En un teléfono no hay `hover`: con `opacity-0` los botones
                    existían pero no se veían nunca. Visibles bajo `md`; de
                    `md` hacia arriba, igual que siempre. */}
                {canEdit && (
                  <div className="absolute top-2 right-2 flex items-center gap-1 opacity-100 md:opacity-0 md:group-hover:opacity-100 focus-within:opacity-100 transition-opacity">
                    <button
                      onClick={() => openEdit(p)}
                      className="w-6 h-6 min-w-[44px] min-h-[44px] md:min-w-0 md:min-h-0 rounded-full flex items-center justify-center bg-slate-700 border border-slate-600 hover:bg-indigo-600 hover:border-indigo-500"
                      title="Editar producto"
                      aria-label="Editar producto"
                    >
                      <i className="fa-solid fa-pencil text-[9px] text-white" />
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="dax-table w-full">
              <thead>
                <tr>
                  <th>SKU</th>
                  <th>Producto</th>
                  <th>Departamento</th>
                  <th className="text-right">Precio</th>
                  <th className="text-right">Stock</th>
                  <th>Estado</th>
                  {canEdit && <th />}
                </tr>
              </thead>
              <tbody>
                {products.map((p) => {
                  const tallasAbiertas = expandedVariantsId === p.id && (p.variants?.length ?? 0) > 1
                  const colCount = 6 + (canEdit ? 1 : 0)
                  return (
                    <Fragment key={p.id}>
                      <tr>
                        <td className="font-mono text-slate-400 text-xs">{p.sku}</td>
                        <td>
                          <div className="flex items-center gap-2">
                            {p.image_url ? (
                              <img src={p.image_url} alt="" className="w-8 h-8 rounded object-cover flex-shrink-0" />
                            ) : (
                              <div className="w-8 h-8 rounded bg-slate-700 flex items-center justify-center flex-shrink-0">
                                <i className="fa-solid fa-box text-slate-500 text-xs" />
                              </div>
                            )}
                            <span className="font-medium text-white">{p.sale_name ?? p.name}</span>
                          </div>
                        </td>
                        <td className="text-slate-400 text-xs">{p.department_name ?? '—'}</td>
                        <td className="text-right font-semibold text-emerald-400">
                          {(() => {
                            const override = user?.branch_id
                              ? p.branch_statuses?.find(s => s.branch_id === user.branch_id)?.price_override
                              : null
                            const effective = override != null ? override : (p.price ?? 0)
                            // Con varias tallas a distinto precio, un solo número miente:
                            // el de la fila era el de la principal. Se muestra el rango.
                            const rango = priceRange(p.variants ?? [])
                            const mostrarRango = override == null && rango != null && !rango.uniforme
                            return (
                              <div className="flex flex-col items-end leading-tight">
                                <span>
                                  {mostrarRango
                                    ? `${formatCurrency(rango!.min)} – ${formatCurrency(rango!.max)}`
                                    : formatCurrency(effective)}
                                </span>
                                {override != null && (
                                  <span className="text-[9px] text-indigo-400 font-normal">
                                    override (base {formatCurrency(p.price ?? 0)})
                                  </span>
                                )}
                                {mostrarRango && (
                                  <span className="text-[9px] text-slate-500 font-normal">
                                    según la {SINGULAR_GRUPO[grupoDeVariantes(p.variants ?? [])]}
                                  </span>
                                )}
                              </div>
                            )
                          })()}
                        </td>
                        <td className="text-right">
                          {(() => {
                            const variantCount = p.variants?.length ?? 0
                            // Con varias tallas la existencia del renglón es la SUMA:
                            // antes se veía solo la de la principal (3 de 12).
                            const qty = variantCount > 1
                              ? sumStock(p)
                              : (!isHQ && user?.branch_id && p.stock_levels?.length)
                                ? (p.stock_levels.find(s => s.branch_id === user.branch_id)?.qty_on_hand ?? p.stock ?? 0)
                                : (p.stock_total ?? p.stock ?? 0)
                            if (variantCount <= 1) {
                              return (
                                <span className={`dax-badge ${qty > 0 ? 'dax-badge-green' : 'dax-badge-red'}`}>
                                  {qty}
                                </span>
                              )
                            }
                            const grupo = grupoDeVariantes(p.variants ?? [])
                            return (
                              <button
                                type="button"
                                onClick={() => setExpandedVariantsId(tallasAbiertas ? null : p.id)}
                                aria-expanded={tallasAbiertas}
                                title={tallasAbiertas ? 'Ocultar el desglose' : `Ver la existencia por ${SINGULAR_GRUPO[grupo]}`}
                                className="flex flex-col items-end leading-tight ml-auto group/tallas"
                              >
                                <span className={`dax-badge ${qty > 0 ? 'dax-badge-green' : 'dax-badge-red'}`}>
                                  {qty}
                                </span>
                                <span className="text-slate-400 text-[10px] mt-0.5 group-hover/tallas:text-indigo-400">
                                  de {variantCount} {grupo}
                                  <i className={`fa-solid ${tallasAbiertas ? 'fa-chevron-up' : 'fa-chevron-down'} ml-1 text-[8px]`} />
                                </span>
                              </button>
                            )
                          })()}
                        </td>
                        <td>
                          {isHQ ? (
                            <span className="text-xs text-slate-400">
                              {p.branch_statuses?.filter(s => s.is_active_pos).length ?? 0}
                              <span className="text-slate-600 ml-0.5">sucursales</span>
                            </span>
                          ) : user?.branch_id ? (
                            (() => {
                              const status = p.branch_statuses?.find(s => s.branch_id === user.branch_id)
                              if (!status) return <span className="text-[10px] text-slate-600 italic">Global</span>
                              return status.is_active_pos
                                ? <Badge variant="green">POS activo</Badge>
                                : <Badge variant="red">POS inactivo</Badge>
                            })()
                          ) : null}
                        </td>
                        {canEdit && (
                          <td className="text-right">
                            <div className="inline-flex items-center gap-1">
                              <button
                                onClick={() => openEdit(p)}
                                className="dax-btn-icon transition-colors p-1 text-slate-500 hover:text-indigo-400"
                                title="Editar producto"
                                aria-label="Editar producto"
                              >
                                <i className="fa-solid fa-pencil text-xs" />
                              </button>
                            </div>
                          </td>
                        )}
                      </tr>
                      {tallasAbiertas && expandVariantRows([p]).map((row) => (
                        <tr key={row.variant.id} className="bg-slate-900/40 text-xs">
                          <td className="font-mono text-slate-500 pl-6">
                            {row.sku}
                            {row.barcode && (
                              <span className="block text-[10px] text-slate-600" title="Código de barras">
                                {row.barcode}
                              </span>
                            )}
                          </td>
                          <td className="text-slate-300">
                            <i className="fa-solid fa-turn-up fa-rotate-90 text-slate-600 mr-2 text-[10px]" />
                            {nombreDeVariante(p, row.variant)}
                          </td>
                          <td />
                          <td className="text-right text-emerald-400/80">{formatCurrency(row.variant.price ?? 0)}</td>
                          <td className={`text-right font-semibold ${row.qty > 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                            {row.qty}
                          </td>
                          <td colSpan={colCount - 5} />
                        </tr>
                      ))}
                    </Fragment>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* Paginación */}
        {pages > 1 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-slate-700/50">
            <button
              onClick={() => { const np = page - 1; setPage(np); load(search, deptId, np) }}
              disabled={page === 0}
              className="dax-btn-secondary text-xs disabled:opacity-40"
            >
              ← Anterior
            </button>
            <span className="text-slate-500 text-xs">Página {page + 1} de {pages}</span>
            <button
              onClick={() => { const np = page + 1; setPage(np); load(search, deptId, np) }}
              disabled={page >= pages - 1}
              className="dax-btn-secondary text-xs disabled:opacity-40"
            >
              Siguiente →
            </button>
          </div>
        )}
      </DaxCard>

      {/* Modales */}
      {showImport && (
        <ImportModal
          isHQ={isHQ}
          onClose={() => setShowImport(false)}
          onDone={() => { setShowImport(false); load(search, deptId, page) }}
        />
      )}
      {editor && (
        <Modal open onClose={() => setEditor(null)} size="xl" closeOnBackdrop={false}
          title={editor.mode === 'create' ? 'Nuevo producto' : 'Editar producto'}>
          <FormularioProducto
            mode={editor.mode}
            productId={editor.mode === 'edit' ? editor.productId : undefined}
            presentacion="modal"
            onDone={handleSaved}
            onCancel={() => setEditor(null)}
          />
        </Modal>
      )}
    </div>
  )
}
