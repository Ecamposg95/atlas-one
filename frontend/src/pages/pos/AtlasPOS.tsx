import { useEffect, useState, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { useAuthStore } from '../../store/authStore'
import { useEnabledModulesStore } from '../../store/enabledModulesStore'
import { urlsOcultasPorPlan } from '../../components/layout/navPerfilPlan'
import { salesApi } from '../../api/sales'
import { DaxCard } from '../../components/ui/DaxCard'
import type { SalesDocument } from '../../types/sales'
import { saleLabel } from '../../types/sales'
import { formatCurrency } from '../../utils/currency'
import { useIsBranchUser } from '../../components/branch/useIsBranchUser'
import { Cockpit } from '../../components/branch/Cockpit'

import { TablaDesplazable } from '../../components/ui/TablaDesplazable'

function greeting() {
  const h = new Date().getHours()
  if (h < 12) return 'Buenos días'
  if (h < 19) return 'Buenas tardes'
  return 'Buenas noches'
}

function Clock() {
  const [time, setTime] = useState(new Date())
  useEffect(() => {
    const id = setInterval(() => setTime(new Date()), 10_000)
    return () => clearInterval(id)
  }, [])
  return (
    <div className="text-right">
      <p className="text-3xl font-mono font-black text-white tabular-nums">
        {time.toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' })}
      </p>
      <p className="text-slate-500 text-xs mt-0.5">
        {time.toLocaleDateString('es-MX', { weekday: 'long', day: 'numeric', month: 'long' })}
      </p>
    </div>
  )
}

const QUICK_ACCESS = [
  { label: 'Punto de Venta', icon: 'fa-cash-register', url: '/pos', color: 'bg-indigo-600' },
  { label: 'Historial Ventas', icon: 'fa-history', url: '/sales', color: 'bg-slate-700' },
  { label: 'Control de Caja', icon: 'fa-vault', url: '/cash-history', color: 'bg-slate-700' },
  { label: 'Productos', icon: 'fa-barcode', url: '/products', color: 'bg-slate-700' },
  { label: 'Devoluciones', icon: 'fa-undo', url: '/returns', color: 'bg-slate-700' },
  { label: 'Mi Expediente', icon: 'fa-id-card', url: '/hr/me', color: 'bg-slate-700' },
]

export function AtlasPOS() {
  const isBranch = useIsBranchUser()
  if (isBranch) return <Cockpit />
  return <AtlasPOSHome />
}

// Separado para no romper Rules of Hooks: el return condicional de arriba
// no puede convivir con hooks en el mismo componente.
function AtlasPOSHome() {
  const { user, org } = useAuthStore()
  const { plan, enabledModules } = useEnabledModulesStore()
  // Mismo criterio que el menú: sin módulo hr o con /hr/me oculto por el plan, no hay tile.
  const quickAccess = QUICK_ACCESS.filter((q) =>
    q.url !== '/hr/me' ||
    ((enabledModules.length === 0 || enabledModules.includes('hr')) && !urlsOcultasPorPlan(plan).includes('/hr/me')))
  const [sales, setSales] = useState<SalesDocument[]>([])
  const [kpiTotal, setKpiTotal] = useState(0)
  const [kpiCount, setKpiCount] = useState(0)
  const [loading, setLoading] = useState(true)

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const today = new Date().toLocaleDateString('en-CA') // YYYY-MM-DD en timezone local
      const res = await salesApi.list({ start_date: today, end_date: today, limit: 5 })
      const items = res.items ?? []
      setSales(items)
      setKpiCount(res.total ?? items.length)
      setKpiTotal(items.reduce((s, v) => s + Number(v.total_amount), 0))
    } catch {
      // silencioso — datos no críticos
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <p className="text-[10px] text-white/30 uppercase font-bold tracking-widest mb-1">
            AtlasPOS — {org?.name ?? 'Sucursal'}
          </p>
          <h2 className="text-2xl font-black text-white">
            {greeting()}, {user?.full_name?.split(' ')[0] ?? user?.username}
          </h2>
          <p className="text-slate-400 text-sm mt-0.5">
            <i className="fa-solid fa-circle text-emerald-400 text-[8px] mr-1.5" />
            Sesión activa
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button onClick={loadData} disabled={loading} className="text-slate-500 hover:text-white transition-colors disabled:opacity-40" title="Actualizar">
            <i className={`fa-solid fa-rotate-right text-sm ${loading ? 'animate-spin' : ''}`} />
          </button>
          <Clock />
        </div>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 gap-4">
        <DaxCard>
          <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-1">Ventas hoy</p>
          <p className="text-3xl font-black text-white tabular-nums">{kpiCount}</p>
          <p className="text-slate-500 text-xs mt-0.5">tickets registrados</p>
        </DaxCard>
        <DaxCard>
          <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-1">Total hoy</p>
          <p className="text-3xl font-black text-indigo-400 tabular-nums">{formatCurrency(kpiTotal)}</p>
          <p className="text-slate-500 text-xs mt-0.5">en ventas del día</p>
        </DaxCard>
      </div>

      {/* Accesos rápidos */}
      <div>
        <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-3">Acceso rápido</p>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          {quickAccess.map((item) => (
            <Link
              key={item.url}
              to={item.url}
              className={`${item.color} rounded-xl p-4 flex flex-col items-center gap-2 hover:opacity-90 transition-opacity`}
            >
              <i className={`fa-solid ${item.icon} text-white text-xl`} />
              <span className="text-white text-xs font-semibold text-center">{item.label}</span>
            </Link>
          ))}
        </div>
      </div>

      {/* Últimas operaciones */}
      <DaxCard padding={false}>
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700/50">
          <p className="text-xs font-bold text-slate-400 uppercase tracking-widest">Últimas operaciones</p>
          <div className="flex items-center gap-3">
            <button onClick={loadData} className="text-slate-500 hover:text-white text-xs transition-colors">
              <i className="fa-solid fa-rotate-right" />
            </button>
            <Link to="/sales" className="text-indigo-400 text-xs hover:text-indigo-300">Ver todo →</Link>
          </div>
        </div>
        {loading ? (
          <div className="p-6 text-center text-slate-500 text-sm">Cargando...</div>
        ) : sales.length === 0 ? (
          <div className="p-6 text-center text-slate-600 text-sm">Sin ventas registradas hoy</div>
        ) : (
          <TablaDesplazable>
            <table className="dax-table w-full">
              <thead>
                <tr>
                  <th>Folio</th>
                  <th>Hora</th>
                  <th>Total</th>
                  <th>Estado</th>
                </tr>
              </thead>
              <tbody>
                {sales.map((sale) => (
                  <tr key={sale.id}>
                    <td className="font-mono text-indigo-400">{saleLabel(sale)}</td>
                    <td>{new Date(sale.created_at).toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' })}</td>
                    <td className="font-semibold">{formatCurrency(sale.total_amount)}</td>
                    <td>
                      <span className={`dax-badge ${sale.status === 'CLOSED' ? 'dax-badge-green' : sale.status === 'CANCELLED' ? 'dax-badge-red' : 'dax-badge-yellow'}`}>
                        {sale.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TablaDesplazable>
        )}
      </DaxCard>
    </div>
  )
}
