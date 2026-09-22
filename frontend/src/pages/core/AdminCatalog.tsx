import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { productsApi } from '../../api/products'
import { useAuthStore } from '../../store/authStore'
import { DaxCard } from '../../components/ui/DaxCard'
import { Spinner } from '../../components/ui/Spinner'
import { CatalogKpis } from '../../components/catalog/CatalogKpis'
import { ProductBranchMatrix } from '../../components/catalog/ProductBranchMatrix'
import { ProductAuditDrawer } from '../../components/catalog/ProductAuditDrawer'
import { TablaDesplazable } from '../../components/ui/TablaDesplazable'
import { useMediaQuery } from '../../hooks/useMediaQuery'
import { ACCIONES_CATALOGO, accionesDeProducto, type ClaveAccionCatalogo } from './catalogActions'
import { formatCurrency } from '../../utils/currency'
import { toast } from '../../store/toastStore'
import { confirm } from '../../components/ui/ConfirmDialog'
import type { Product, Department, Brand } from '../../types/products'

const PAGE_LIMIT = 50

type ApprovalFilter = 'ALL' | 'PENDING' | 'APPROVED' | 'REJECTED'

export function AdminCatalog() {
  const { org } = useAuthStore()
  const navigate = useNavigate()

  const [search, setSearch] = useState('')
  const [deptId, setDeptId] = useState<string>('')
  const [brandId, setBrandId] = useState<string>('')
  const [approval, setApproval] = useState<ApprovalFilter>('ALL')
  const [noBranchOnly, setNoBranchOnly] = useState(false)
  const [includeArchived, setIncludeArchived] = useState(false)
  const [page, setPage] = useState(0)

  const [departments, setDepartments] = useState<Department[]>([])
  const [brands, setBrands] = useState<Brand[]>([])
  const [products, setProducts] = useState<Product[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)

  const [kpis, setKpis] = useState<Awaited<ReturnType<typeof productsApi.catalogKpis>> | null>(null)
  const [kpisLoading, setKpisLoading] = useState(true)

  const [matrixProduct, setMatrixProduct] = useState<Product | null>(null)
  const [auditProduct, setAuditProduct] = useState<Product | null>(null)

  const debounceRef = useRef<number | null>(null)

  // Bajo `md` la tabla pedía ~1020 px de ancho (7 columnas + hasta 7 botones
  // de 44 px en la última) y había que desplazarse ~660 px para llegar a
  // «Editar», momento en el que ya no se veía de qué producto se trataba.
  const enTarjetas = useMediaQuery('(max-width: 767px)')

  const pages = Math.max(1, Math.ceil(total / PAGE_LIMIT))

  const currentFilters = useMemo(
    () => ({
      search: search.trim() || undefined,
      department_id: deptId || undefined,
      brand_id: brandId || undefined,
      approval_status: approval === 'ALL' ? undefined : approval,
    }),
    [search, deptId, brandId, approval],
  )

  const listFilters = useMemo(
    () => ({
      ...currentFilters,
      include_inactive: includeArchived || undefined,
    }),
    [currentFilters, includeArchived],
  )

  const loadList = useCallback(async (pg: number) => {
    setLoading(true)
    try {
      const res = await productsApi.list({
        ...listFilters,
        skip: pg * PAGE_LIMIT,
        limit: PAGE_LIMIT,
      })
      let items = res.items ?? []
      if (noBranchOnly) {
        items = items.filter((p) => !p.branch_statuses || p.branch_statuses.length === 0)
      }
      setProducts(items)
      setTotal(res.total ?? items.length)
    } catch (e: any) {
      const detail = e?.response?.data?.detail
      toast.error(typeof detail === 'string' ? detail : 'No se pudo cargar el catálogo.')
      setProducts([])
      setTotal(0)
    } finally {
      setLoading(false)
    }
  }, [listFilters, noBranchOnly])

  const loadKpis = useCallback(async () => {
    setKpisLoading(true)
    try {
      const data = await productsApi.catalogKpis(currentFilters)
      setKpis(data)
    } catch {
      // KPIs silent fail — banner ya cubre errores generales en list()
      setKpis(null)
    } finally {
      setKpisLoading(false)
    }
  }, [currentFilters])

  useEffect(() => {
    productsApi.getDepartments()
      .then(setDepartments)
      .catch(() => toast.error('No se pudieron cargar los departamentos.'))
    productsApi.getBrands()
      .then(setBrands)
      .catch(() => toast.error('No se pudieron cargar las marcas.'))
  }, [])

  useEffect(() => {
    if (debounceRef.current) window.clearTimeout(debounceRef.current)
    debounceRef.current = window.setTimeout(() => {
      setPage(0)
      loadList(0)
      loadKpis()
    }, 300)
    return () => { if (debounceRef.current) window.clearTimeout(debounceRef.current) }
  }, [listFilters, noBranchOnly, loadList, loadKpis])

  const handleEdit = (product: Product) => {
    // `/products?edit=<id>` no lo lee nadie: el lápiz dejaba al admin en el
    // listado, sin formulario. La edición completa (precios escalonados,
    // empaques y tablas de tallas) vive en /products/:id/edit, que admite
    // ADMINISTRADOR/DUEÑO/GERENTE/CAJERO (ver App.tsx).
    navigate(`/products/${product.id}/edit`)
  }

  const handleMatrix = (product: Product) => {
    setMatrixProduct(product)
  }

  const handleExport = async () => {
    try {
      // `listFilters` (no `currentFilters`) es el que trae `include_inactive`:
      // exportar debe respetar el checkbox "Incluir archivados" tal como se ve
      // en la tabla, no el conjunto sin filtrar.
      await productsApi.downloadTemplate({
        ...listFilters,
      })
      toast.success('Descarga iniciada.')
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'No se pudo exportar el catálogo.')
    }
  }

  const handleDelete = async (product: Product) => {
    const ok = await confirm({
      title: 'Archivar producto',
      message: `"${product.name}" se desactivará en todas las sucursales. Podrás volver a verlo filtrando por archivados.`,
      confirmText: 'Archivar',
      variant: 'danger',
    })
    if (!ok) return
    try {
      await (await import('../../api/client')).default.delete(`/products/${product.id}`)
      toast.success('Producto archivado.')
      loadList(page)
      loadKpis()
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Error al archivar.')
    }
  }

  const handleDuplicate = async (product: Product) => {
    const ok = await confirm({
      title: 'Duplicar producto',
      message: `Se creará una copia de "${product.name}" con SKU nuevo y sin existencias.`,
      confirmText: 'Duplicar',
      variant: 'info',
    })
    if (!ok) return
    try {
      const copy = await productsApi.duplicate(product.id)
      toast.success(`Copia creada: ${copy.sku}`)
      loadList(page)
      loadKpis()
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Error al duplicar.')
    }
  }

  const handleApprove = async (product: Product) => {
    try {
      await productsApi.approve(product.id)
      toast.success(`Aprobado: ${product.name}`)
      loadList(page)
      loadKpis()
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Error al aprobar.')
    }
  }

  const handleReject = async (product: Product) => {
    const ok = await confirm({
      title: 'Rechazar producto',
      message: `"${product.name}" se desactivará en el punto de venta de todas las sucursales.`,
      confirmText: 'Rechazar',
      variant: 'danger',
    })
    if (!ok) return
    try {
      await productsApi.reject(product.id)
      toast.success(`Rechazado: ${product.name}`)
      loadList(page)
      loadKpis()
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Error al rechazar.')
    }
  }

  const handleRestore = async (product: Product) => {
    try {
      const res = await productsApi.restore(product.id)
      toast.success(res.message ?? 'Producto restaurado.')
      loadList(page)
      loadKpis()
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Error al restaurar.')
    }
  }

  const correrAccion = (clave: ClaveAccionCatalogo, product: Product) => {
    switch (clave) {
      case 'matriz': return handleMatrix(product)
      case 'aprobar': return handleApprove(product)
      case 'rechazar': return handleReject(product)
      case 'historial': return setAuditProduct(product)
      case 'editar': return handleEdit(product)
      case 'duplicar': return handleDuplicate(product)
      case 'archivar': return handleDelete(product)
      case 'restaurar': return handleRestore(product)
    }
  }

  /** Los mismos botones en la fila de la tabla y en la tarjeta. */
  const botonesDeAcciones = (product: Product, conTexto: boolean) =>
    accionesDeProducto(product).map((clave) => {
      const meta = ACCIONES_CATALOGO[clave]
      return (
        <button
          key={clave}
          onClick={() => correrAccion(clave, product)}
          className={`dax-btn-icon p-1.5 rounded-md text-slate-400 ${meta.clase} ${
            conTexto ? 'inline-flex items-center gap-1.5 px-2.5 text-[11px] font-semibold' : ''
          }`}
          title={meta.etiqueta}
          aria-label={`${meta.etiqueta} — ${product.name}`}
        >
          <i className={`fa-solid ${meta.icono}`} />
          {conTexto && <span>{meta.etiqueta}</span>}
        </button>
      )
    })

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <div className="flex items-center gap-3">
            <i className="fa-solid fa-book text-indigo-400 text-xl" />
            <h1 className="text-2xl font-black text-white">Catálogo</h1>
          </div>
          <p className="text-slate-500 text-xs mt-0.5">
            Gestión completa de productos · {org?.name ?? 'Organización'}
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <Link
            to="/admin/products/new"
            className="dax-btn-primary dax-btn-icon text-xs inline-flex items-center gap-1.5 whitespace-nowrap"
          >
            <i className="fa-solid fa-plus" /> Nuevo producto
          </Link>
          <button
            onClick={handleExport}
            className="dax-btn-secondary dax-btn-icon text-xs inline-flex items-center gap-1.5 whitespace-nowrap"
            title="Exportar catálogo filtrado a Excel"
          >
            <i className="fa-solid fa-file-excel text-emerald-400" /> Exportar
          </button>
          <Link
            to="/products"
            className="dax-btn-secondary dax-btn-icon text-xs inline-flex items-center gap-1.5 whitespace-nowrap"
            title="Vista completa con import, packaging y precios escalonados"
          >
            <i className="fa-solid fa-layer-group" /> Vista completa
          </Link>
        </div>
      </div>

      {/* KPIs */}
      <CatalogKpis
        data={kpis}
        loading={kpisLoading}
        onFilterPending={() => setApproval('PENDING')}
        onFilterNoBranch={() => setNoBranchOnly(true)}
      />

      {/* Filtros */}
      <DaxCard>
        <div className="flex flex-wrap gap-3 items-end">
          <div className="flex-1 basis-full sm:basis-0 sm:min-w-[200px]">
            <label className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-1 block">
              Buscar
            </label>
            <div className="relative">
              <i className="fa-solid fa-magnifying-glass absolute left-3 top-1/2 -translate-y-1/2 text-slate-600 text-xs" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Nombre, SKU, código de barras..."
                className="w-full pl-9 pr-3 py-2 rounded-lg bg-slate-900/40 border border-slate-700 text-sm text-white focus:outline-none focus:border-indigo-500"
              />
            </div>
          </div>

          <div className="flex-1 basis-[calc(50%-0.375rem)] sm:flex-initial sm:basis-auto sm:min-w-[150px]">
            <label className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-1 block">
              Departamento
            </label>
            <select
              value={deptId}
              onChange={(e) => setDeptId(e.target.value)}
              className="w-full px-3 py-2 rounded-lg bg-slate-900/40 border border-slate-700 text-sm text-white focus:outline-none focus:border-indigo-500"
            >
              <option value="">Todos</option>
              {departments.map((d) => (
                <option key={d.id} value={d.id}>{d.name}</option>
              ))}
            </select>
          </div>

          <div className="flex-1 basis-[calc(50%-0.375rem)] sm:flex-initial sm:basis-auto sm:min-w-[150px]">
            <label className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-1 block">
              Marca
            </label>
            <select
              value={brandId}
              onChange={(e) => setBrandId(e.target.value)}
              className="w-full px-3 py-2 rounded-lg bg-slate-900/40 border border-slate-700 text-sm text-white focus:outline-none focus:border-indigo-500"
            >
              <option value="">Todas</option>
              {brands.map((b) => (
                <option key={b.id} value={b.id}>{b.name}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-1 block">
              Aprobación
            </label>
            <div className="flex flex-wrap rounded-lg bg-slate-900/40 border border-slate-700 p-0.5">
              {(['ALL', 'PENDING', 'APPROVED', 'REJECTED'] as ApprovalFilter[]).map((a) => (
                <button
                  key={a}
                  onClick={() => setApproval(a)}
                  className={`flex-1 sm:flex-none min-h-[44px] sm:min-h-0 px-3 py-1.5 rounded-md text-[11px] font-bold uppercase tracking-wider transition ${
                    approval === a ? 'bg-indigo-500 text-white' : 'text-slate-500 hover:text-white'
                  }`}
                >
                  {a === 'ALL' ? 'Todos' : a === 'PENDING' ? 'Pend.' : a === 'APPROVED' ? 'OK' : 'Rech.'}
                </button>
              ))}
            </div>
          </div>

          {noBranchOnly && (
            <button
              onClick={() => setNoBranchOnly(false)}
              className="text-[11px] font-bold text-fuchsia-300 hover:text-white inline-flex items-center gap-1.5 py-2"
              title="Quitar filtro"
            >
              <i className="fa-solid fa-xmark" /> Sin sucursal
            </button>
          )}

          <label className="inline-flex items-center gap-2 text-xs text-slate-400 select-none py-2">
            <input
              type="checkbox"
              checked={includeArchived}
              onChange={(e) => setIncludeArchived(e.target.checked)}
              className="w-3.5 h-3.5 accent-indigo-500"
            />
            Incluir archivados
          </label>
        </div>
      </DaxCard>

      {/* List */}
      {loading && products.length === 0 ? (
        <Spinner text="Cargando catálogo..." />
      ) : products.length === 0 ? (
        <DaxCard>
          <div className="p-12 text-center text-slate-500">
            <i className="fa-solid fa-box-open text-3xl mb-3 text-slate-700" />
            <p>No hay productos que coincidan con los filtros.</p>
          </div>
        </DaxCard>
      ) : (
        <DaxCard padding={!enTarjetas}>
          {enTarjetas ? (
            /* Una tarjeta por producto: nombre + marca de titular, SKU,
               departamento, precio y los dos distintivos; las acciones,
               rotuladas y envolviendo, debajo. */
            <div className="divide-y divide-slate-800/60">
              {products.map((p) => (
                <div key={p.id} className="p-3 space-y-2">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="font-semibold text-white break-words">{p.name}</p>
                      {p.brand_name && <p className="text-[11px] text-slate-500">{p.brand_name}</p>}
                    </div>
                    <span className="tabular-nums text-emerald-400 font-semibold whitespace-nowrap">
                      {formatCurrency(p.price)}
                    </span>
                  </div>
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-400">
                    <span className="tabular-nums">{p.sku || '—'}</span>
                    <span>{p.department_name || '—'}</span>
                    <BranchBadge count={p.branch_statuses?.filter((s) => s.is_active_pos).length ?? 0} total={p.branch_statuses?.length ?? 0} />
                    <ApprovalBadge status={p.approval_status || 'APPROVED'} active={p.is_active} />
                  </div>
                  <div className="flex flex-wrap gap-1.5">{botonesDeAcciones(p, true)}</div>
                </div>
              ))}
            </div>
          ) : (
          <TablaDesplazable sangrado={false}>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-[10px] font-bold text-slate-500 uppercase tracking-widest border-b border-slate-800">
                  <th className="text-left py-2 px-3">Producto</th>
                  <th className="text-left py-2 px-3">SKU</th>
                  <th className="text-left py-2 px-3">Departamento</th>
                  <th className="text-right py-2 px-3">Precio</th>
                  <th className="text-center py-2 px-3">Sucursales</th>
                  <th className="text-center py-2 px-3">Estado</th>
                  <th className="text-right py-2 px-3">Acciones</th>
                </tr>
              </thead>
              <tbody>
                {products.map((p) => (
                  <tr key={p.id} className="border-b border-slate-800/40 hover:bg-slate-800/30 transition">
                    <td className="py-2.5 px-3">
                      <div className="font-semibold text-white truncate max-w-[280px]">{p.name}</div>
                      {p.brand_name && (
                        <div className="text-[11px] text-slate-500">{p.brand_name}</div>
                      )}
                    </td>
                    <td className="py-2.5 px-3 text-slate-400 tabular-nums text-xs">{p.sku || '—'}</td>
                    <td className="py-2.5 px-3 text-slate-400 text-xs">{p.department_name || '—'}</td>
                    <td className="py-2.5 px-3 text-right tabular-nums text-emerald-400 font-semibold">
                      {formatCurrency(p.price)}
                    </td>
                    <td className="py-2.5 px-3 text-center">
                      <BranchBadge count={p.branch_statuses?.filter((s) => s.is_active_pos).length ?? 0} total={p.branch_statuses?.length ?? 0} />
                    </td>
                    <td className="py-2.5 px-3 text-center">
                      <ApprovalBadge status={p.approval_status || 'APPROVED'} active={p.is_active} />
                    </td>
                    <td className="py-2.5 px-3 text-right">
                      <div className="inline-flex gap-1">{botonesDeAcciones(p, false)}</div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TablaDesplazable>
          )}

          {pages > 1 && (
            <div className="flex items-center justify-between pt-4 mt-3 border-t border-slate-800">
              <p className="text-xs text-slate-500">
                Página {page + 1} de {pages} · {total.toLocaleString('es-MX')} productos
              </p>
              <div className="inline-flex gap-1">
                <button
                  onClick={() => { const np = Math.max(0, page - 1); setPage(np); loadList(np) }}
                  disabled={page === 0}
                  className="px-3 py-1.5 rounded-md text-xs font-semibold bg-slate-800 text-slate-300 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-slate-700"
                >
                  ← Anterior
                </button>
                <button
                  onClick={() => { const np = Math.min(pages - 1, page + 1); setPage(np); loadList(np) }}
                  disabled={page >= pages - 1}
                  className="px-3 py-1.5 rounded-md text-xs font-semibold bg-slate-800 text-slate-300 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-slate-700"
                >
                  Siguiente →
                </button>
              </div>
            </div>
          )}
        </DaxCard>
      )}

      {matrixProduct && (
        <ProductBranchMatrix
          product={matrixProduct}
          onClose={() => setMatrixProduct(null)}
          onSaved={() => { loadList(page); loadKpis() }}
        />
      )}

      {auditProduct && (
        <ProductAuditDrawer
          product={auditProduct}
          onClose={() => setAuditProduct(null)}
        />
      )}
    </div>
  )
}

function BranchBadge({ count, total }: { count: number; total: number }) {
  if (total === 0) {
    return <span className="text-[11px] font-semibold text-fuchsia-400">Sin sucursal</span>
  }
  const pct = total > 0 ? (count / total) * 100 : 0
  return (
    <span
      className={`inline-flex items-center gap-1 text-[11px] font-semibold tabular-nums ${
        pct === 100 ? 'text-emerald-400' : pct === 0 ? 'text-slate-500' : 'text-amber-400'
      }`}
    >
      <i className="fa-solid fa-store text-[10px]" />
      {count}/{total}
    </span>
  )
}

function ApprovalBadge({ status, active }: { status: string; active: boolean }) {
  if (!active) {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-slate-700/40 border border-slate-600/40 text-[10px] font-bold text-slate-400">
        Archivado
      </span>
    )
  }
  const config: Record<string, { bg: string; border: string; text: string; label: string }> = {
    APPROVED: { bg: 'bg-emerald-500/15', border: 'border-emerald-500/30', text: 'text-emerald-300', label: 'Aprobado' },
    PENDING:  { bg: 'bg-amber-500/15',   border: 'border-amber-500/30',   text: 'text-amber-300',   label: 'Pendiente' },
    REJECTED: { bg: 'bg-rose-500/15',    border: 'border-rose-500/30',    text: 'text-rose-300',    label: 'Rechazado' },
  }
  const c = config[status] || config.APPROVED
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full ${c.bg} border ${c.border} text-[10px] font-bold ${c.text}`}>
      {c.label}
    </span>
  )
}
