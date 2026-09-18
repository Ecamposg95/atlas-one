import { useCallback, useEffect, useMemo, useState } from 'react'
import { productsApi, type BranchStatusPatch } from '../../api/products'
import { planBranchStatusWrites } from './branchFanout'
import { grupoDeVariantes } from '../../pages/inventory/variantRows'
import { organizationApi, type Branch } from '../../api/organization'
import { Spinner } from '../ui/Spinner'
import { TablaDesplazable } from '../ui/TablaDesplazable'
import { toast } from '../../store/toastStore'
import type { Product, ProductBranchStatus } from '../../types/products'
import { formatCurrency } from '../../utils/currency'

interface Props {
  product: Product
  onClose: () => void
  onSaved?: () => void
}

export function ProductBranchMatrix({ product, onClose, onSaved }: Props) {
  // `product.variants` ya viene sin las retiradas (el backend filtra
  // `deleted_at`), así que son las tallas vivas. La primera es la principal:
  // es la que el backend usa para el PBS que se lee, pero lo que se ESCRIBE
  // va a todas (ver `planBranchStatusWrites`).
  const variantes = useMemo(() => product.variants ?? [], [product.variants])
  const variant = variantes[0]
  const variasTallas = variantes.length > 1

  const [branches, setBranches] = useState<Branch[]>([])
  const [pbsRows, setPbsRows] = useState<ProductBranchStatus[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [cloneFrom, setCloneFrom] = useState<number | ''>('')
  const [cloneOverwrite, setCloneOverwrite] = useState(false)

  const load = useCallback(async () => {
    if (!product.id) return
    setLoading(true)
    try {
      const [brs, pbs] = await Promise.all([
        organizationApi.getBranches(),
        productsApi.getBranchStatuses(product.id),
      ])
      setBranches(brs.filter((b: Branch) => b.is_active))
      setPbsRows(pbs)
    } catch (e: any) {
      const detail = e?.response?.data?.detail
      toast.error(typeof detail === 'string' ? detail : 'No se pudo cargar la matriz.')
    } finally {
      setLoading(false)
    }
  }, [product.id])

  useEffect(() => { load() }, [load])

  const pbsByBranch = useMemo(() => {
    const m = new Map<number, ProductBranchStatus>()
    for (const r of pbsRows) m.set(r.branch_id, r)
    return m
  }, [pbsRows])

  const activeCount = useMemo(
    () => pbsRows.filter((r) => r.is_active_pos).length,
    [pbsRows],
  )

  const saveCell = async (branchId: number, patch: BranchStatusPatch) => {
    if (!variant) return
    // Dinero: el cambio aplica a TODAS las tallas vivas, no solo a la
    // principal. Antes, apagar el POS o fijar un precio de sucursal dejaba
    // M y G vendiéndose al precio viejo.
    const plan = planBranchStatusWrites(variantes.map((v) => v.id), patch)
    setSaving(true)
    try {
      if (plan.bulk) {
        await productsApi.bulkToggleBranchStatus({
          variant_ids: plan.bulk.variantIds,
          branch_ids: [branchId],
          is_active_pos: plan.bulk.isActivePos,
        })
      }
      if (plan.patches) {
        for (const vid of plan.patches.variantIds) {
          await productsApi.updateBranchStatus(vid, plan.patches.patch, branchId)
        }
      }
      await load()
      onSaved?.()
    } catch (e: any) {
      const detail = e?.response?.data?.detail
      toast.error(typeof detail === 'string' ? detail : 'Error al guardar cambios.')
    } finally {
      setSaving(false)
    }
  }

  const bulkEnableAll = async (enable: boolean) => {
    if (!variant) return
    const branchIds = branches.map((b) => b.id)
    if (!branchIds.length) return
    if (!window.confirm(
      enable
        ? `¿Activar este producto en las ${branchIds.length} sucursales?`
        : `¿Desactivar en las ${branchIds.length} sucursales?`,
    )) return
    setSaving(true)
    try {
      const res = await productsApi.bulkToggleBranchStatus({
        variant_ids: (product.variants ?? []).map((v) => v.id),
        branch_ids: branchIds,
        is_active_pos: enable,
      })
      toast.success(`${res.updated_records} sucursales ${enable ? 'activadas' : 'desactivadas'}.`)
      await load()
      onSaved?.()
    } catch (e: any) {
      const detail = e?.response?.data?.detail
      toast.error(typeof detail === 'string' ? detail : 'Error en acción masiva.')
    } finally {
      setSaving(false)
    }
  }

  const cloneFromBranch = async () => {
    if (!variant || cloneFrom === '' || cloneFrom === null) return
    const to_branch_ids = branches.map((b) => b.id).filter((id) => id !== cloneFrom)
    if (!to_branch_ids.length) {
      toast.error('No hay sucursales destino.')
      return
    }
    if (!window.confirm(
      `Replicar config de ${branches.find((b) => b.id === cloneFrom)?.name ?? 'origen'} a las otras ${to_branch_ids.length} sucursales${cloneOverwrite ? ' (pisar existentes)' : ''}?`,
    )) return
    setSaving(true)
    try {
      const res = await productsApi.cloneBranchStatus({
        from_branch_id: Number(cloneFrom),
        to_branch_ids,
        variant_ids: (product.variants ?? []).map((v) => v.id),
        overwrite: cloneOverwrite,
      })
      toast.success(`Clonado: ${res.created} nuevas, ${res.updated} actualizadas, ${res.skipped} sin cambios.`)
      await load()
      onSaved?.()
    } catch (e: any) {
      const detail = e?.response?.data?.detail
      toast.error(typeof detail === 'string' ? detail : 'Error al clonar configuración.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end"
      style={{ background: 'rgba(0,0,0,0.55)' }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <aside
        className="h-full w-full max-w-3xl overflow-y-auto"
        style={{ background: 'var(--dax-surface)', borderLeft: '1px solid var(--dax-border)' }}
      >
        {/* Header */}
        <div className="sticky top-0 z-10 px-5 py-4 border-b" style={{
          background: 'var(--dax-surface)', borderColor: 'var(--dax-border-dim)',
        }}>
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="flex items-center gap-2">
                <i className="fa-solid fa-store text-indigo-400" />
                <h2 className="text-lg font-bold text-white">Matriz de Sucursales</h2>
              </div>
              <p className="text-xs text-slate-500 mt-1 truncate max-w-[420px]">
                {product.name} · SKU <span className="font-mono">{variant?.sku ?? '—'}</span>
              </p>
              {variasTallas && (
                <p className="text-[11px] text-slate-400 mt-1">
                  Lo que cambies aquí se aplica a las {variantes.length} {grupoDeVariantes(variantes)} del producto.
                </p>
              )}
            </div>
            <button
              onClick={onClose}
              className="p-2 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800"
              title="Cerrar"
            >
              <i className="fa-solid fa-xmark text-xl" />
            </button>
          </div>
        </div>

        <div className="p-5 space-y-4">
          {/* Summary chip */}
          <div className="flex items-center justify-between flex-wrap gap-3">
            <div className="text-sm text-slate-400">
              Activo en{' '}
              <span className={`font-bold ${activeCount === branches.length ? 'text-emerald-400' : activeCount === 0 ? 'text-rose-400' : 'text-amber-400'}`}>
                {activeCount}/{branches.length}
              </span>{' '}
              sucursales
            </div>
            <div className="inline-flex gap-2">
              <button
                onClick={() => bulkEnableAll(true)}
                disabled={saving || branches.length === 0}
                className="text-xs px-3 py-1.5 rounded-md bg-emerald-600/15 text-emerald-300 border border-emerald-600/30 hover:bg-emerald-600/25 disabled:opacity-50"
              >
                <i className="fa-solid fa-check mr-1" /> Activar todas
              </button>
              <button
                onClick={() => bulkEnableAll(false)}
                disabled={saving || branches.length === 0}
                className="text-xs px-3 py-1.5 rounded-md bg-rose-600/15 text-rose-300 border border-rose-600/30 hover:bg-rose-600/25 disabled:opacity-50"
              >
                <i className="fa-solid fa-ban mr-1" /> Desactivar todas
              </button>
            </div>
          </div>

          {/* Clone from branch */}
          <div className="rounded-xl border border-slate-700 p-3 bg-slate-900/30">
            <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2">
              Replicar configuración
            </p>
            <div className="flex items-end gap-2 flex-wrap">
              <div className="flex-1 min-w-[180px]">
                <label className="text-xs text-slate-400 block mb-1">Copiar desde</label>
                <select
                  value={cloneFrom}
                  onChange={(e) => setCloneFrom(e.target.value === '' ? '' : Number(e.target.value))}
                  className="w-full px-3 py-2 rounded-lg bg-slate-900/60 border border-slate-700 text-sm text-white focus:outline-none focus:border-indigo-500"
                >
                  <option value="">Seleccionar sucursal origen…</option>
                  {branches
                    .filter((b) => pbsByBranch.get(b.id))
                    .map((b) => (
                      <option key={b.id} value={b.id}>
                        {b.name} ({pbsByBranch.get(b.id)?.is_active_pos ? 'activa' : 'inactiva'})
                      </option>
                    ))}
                </select>
              </div>
              <label className="inline-flex items-center gap-2 text-xs text-slate-400 select-none">
                <input
                  type="checkbox"
                  checked={cloneOverwrite}
                  onChange={(e) => setCloneOverwrite(e.target.checked)}
                  className="w-3.5 h-3.5 accent-indigo-500"
                />
                Pisar config existente
              </label>
              <button
                onClick={cloneFromBranch}
                disabled={saving || cloneFrom === ''}
                className="text-xs px-3 py-2 rounded-lg bg-indigo-600 text-white hover:bg-indigo-500 disabled:opacity-50"
              >
                <i className="fa-solid fa-copy mr-1" /> Replicar
              </button>
            </div>
          </div>

          {/* Matrix table */}
          {loading ? (
            <Spinner text="Cargando sucursales..." />
          ) : branches.length === 0 ? (
            <p className="text-sm text-slate-500 py-6 text-center">
              No hay sucursales configuradas en esta organización.
            </p>
          ) : (
            <div className="rounded-xl border border-slate-800 overflow-hidden">
              <TablaDesplazable>
                <table className="w-full text-sm">
                  <thead className="bg-slate-900/40">
                    <tr className="text-[10px] font-bold text-slate-500 uppercase tracking-widest border-b border-slate-800">
                      <th className="text-left py-2 px-3">Sucursal</th>
                      <th className="text-center py-2 px-3">POS</th>
                      <th className="text-right py-2 px-3">Precio override</th>
                      <th className="text-right py-2 px-3">Stock mín / máx</th>
                    </tr>
                  </thead>
                  <tbody>
                    {branches.map((b) => {
                      const pbs = pbsByBranch.get(b.id)
                      return (
                        <BranchRow
                          key={b.id}
                          branch={b}
                          pbs={pbs}
                          variantPrice={variant?.price ?? 0}
                          disabled={saving}
                          onToggle={(val) => saveCell(b.id, { is_active_pos: val })}
                          onPriceOverride={(val) => saveCell(b.id, { price_override: val })}
                          onMinStock={(val) => saveCell(b.id, { min_stock_alert: val })}
                          onMaxStock={(val) => saveCell(b.id, { max_stock_limit: val })}
                        />
                      )
                    })}
                  </tbody>
                </table>
              </TablaDesplazable>
            </div>
          )}
        </div>
      </aside>
    </div>
  )
}

interface RowProps {
  branch: Branch
  pbs: ProductBranchStatus | undefined
  variantPrice: number
  disabled: boolean
  onToggle: (val: boolean) => void
  onPriceOverride: (val: number | null) => void
  onMinStock: (val: number | null) => void
  onMaxStock: (val: number | null) => void
}

function BranchRow({ branch, pbs, variantPrice, disabled, onToggle, onPriceOverride, onMinStock, onMaxStock }: RowProps) {
  const active = pbs?.is_active_pos ?? false
  const priceOverride = pbs?.price_override
  const minStock = pbs?.min_stock_alert
  const maxStock = pbs?.max_stock_limit

  return (
    <tr className="border-b border-slate-800/60 hover:bg-slate-800/20">
      <td className="py-2.5 px-3">
        <div className="flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full ${active ? 'bg-emerald-400' : pbs ? 'bg-slate-600' : 'bg-fuchsia-500'}`} />
          <span className="text-white font-semibold">{branch.name}</span>
          {branch.is_headquarters && (
            <span className="text-[9px] font-bold uppercase tracking-widest text-indigo-400">HQ</span>
          )}
          {!pbs && (
            <span className="text-[10px] text-fuchsia-400">(sin PBS)</span>
          )}
        </div>
      </td>
      <td className="py-2 px-3 text-center">
        <input
          type="checkbox"
          checked={active}
          disabled={disabled}
          onChange={(e) => onToggle(e.target.checked)}
          className="w-4 h-4 accent-emerald-500"
          title={active ? 'Desactivar en POS' : 'Activar en POS'}
        />
      </td>
      <td className="py-2 px-3 text-right">
        <NumberBlurInput
          value={priceOverride ?? null}
          placeholder={formatCurrency(variantPrice)}
          disabled={disabled || !pbs}
          onCommit={(v) => onPriceOverride(v)}
          min={0}
        />
      </td>
      <td className="py-2 px-3 text-right">
        <div className="inline-flex gap-1">
          <NumberBlurInput
            value={minStock ?? null}
            placeholder="min"
            disabled={disabled || !pbs}
            onCommit={onMinStock}
            width="w-20"
            min={0}
          />
          <NumberBlurInput
            value={maxStock ?? null}
            placeholder="max"
            disabled={disabled || !pbs}
            onCommit={onMaxStock}
            width="w-20"
            min={0}
          />
        </div>
      </td>
    </tr>
  )
}

interface NumberBlurInputProps {
  value: number | null
  placeholder: string
  disabled: boolean
  onCommit: (v: number | null) => void
  min?: number
  width?: string
}

function NumberBlurInput({ value, placeholder, disabled, onCommit, min, width = 'w-28' }: NumberBlurInputProps) {
  const [local, setLocal] = useState(value !== null ? String(value) : '')

  useEffect(() => {
    setLocal(value !== null ? String(value) : '')
  }, [value])

  const commit = () => {
    if (local === '') {
      if (value !== null) onCommit(null)
      return
    }
    const n = Number(local)
    if (!Number.isFinite(n)) {
      setLocal(value !== null ? String(value) : '')
      return
    }
    if (min != null && n < min) {
      setLocal(value !== null ? String(value) : '')
      return
    }
    if (n !== value) onCommit(n)
  }

  return (
    <input
      type="number"
      value={local}
      placeholder={placeholder}
      disabled={disabled}
      onChange={(e) => setLocal(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === 'Enter') (e.target as HTMLInputElement).blur()
        if (e.key === 'Escape') setLocal(value !== null ? String(value) : '')
      }}
      className={`${width} px-2 py-1 rounded-md bg-slate-900/60 border border-slate-700 text-xs text-white text-right focus:outline-none focus:border-indigo-500 disabled:opacity-40`}
    />
  )
}
