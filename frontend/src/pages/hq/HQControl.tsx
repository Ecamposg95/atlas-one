import { useEffect, useState, useCallback } from 'react'
import { reportsApi, type AuditDiscrepancy } from '../../api/reports'
import { organizationApi } from '../../api/organization'
import { DaxCard } from '../../components/ui/DaxCard'
import { Spinner } from '../../components/ui/Spinner'
import { Link } from 'react-router-dom'
import { formatCurrency } from '../../utils/currency'
import { todayStr } from '../../utils/dates'

interface AuditLogEntry {
  id: number
  action: string
  entity_type: string | null
  entity_id: string | null
  payload: string | null
  created_at: string
}

export function HQControl() {
  const [discrepancies, setDiscrepancies] = useState<AuditDiscrepancy[]>([])
  const [loading, setLoading] = useState(true)
  const [branchCount, setBranchCount] = useState<number | null>(null)
  const [revenue, setRevenue] = useState<number | null>(null)
  const [tickets, setTickets] = useState<number | null>(null)
  const [alertCount, setAlertCount] = useState<number | null>(null)
  const [auditLog, setAuditLog] = useState<AuditLogEntry[]>([])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const today = todayStr()
      const [discData, branches, stats] = await Promise.allSettled([
        reportsApi.auditDiscrepancies(20),
        organizationApi.getBranches(),
        reportsApi.commandCenterStats({ start_date: today, end_date: today }),
      ])
      setDiscrepancies(discData.status === 'fulfilled' ? discData.value : [])
      if (branches.status === 'fulfilled') setBranchCount(branches.value.length)
      if (stats.status === 'fulfilled') {
        setRevenue(stats.value.global?.total_sales ?? null)
        setTickets(stats.value.global?.total_tickets ?? null)
        setAlertCount(stats.value.alerts?.length ?? 0)
      }
    } finally { setLoading(false) }
  }, [])

  const loadAuditLog = useCallback(async () => {
    try {
      const { data } = await import('../../api/client').then(m => m.default.get('/platform/audit/logs', { params: { limit: 10 } }))
      const entries = Array.isArray(data) ? data : (data as any)?.items ?? []
      setAuditLog(entries)
    } catch { setAuditLog([]) }
  }, [])

  useEffect(() => { load(); loadAuditLog() }, [load, loadAuditLog])

  const SHORTCUTS = [
    { label: 'Gestión de Usuarios', icon: 'fa-users', url: '/users', color: 'text-indigo-400' },
    { label: 'Organización', icon: 'fa-building', url: '/organization', color: 'text-blue-400' },
    { label: 'Catálogo', icon: 'fa-barcode', url: '/admin/catalog', color: 'text-emerald-400' },
    { label: 'Departamentos', icon: 'fa-tags', url: '/departments', color: 'text-amber-400' },
    { label: 'Marcas', icon: 'fa-star', url: '/brands', color: 'text-pink-400' },
    { label: 'RR.HH.', icon: 'fa-id-card', url: '/hr', color: 'text-purple-400' },
  ]

  const ACTION_COLORS: Record<string, string> = {
    CREATE: 'text-emerald-400', UPDATE: 'text-sky-400', DELETE: 'text-rose-400',
    UPDATE_ORG_INDUSTRY: 'text-amber-400', TOGGLE_MODULE: 'text-violet-400',
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <i className="fa-solid fa-sliders text-indigo-400 text-xl" />
          <h1 className="text-2xl font-black text-white">Control</h1>
        </div>
        <button onClick={() => { load(); loadAuditLog() }} className="dax-btn-secondary text-xs">
          <i className="fa-solid fa-rotate-right" /> Actualizar
        </button>
      </div>

      {/* KPI Strip */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <DaxCard>
          <p className="text-[10px] text-slate-500 uppercase font-bold tracking-wider">Sucursales</p>
          <p className="text-3xl font-black text-white mt-2 tabular-nums">{branchCount ?? '—'}</p>
          <p className="text-[10px] text-indigo-400 mt-1">Activas</p>
        </DaxCard>
        <DaxCard>
          <p className="text-[10px] text-slate-500 uppercase font-bold tracking-wider">Ventas de hoy</p>
          <p className="text-3xl font-black text-emerald-400 mt-2 tabular-nums">{revenue !== null ? formatCurrency(revenue) : '—'}</p>
          <p className="text-[10px] text-slate-500 mt-1">Acumulado del día</p>
        </DaxCard>
        <DaxCard>
          <p className="text-[10px] text-slate-500 uppercase font-bold tracking-wider">Tickets de hoy</p>
          <p className="text-3xl font-black text-sky-400 mt-2 tabular-nums">{tickets ?? '—'}</p>
          <p className="text-[10px] text-slate-500 mt-1">Transacciones</p>
        </DaxCard>
        <Link to="/hq/operations">
          <DaxCard className="hover:border-rose-500/30 cursor-pointer">
            <p className="text-[10px] text-slate-500 uppercase font-bold tracking-wider">Alertas</p>
            <p className="text-3xl font-black text-rose-400 mt-2 tabular-nums">{alertCount ?? '—'}</p>
            <p className="text-[10px] text-slate-500 mt-1">Ver operaciones →</p>
          </DaxCard>
        </Link>
      </div>

      {/* Accesos rápidos de configuración */}
      <div>
        <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-3">Configuración rápida</p>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          {SHORTCUTS.map((s) => (
            <Link key={s.url} to={s.url}
              className="dax-card p-4 flex flex-col items-center gap-2 hover:border-indigo-500/40 transition-colors text-center">
              <i className={`fa-solid ${s.icon} ${s.color} text-xl`} />
              <span className="text-xs font-semibold text-slate-300">{s.label}</span>
            </Link>
          ))}
        </div>
      </div>

      {/* Auditoría de diferencias de caja */}
      <div>
        <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-3">
          Diferencias de Caja Recientes
        </p>
        <DaxCard padding={false}>
          {loading ? <Spinner text="Cargando auditoría..." /> : discrepancies.length === 0 ? (
            <div className="p-12 text-center text-slate-600">
              <i className="fa-solid fa-check-circle text-emerald-600 text-3xl mb-3 block" />
              Sin diferencias de caja registradas
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="dax-table w-full">
                <thead>
                  <tr>
                    <th>Sucursal</th>
                    <th>Cajero</th>
                    <th className="text-right">Esperado</th>
                    <th className="text-right">Contado</th>
                    <th className="text-right">Diferencia</th>
                    <th>Fecha</th>
                  </tr>
                </thead>
                <tbody>
                  {discrepancies.map((d) => (
                    <tr key={d.session_id}>
                      <td className="text-sm font-semibold text-white">{d.branch_name}</td>
                      <td className="text-sm text-slate-400">{d.opened_by}</td>
                      <td className="text-right tabular-nums">{formatCurrency(d.expected_cash)}</td>
                      <td className="text-right tabular-nums">{formatCurrency(d.closing_amount)}</td>
                      <td className={`text-right font-bold tabular-nums ${d.difference > 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                        {d.difference > 0 ? '+' : ''}{formatCurrency(d.difference)}
                      </td>
                      <td className="text-xs text-slate-500">
                        {new Date(d.closed_at).toLocaleDateString('es-MX', { day: '2-digit', month: 'short' })}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </DaxCard>
      </div>

      {/* Actividad Reciente */}
      <div>
        <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-3">
          Actividad Reciente
        </p>
        <DaxCard padding={false}>
          {auditLog.length === 0 ? (
            <div className="p-8 text-center text-slate-600 text-sm italic">Sin actividad reciente registrada.</div>
          ) : (
            <div className="divide-y divide-slate-700/30">
              {auditLog.map((e) => {
                const color = ACTION_COLORS[e.action] ?? 'text-slate-400'
                const ts = e.created_at
                  ? new Date(e.created_at).toLocaleString('es-MX', { hour: '2-digit', minute: '2-digit', month: 'short', day: 'numeric' })
                  : ''
                return (
                  <div key={e.id} className="flex items-start gap-3 p-3 hover:bg-slate-800/20 transition">
                    <div className="w-5 h-5 rounded bg-slate-800 flex items-center justify-center shrink-0 mt-0.5">
                      <i className={`fa-solid fa-circle-dot text-[8px] ${color}`} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-xs text-slate-300 truncate font-medium">{e.entity_type ?? 'Sistema'}{e.entity_id ? ` #${e.entity_id}` : ''}</p>
                      <p className="text-[10px] text-slate-600 mt-0.5">
                        <span className={`${color} font-bold`}>{e.action}</span>
                        {ts ? ` · ${ts}` : ''}
                      </p>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </DaxCard>
      </div>
    </div>
  )
}
