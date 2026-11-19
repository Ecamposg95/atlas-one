import { useEffect, useState } from 'react'
import { reportsApi, WaiterSales } from '../../api/reports'
import { useAuthStore } from '../../store/authStore'
import { DaxCard } from '../../components/ui/DaxCard'
import { Spinner } from '../../components/ui/Spinner'
import { BarChart } from '../../components/atlas-one'

const money = (n: number) =>
  new Intl.NumberFormat('es-MX', { style: 'currency', currency: 'MXN', maximumFractionDigits: 0 }).format(n || 0)

function isoDaysAgo(days: number): string {
  const d = new Date()
  d.setDate(d.getDate() - days)
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${mm}-${dd}`
}

const RANGES = [
  { key: 'today', label: 'Hoy', days: 0 },
  { key: '7d', label: '7 días', days: 6 },
  { key: '30d', label: '30 días', days: 29 },
] as const

/** Accent del preset actual (violeta bar, naranja restaurant…), leído del CSS. */
function presetAccent(): string {
  if (typeof document === 'undefined') return '#EA580C'
  return getComputedStyle(document.documentElement).getPropertyValue('--p-accent').trim() || '#EA580C'
}

export function Meseros() {
  const { branch } = useAuthStore()
  const [range, setRange] = useState<(typeof RANGES)[number]['key']>('today')
  const [waiters, setWaiters] = useState<WaiterSales[]>([])
  const [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState(false)
  const accent = presetAccent()

  useEffect(() => {
    let alive = true
    const r = RANGES.find((x) => x.key === range)!
    const start = isoDaysAgo(r.days)
    const end = isoDaysAgo(0)
    setLoading(true)
    setFailed(false)
    reportsApi
      .byWaiter({ start_date: start, end_date: end, branch_id: branch?.id })
      .then((d) => { if (alive) setWaiters(d.waiters) })
      .catch(() => { if (alive) setFailed(true) })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [range, branch?.id])

  const totalRevenue = waiters.reduce((s, w) => s + w.revenue, 0)
  const totalTips = waiters.reduce((s, w) => s + w.tips, 0)
  const totalTickets = waiters.reduce((s, w) => s + w.tickets, 0)
  const top = waiters[0]

  const th = 'px-4 py-3 text-[11px] uppercase tracking-wide font-semibold text-slate-400 bg-slate-800/50 border-b border-slate-700/60'
  const td = 'px-4 py-3 border-b border-slate-700/40 tabular-nums'

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-[11px] uppercase tracking-[0.14em] text-slate-500 font-semibold">Reportes · Gastro</p>
          <div className="flex items-center gap-3 mt-1">
            <i className="fa-solid fa-user-tie text-xl" style={{ color: accent }} />
            <h1 className="text-2xl font-black text-white">Ventas por mesero</h1>
          </div>
          <p className="text-sm text-slate-400 mt-0.5">Desempeño y propinas por colaborador.</p>
        </div>
        <div className="inline-flex gap-1 bg-slate-800 rounded-full p-1">
          {RANGES.map((r) => {
            const on = range === r.key
            return (
              <button key={r.key} onClick={() => setRange(r.key)}
                className="px-3.5 py-1.5 rounded-full text-xs font-semibold transition-colors"
                style={on ? { background: accent, color: '#fff' } : { color: '#A8A29A' }}>
                {r.label}
              </button>
            )
          })}
        </div>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <DaxCard>
          <p className="text-[11px] uppercase tracking-wide text-slate-500">Ventas totales</p>
          <p className="text-2xl font-black text-white tabular-nums mt-1">{money(totalRevenue)}</p>
        </DaxCard>
        <DaxCard>
          <p className="text-[11px] uppercase tracking-wide text-slate-500">Propinas</p>
          <p className="text-2xl font-black tabular-nums mt-1" style={{ color: accent }}>{money(totalTips)}</p>
        </DaxCard>
        <DaxCard>
          <p className="text-[11px] uppercase tracking-wide text-slate-500">Tickets</p>
          <p className="text-2xl font-black text-white tabular-nums mt-1">{totalTickets}</p>
        </DaxCard>
        <DaxCard>
          <p className="text-[11px] uppercase tracking-wide text-slate-500">Mejor mesero</p>
          <p className="text-2xl font-black text-white mt-1 truncate">{top ? top.name.split(' ')[0] : '—'}</p>
          {top && <p className="text-[11px] text-slate-500 mt-0.5 tabular-nums">{money(top.revenue)}</p>}
        </DaxCard>
      </div>

      {failed ? (
        <DaxCard><p className="text-sm text-slate-300 py-2">No pudimos cargar el reporte de meseros.</p></DaxCard>
      ) : loading ? (
        <Spinner size="lg" text="Cargando meseros..." />
      ) : waiters.length === 0 ? (
        <DaxCard><p className="text-sm text-slate-400 text-center py-6">Sin ventas en el periodo</p></DaxCard>
      ) : (
        <>
          <DaxCard>
            <p className="text-[11px] uppercase tracking-wide text-slate-500 mb-3">Ventas por mesero</p>
            <div className="overflow-x-auto">
              <BarChart width={640} height={200} color={accent} soft="rgba(168, 162, 154,0.22)"
                data={waiters.slice(0, 8).map((w, i) => ({
                  label: w.name.split(' ')[0].slice(0, 8),
                  value: Math.round(w.revenue),
                  highlight: i === 0,
                }))}
              />
            </div>
          </DaxCard>

          <DaxCard padding={false} className="overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr>
                    <th className={`${th} text-left`}>Mesero</th>
                    <th className={`${th} text-right`}>Tickets</th>
                    <th className={`${th} text-right`}>Ventas</th>
                    <th className={`${th} text-right`}>Propinas</th>
                    <th className={`${th} text-right`}>Ticket prom.</th>
                  </tr>
                </thead>
                <tbody>
                  {waiters.map((w) => (
                    <tr key={w.user_id} className="hover:bg-slate-800/30 transition-colors">
                      <td className={`${td} text-white font-semibold`}>{w.name}</td>
                      <td className={`${td} text-right text-slate-300`}>{w.tickets}</td>
                      <td className={`${td} text-right text-white font-semibold`}>{money(w.revenue)}</td>
                      <td className={`${td} text-right font-semibold`} style={{ color: accent }}>{money(w.tips)}</td>
                      <td className={`${td} text-right text-slate-300`}>{money(w.avg_ticket)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </DaxCard>
        </>
      )}
    </div>
  )
}
