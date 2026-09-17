import { useEffect, useState, useCallback } from 'react'
import { returnsApi, type ReturnDocument, type ReturnStatus, returnLabel, returnRequestedBy, returnApprovedBy, returnBranchName } from '../../api/returns'
import { organizationApi, type Branch } from '../../api/organization'
import { useAuthStore } from '../../store/authStore'
import { toast } from '../../store/toastStore'
import { DaxCard } from '../../components/ui/DaxCard'
import { Badge } from '../../components/ui/Badge'
import { Spinner } from '../../components/ui/Spinner'
import { formatCurrency } from '../../utils/currency'

// Extrae el detail del backend (FastAPI standard `{detail: "..."}`) y cae
// a un fallback si la respuesta no lo trae. Sin esto, errores 409/422 con
// mensajes accionables ("cambia método de reembolso a STORE_CREDIT…")
// quedaban escondidos detrás de un `alert("Error al aprobar")` genérico.
function serverDetail(err: any, fallback: string): string {
  const detail = err?.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  return fallback
}

const CAN_APPROVE = ['ADMINISTRADOR', 'DUEÑO', 'GERENTE']

export function HQReturns() {
  const { user } = useAuthStore()
  const canApprove = CAN_APPROVE.includes(user?.role ?? '')

  const [tab, setTab] = useState<'pending' | 'history'>('pending')
  const [pending, setPending] = useState<ReturnDocument[]>([])
  const [history, setHistory] = useState<ReturnDocument[]>([])
  const [branches, setBranches] = useState<Branch[]>([])
  const [branchId, setBranchId] = useState<number | ''>('')
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<ReturnDocument | null>(null)
  const [actionLoading, setActionLoading] = useState(false)

  const loadData = useCallback(async (bid: number | '') => {
    setLoading(true)
    try {
      const params: { status?: ReturnStatus; branch_id?: number } = {}
      if (bid) params.branch_id = bid as number
      const [pendingData, historyData] = await Promise.all([
        returnsApi.list({ ...params, status: 'PENDING' }),
        returnsApi.list(params),
      ])
      setPending(pendingData)
      setHistory(historyData)
    } catch {
      setPending([]); setHistory([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    organizationApi.getBranches().then(setBranches).catch(() => {})
    loadData('')
  }, [])

  const handleApprove = async (id: string, force = false) => {
    setActionLoading(true)
    try {
      await returnsApi.approve(id, force)
      await loadData(branchId)
      setSelected(null)
      toast.success('Devolución aprobada')
    } catch (err) {
      const detail = serverDetail(err, 'Error al aprobar la devolución')
      if (!force && /EFECTIVO de monto alto|force=True/i.test(detail)) {
        if (window.confirm(`${detail}\n\n¿Confirmas el reembolso en efectivo?`)) {
          setActionLoading(false)
          return handleApprove(id, true)
        }
      } else {
        toast.error(detail)
      }
    } finally { setActionLoading(false) }
  }

  const [rejectingId, setRejectingId] = useState<string | null>(null)
  const [rejectReason, setRejectReason] = useState('')

  const handleReject = async (id: string, reason?: string) => {
    setActionLoading(true)
    try {
      await returnsApi.reject(id, reason)
      await loadData(branchId)
      setSelected(null)
      setRejectingId(null)
      setRejectReason('')
      toast.success('Devolución rechazada')
    } catch (err) {
      toast.error(serverDetail(err, 'Error al rechazar la devolución'))
    } finally { setActionLoading(false) }
  }

  const statusVariant = (s: ReturnStatus) =>
    s === 'APPROVED' ? 'green' : s === 'REJECTED' ? 'red' : 'yellow'

  const items = tab === 'pending' ? pending : history

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <i className="fa-solid fa-undo text-indigo-400 text-xl" />
          <h1 className="text-2xl font-black text-white">Devoluciones HQ</h1>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={branchId}
            onChange={(e) => { const v = e.target.value ? Number(e.target.value) : ''; setBranchId(v); loadData(v) }}
            className="dax-input text-xs max-w-[160px]">
            <option value="">Todas las sucursales</option>
            {branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
          </select>
          <button onClick={() => loadData(branchId)} className="dax-btn-secondary text-xs">
            <i className="fa-solid fa-rotate-right" /> Actualizar
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-slate-800/50 p-1 rounded-lg w-fit">
        {(['pending', 'history'] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-1.5 rounded-md text-sm font-semibold transition-colors ${
              tab === t ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-white'
            }`}>
            {t === 'pending' ? (
              <>Pendientes {pending.length > 0 && <span className="ml-1.5 bg-red-500 text-white text-[10px] font-black px-1.5 py-0.5 rounded-full">{pending.length}</span>}</>
            ) : 'Historial'}
          </button>
        ))}
      </div>

      <DaxCard padding={false}>
        {loading ? <Spinner text="Cargando..." /> : items.length === 0 ? (
          <div className="p-12 text-center text-slate-600">
            {tab === 'pending' ? 'No hay devoluciones pendientes' : 'Sin historial'}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="dax-table w-full">
              <thead>
                <tr>
                  <th>Ticket</th>
                  <th>Sucursal</th>
                  <th>Solicitó</th>
                  <th>Fecha</th>
                  <th>Motivo</th>
                  <th className="text-right">Total</th>
                  <th>Estado</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {items.map((r) => (
                  <tr key={r.id}>
                    <td className="font-mono text-indigo-400 text-xs">{returnLabel(r)}</td>
                    <td className="text-xs text-slate-400">{returnBranchName(r) ?? '—'}</td>
                    <td className="text-sm">{returnRequestedBy(r)}</td>
                    <td className="text-xs text-slate-400">
                      {new Date(r.created_at).toLocaleDateString('es-MX', { day: '2-digit', month: 'short' })}
                    </td>
                    <td className="text-xs max-w-[140px] truncate">{r.reason}</td>
                    <td className="text-right font-semibold text-red-400">{formatCurrency(r.total_refunded)}</td>
                    <td><Badge variant={statusVariant(r.status)}>{r.status}</Badge></td>
                    <td>
                      <button onClick={() => setSelected(r)} className="dax-btn-icon text-slate-500 hover:text-white text-xs">
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

      {/* Modal detalle */}
      {selected && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm" onClick={() => setSelected(null)}>
          <div className="dax-card p-6 w-full max-w-lg max-h-[80vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-black text-white">Detalle de Devolución</h3>
              <button onClick={() => setSelected(null)} className="dax-btn-icon text-slate-500 hover:text-white"><i className="fa-solid fa-xmark text-lg" /></button>
            </div>

            <div className="space-y-2 text-sm mb-4">
              <div className="flex justify-between"><span className="text-slate-500">Ticket</span><span className="font-mono text-indigo-400">{returnLabel(selected)}</span></div>
              <div className="flex justify-between"><span className="text-slate-500">Sucursal</span><span>{returnBranchName(selected) ?? '—'}</span></div>
              <div className="flex justify-between"><span className="text-slate-500">Solicitó</span><span>{returnRequestedBy(selected)}</span></div>
              <div className="flex justify-between"><span className="text-slate-500">Motivo</span><span className="text-right max-w-[60%]">{selected.reason}</span></div>
              <div className="flex justify-between"><span className="text-slate-500">Estado</span><Badge variant={statusVariant(selected.status)}>{selected.status}</Badge></div>
              {selected.supervisor && <div className="flex justify-between"><span className="text-slate-500">Aprobó</span><span>{returnApprovedBy(selected)}</span></div>}
            </div>

            {selected.items?.length > 0 && (
              <div className="border-t border-slate-700/50 pt-4 mb-4">
                <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2">Artículos</p>
                <table className="dax-table w-full text-xs">
                  <thead><tr><th>Producto</th><th className="text-right">Cant.</th><th className="text-right">Reembolso</th><th>Stock</th></tr></thead>
                  <tbody>
                    {selected.items.map((item, i) => (
                      <tr key={i}>
                        <td>{item.variant?.product_name ?? item.variant?.sku ?? '—'}</td>
                        <td className="text-right">{item.quantity}</td>
                        <td className="text-right text-red-400">{formatCurrency(Number(item.refund_amount))}</td>
                        <td><Badge variant={item.is_inventory_reentry ? 'green' : 'red'}>{item.is_inventory_reentry ? 'Regresa' : 'Merma'}</Badge></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            <div className="flex justify-between font-black text-white border-t border-slate-700/50 pt-3">
              <span>Total reembolso</span><span className="text-red-400">{formatCurrency(selected.total_refunded)}</span>
            </div>

            {canApprove && selected.status === 'PENDING' && (
              <div className="flex gap-2 mt-4">
                <button onClick={() => handleApprove(selected.id)} disabled={actionLoading} className="dax-btn-primary flex-1 justify-center">
                  {actionLoading ? <i className="fa-solid fa-spinner fa-spin" /> : <><i className="fa-solid fa-check" /> Aprobar</>}
                </button>
                <button onClick={() => { setRejectingId(selected.id); setRejectReason('') }} disabled={actionLoading} className="dax-btn-danger flex-1 justify-center">
                  <i className="fa-solid fa-xmark" /> Rechazar
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Modal de rechazo con motivo */}
      {rejectingId && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm" onClick={() => setRejectingId(null)}>
          <div className="dax-card p-5 w-full max-w-sm" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-base font-black mb-3" style={{ color: 'var(--dax-text)' }}>
              <i className="fa-solid fa-circle-exclamation mr-2 text-red-500" />
              Rechazar devolución
            </h3>
            <label className="text-[10px] font-bold uppercase tracking-wider block mb-1" style={{ color: 'var(--dax-text-muted)' }}>
              Motivo (opcional)
            </label>
            <textarea
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              className="dax-input w-full"
              rows={3}
              placeholder="Ej: Producto fuera de plazo de devolución, ticket duplicado..."
              autoFocus
            />
            <div className="flex gap-2 mt-4">
              <button onClick={() => setRejectingId(null)} className="dax-btn-secondary flex-1" disabled={actionLoading}>
                Cancelar
              </button>
              <button
                onClick={() => handleReject(rejectingId, rejectReason.trim() || undefined)}
                className="dax-btn-danger flex-1 justify-center"
                disabled={actionLoading}
              >
                {actionLoading ? <i className="fa-solid fa-spinner fa-spin" /> : <><i className="fa-solid fa-xmark" /> Confirmar rechazo</>}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
