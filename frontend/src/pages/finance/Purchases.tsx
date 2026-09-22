import { useEffect, useState, useCallback } from 'react'
import { purchasesApi, type PurchaseOrder, type POStatus, type POStats, type POCreate } from '../../api/purchases'
import { DaxCard } from '../../components/ui/DaxCard'
import { Spinner } from '../../components/ui/Spinner'
import { Badge } from '../../components/ui/Badge'
import { toast } from '../../store/toastStore'
import { formatCurrency } from '../../utils/currency'

const statusVariant = (s: POStatus) =>
  s === 'RECEIVED' ? 'green' : s === 'CANCELLED' ? 'red' : s === 'DRAFT' ? 'slate' : s === 'ORDERED' ? 'blue' : 'yellow'

const STATUS_LABELS: Record<POStatus, string> = {
  DRAFT: 'Borrador', ORDERED: 'Enviada', PARTIAL: 'Parcial', RECEIVED: 'Recibida', CANCELLED: 'Cancelada'
}

interface POFormItem { product_name: string; sku: string; qty_ordered: string; unit_cost: string }

export function Purchases() {
  const [orders, setOrders] = useState<PurchaseOrder[]>([])
  const [stats, setStats] = useState<POStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [filterStatus, setFilterStatus] = useState<POStatus | ''>('')
  const [selected, setSelected] = useState<PurchaseOrder | null>(null)
  const [modal, setModal] = useState(false)
  const [supplier, setSupplier] = useState('')
  const [notes, setNotes] = useState('')
  const [poItems, setPoItems] = useState<POFormItem[]>([{ product_name: '', sku: '', qty_ordered: '1', unit_cost: '0' }])
  const [saving, setSaving] = useState(false)

  const load = useCallback(async (status?: POStatus | '') => {
    setLoading(true)
    try {
      const res = await purchasesApi.list({ status: status || undefined, limit: 100 })
      setOrders(res.items ?? [])
    } catch { setOrders([]) } finally { setLoading(false) }
  }, [])

  useEffect(() => {
    purchasesApi.getStats().then(setStats).catch(() => {})
    load()
  }, [])

  const handleCreate = async () => {
    if (!supplier || poItems.every((i) => !i.product_name)) return
    setSaving(true)
    try {
      const payload: POCreate = {
        supplier_name: supplier,
        notes: notes || undefined,
        lines: poItems.filter((i) => i.product_name).map((i) => ({
          product_name: i.product_name, sku: i.sku || undefined,
          qty_ordered: parseInt(i.qty_ordered) || 1, unit_cost: parseFloat(i.unit_cost) || 0,
        })),
      }
      await purchasesApi.create(payload)
      setModal(false); setSupplier(''); setNotes(''); setPoItems([{ product_name: '', sku: '', qty_ordered: '1', unit_cost: '0' }])
      purchasesApi.getStats().then(setStats).catch(() => {})
      load(filterStatus)
    } catch { toast.error('Error al crear la orden de compra') } finally { setSaving(false) }
  }

  const handleStatusChange = async (id: number, status: POStatus) => {
    try {
      await purchasesApi.updateStatus(id, status)
      load(filterStatus)
      if (selected?.id === id) {
        const updated = await purchasesApi.getById(id)
        setSelected(updated)
      }
    } catch { toast.error('Error al cambiar el estado de la orden') }
  }

  const handleReceive = async (po: PurchaseOrder) => {
    try {
      const lines = (po.lines ?? []).map((l) => ({ line_id: l.id, qty_received: l.qty_ordered }))
      await purchasesApi.receive(po.id, lines)
      load(filterStatus)
      setSelected(null)
    } catch { toast.error('Error al recibir la orden de compra') }
  }

  const addItem = () => setPoItems((prev) => [...prev, { product_name: '', sku: '', qty_ordered: '1', unit_cost: '0' }])
  const removeItem = (i: number) => setPoItems((prev) => prev.filter((_, idx) => idx !== i))
  const updateItem = (i: number, field: keyof POFormItem, val: string) =>
    setPoItems((prev) => prev.map((item, idx) => idx === i ? { ...item, [field]: val } : item))

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <i className="fa-solid fa-shopping-cart text-indigo-400 text-xl" />
          <h1 className="text-2xl font-black text-white">Compras</h1>
        </div>
        <button onClick={() => setModal(true)} className="dax-btn-primary text-xs">
          <i className="fa-solid fa-plus" /> Nueva OC
        </button>
      </div>

      {/* KPIs */}
      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[
            { label: 'Este mes', value: formatCurrency(stats.total_month), icon: 'fa-calendar', color: 'text-indigo-400' },
            { label: 'OC activas', value: String(stats.active_orders), icon: 'fa-clock', color: 'text-amber-400' },
            { label: 'Total histórico', value: formatCurrency(stats.total_historic), icon: 'fa-coins', color: 'text-white' },
            { label: 'Proveedor top', value: stats.top_supplier ?? '—', icon: 'fa-truck', color: 'text-slate-300' },
          ].map((k) => (
            <DaxCard key={k.label}>
              <div className="flex items-center gap-2 mb-1">
                <i className={`fa-solid ${k.icon} text-slate-500 text-xs`} />
                <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">{k.label}</p>
              </div>
              <p className={`text-xl font-black tabular-nums truncate ${k.color}`}>{k.value}</p>
            </DaxCard>
          ))}
        </div>
      )}

      {/* Filtro estado */}
      <div className="flex flex-wrap gap-2">
        {(['', 'DRAFT', 'ORDERED', 'PARTIAL', 'RECEIVED', 'CANCELLED'] as (POStatus | '')[]).map((s) => (
          <button key={s} onClick={() => { setFilterStatus(s); load(s) }}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${filterStatus === s ? 'bg-indigo-600 text-white' : 'bg-slate-700/50 text-slate-400 hover:text-white'}`}>
            {s ? STATUS_LABELS[s] : 'Todas'}
          </button>
        ))}
      </div>

      {/* Tabla */}
      <DaxCard padding={false}>
        {loading ? <Spinner text="Cargando órdenes..." /> : orders.length === 0 ? (
          <div className="p-12 text-center text-slate-600">Sin órdenes de compra</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="dax-table w-full">
              <thead>
                <tr>
                  <th>Folio</th>
                  <th>Proveedor</th>
                  <th>Sucursal</th>
                  <th>Fecha</th>
                  <th className="text-right">Total</th>
                  <th>Estado</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {orders.map((o) => (
                  <tr key={o.id}>
                    <td className="font-mono text-indigo-400 text-xs">{o.folio ?? `OC-${o.id}`}</td>
                    <td className="font-semibold text-white">{o.supplier_name}</td>
                    <td className="text-slate-400 text-xs">{o.branch_name ?? '—'}</td>
                    <td className="text-slate-400 text-xs">
                      {new Date(o.created_at).toLocaleDateString('es-MX', { day: '2-digit', month: 'short' })}
                    </td>
                    <td className="text-right font-semibold text-indigo-400 tabular-nums">{formatCurrency(o.total)}</td>
                    <td><Badge variant={statusVariant(o.status)}>{STATUS_LABELS[o.status]}</Badge></td>
                    <td>
                      <button onClick={() => setSelected(o)} className="text-slate-500 hover:text-white text-xs">
                        <i className="fa-solid fa-eye" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </DaxCard>

      {/* Modal detalle OC */}
      {selected && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm" onClick={() => setSelected(null)}>
          <div className="dax-card p-6 w-full max-w-lg max-h-[85vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <div>
                <p className="text-[10px] text-slate-500 uppercase tracking-widest">Orden de Compra</p>
                <p className="text-xl font-black text-indigo-400 font-mono">{selected.folio ?? `OC-${selected.id}`}</p>
              </div>
              <button onClick={() => setSelected(null)} className="text-slate-500 hover:text-white"><i className="fa-solid fa-xmark text-lg" /></button>
            </div>

            <div className="space-y-2 text-sm mb-4">
              <div className="flex justify-between"><span className="text-slate-500">Proveedor</span><span className="font-semibold">{selected.supplier_name}</span></div>
              <div className="flex justify-between"><span className="text-slate-500">Estado</span><Badge variant={statusVariant(selected.status)}>{STATUS_LABELS[selected.status]}</Badge></div>
              {selected.notes && <div className="flex justify-between"><span className="text-slate-500">Notas</span><span className="text-right max-w-[60%] text-slate-400">{selected.notes}</span></div>}
            </div>

            <table className="dax-table w-full text-xs mb-4">
              <thead><tr><th>Producto</th><th>SKU</th><th className="text-right">Cant.</th><th className="text-right">Recibido</th><th className="text-right">Costo</th></tr></thead>
              <tbody>
                {(selected.lines ?? []).map((line) => (
                  <tr key={line.id}>
                    <td>{line.product_name}</td>
                    <td className="font-mono text-slate-500">{line.sku ?? '—'}</td>
                    <td className="text-right">{line.qty_ordered}</td>
                    <td className={`text-right ${line.qty_received >= line.qty_ordered ? 'text-emerald-400' : 'text-amber-400'}`}>{line.qty_received}</td>
                    <td className="text-right">{formatCurrency(line.unit_cost)}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            <div className="flex justify-between font-black text-white border-t border-slate-700/50 pt-3 mb-4">
              <span>Total</span><span className="text-indigo-400">{formatCurrency(selected.total)}</span>
            </div>

            <div className="flex flex-wrap gap-2">
              {selected.status === 'DRAFT' && (
                <button onClick={() => handleStatusChange(selected.id, 'ORDERED')} className="dax-btn-secondary text-xs">
                  <i className="fa-solid fa-paper-plane" /> Enviar
                </button>
              )}
              {(selected.status === 'ORDERED' || selected.status === 'PARTIAL') && (
                <button onClick={() => handleReceive(selected)} className="dax-btn-primary text-xs">
                  <i className="fa-solid fa-box-open" /> Recibir mercancía
                </button>
              )}
              {selected.status !== 'CANCELLED' && selected.status !== 'RECEIVED' && (
                <button onClick={() => handleStatusChange(selected.id, 'CANCELLED')} className="dax-btn-danger text-xs">
                  <i className="fa-solid fa-xmark" /> Cancelar
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Modal nueva OC */}
      {modal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm" onClick={() => setModal(false)}>
          <div className="dax-card p-6 w-full max-w-xl max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-5">
              <h3 className="text-lg font-black text-white">Nueva Orden de Compra</h3>
              <button onClick={() => setModal(false)} className="text-slate-500 hover:text-white"><i className="fa-solid fa-xmark text-lg" /></button>
            </div>

            <div className="space-y-3 mb-4">
              <div>
                <label className="dax-label">Proveedor</label>
                <input value={supplier} onChange={(e) => setSupplier(e.target.value)} className="dax-input w-full" placeholder="Nombre del proveedor" autoFocus />
              </div>
              <div>
                <label className="dax-label">Notas (opcional)</label>
                <input value={notes} onChange={(e) => setNotes(e.target.value)} className="dax-input w-full" />
              </div>
            </div>

            <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2">Artículos</p>
            <div className="space-y-2 mb-3">
              {poItems.map((item, i) => (
                <div key={i} className="grid grid-cols-12 gap-1 items-center">
                  <input value={item.product_name} onChange={(e) => updateItem(i, 'product_name', e.target.value)}
                    placeholder="Producto" className="dax-input col-span-4 text-xs" />
                  <input value={item.sku} onChange={(e) => updateItem(i, 'sku', e.target.value)}
                    placeholder="SKU" className="dax-input col-span-2 text-xs" />
                  <input type="number" value={item.qty_ordered} onChange={(e) => updateItem(i, 'qty_ordered', e.target.value)}
                    placeholder="Cant." className="dax-input col-span-2 text-xs" />
                  <input type="number" step="0.01" value={item.unit_cost} onChange={(e) => updateItem(i, 'unit_cost', e.target.value)}
                    placeholder="Costo" className="dax-input col-span-3 text-xs" />
                  <button onClick={() => removeItem(i)} className="text-slate-600 hover:text-red-400 col-span-1 text-center">
                    <i className="fa-solid fa-xmark text-xs" />
                  </button>
                </div>
              ))}
            </div>
            <button onClick={addItem} className="dax-btn-secondary text-xs mb-4">
              <i className="fa-solid fa-plus" /> Agregar artículo
            </button>

            <div className="flex gap-2">
              <button onClick={() => setModal(false)} className="dax-btn-secondary flex-1">Cancelar</button>
              <button onClick={handleCreate} disabled={saving || !supplier} className="dax-btn-primary flex-1 justify-center disabled:opacity-40">
                {saving ? <i className="fa-solid fa-spinner fa-spin" /> : <><i className="fa-solid fa-check" /> Crear OC</>}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
