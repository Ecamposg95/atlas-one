import { useEffect, useMemo, useRef, useState, useCallback } from 'react'
import { Link } from 'react-router-dom'
import {
  Chart as ChartJS,
  CategoryScale, LinearScale, BarElement, ArcElement,
  Tooltip, Legend,
} from 'chart.js'
import { Bar, Doughnut } from 'react-chartjs-2'
import { reportsApi, type CommandCenterStats } from '../../api/reports'
import { KPICard } from '../../components/reports/KPICard'
import { Spinner } from '../../components/ui/Spinner'
import { formatCurrency } from '../../utils/currency'
import { todayStr, daysAgoStr, formatDate } from '../../utils/dates'
import useKeyboardShortcuts from '../../hooks/useKeyboardShortcuts'

ChartJS.register(CategoryScale, LinearScale, BarElement, ArcElement, Tooltip, Legend)

type Period = 'today' | 'yesterday' | '7d' | 'week' | 'month' | 'custom'
type BranchSort = 'sales' | 'name' | 'alerts'

const REFRESH_MS = 60_000
const READ_ALERTS_KEY = 'hq-ops-read-alerts-v1'

const PERIOD_LABELS: Record<Period, string> = {
  today: 'Hoy',
  yesterday: 'Ayer',
  '7d': '7d',
  week: 'Semana',
  month: 'Mes',
  custom: 'Rango',
}

const PERIOD_VS: Record<Period, string> = {
  today: 'vs. ayer',
  yesterday: 'vs. anteayer',
  '7d': 'vs. 7d previos',
  week: 'vs. semana pasada',
  month: 'vs. mes pasado',
  custom: 'vs. periodo anterior',
}

const PAYMENT_COLORS: Record<string, string> = {
  CASH: '#10b981', EFECTIVO: '#10b981',
  CARD: '#0ea5e9', TARJETA: '#0ea5e9',
  TRANSFER: '#8b5cf6', TRANSFERENCIA: '#8b5cf6',
  CREDIT: '#f59e0b', CREDITO: '#f59e0b',
}
const OTHER_COLOR = '#64748b'

function rangeFor(period: Period, custom: { start: string; end: string }): { start: string; end: string } {
  const today = todayStr()
  if (period === 'today') return { start: today, end: today }
  if (period === 'yesterday') return { start: daysAgoStr(1), end: daysAgoStr(1) }
  if (period === '7d') return { start: daysAgoStr(6), end: today }
  if (period === 'week') {
    const d = new Date()
    const dow = d.getDay() || 7
    d.setDate(d.getDate() - dow + 1)
    return { start: d.toLocaleDateString('en-CA'), end: today }
  }
  if (period === 'month') {
    const d = new Date()
    return { start: `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-01`, end: today }
  }
  return { start: custom.start || today, end: custom.end || today }
}

function alertKey(a: { msg: string; source: string }): string {
  return `${a.source}::${a.msg}`
}

function loadReadAlerts(): Set<string> {
  try {
    const raw = localStorage.getItem(READ_ALERTS_KEY)
    if (!raw) return new Set()
    const arr = JSON.parse(raw) as string[]
    return new Set(arr.slice(-200))
  } catch { return new Set() }
}

function saveReadAlerts(set: Set<string>): void {
  try { localStorage.setItem(READ_ALERTS_KEY, JSON.stringify(Array.from(set).slice(-200))) } catch { /* ignore */ }
}

export function HQOperations() {
  const [period, setPeriod] = useState<Period>('today')
  const [customStart, setCustomStart] = useState(todayStr())
  const [customEnd, setCustomEnd] = useState(todayStr())
  const [stats, setStats] = useState<CommandCenterStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [lastSync, setLastSync] = useState<Date | null>(null)
  const [now, setNow] = useState(new Date())
  const [countdown, setCountdown] = useState(60)
  const [branchSearch, setBranchSearch] = useState('')
  const [branchSort, setBranchSort] = useState<BranchSort>('sales')
  const [readAlerts, setReadAlerts] = useState<Set<string>>(() => loadReadAlerts())
  const refreshRef = useRef<number | null>(null)

  const currentRange = useMemo(
    () => rangeFor(period, { start: customStart, end: customEnd }),
    [period, customStart, customEnd],
  )

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const { start, end } = currentRange
      const res = await reportsApi.commandCenterStats({ start_date: start, end_date: end })
      setStats(res)
      setLastSync(new Date())
      setCountdown(60)
    } catch (e) {
      console.error('Operaciones error:', e)
    } finally {
      setLoading(false)
    }
  }, [currentRange])

  useEffect(() => {
    load()
    if (refreshRef.current) window.clearInterval(refreshRef.current)
    refreshRef.current = window.setInterval(() => {
      if (document.hidden) return
      load()
    }, REFRESH_MS)
    return () => { if (refreshRef.current) window.clearInterval(refreshRef.current) }
  }, [load])

  useEffect(() => {
    const tick = window.setInterval(() => {
      if (document.hidden) return
      setNow(new Date())
      setCountdown((c) => (c <= 1 ? 60 : c - 1))
    }, 1000)
    return () => window.clearInterval(tick)
  }, [])

  useEffect(() => {
    const onVis = () => { if (!document.hidden) load() }
    document.addEventListener('visibilitychange', onVis)
    return () => document.removeEventListener('visibilitychange', onVis)
  }, [load])

  useKeyboardShortcuts([
    { keys: '1', handler: () => setPeriod('today') },
    { keys: '2', handler: () => setPeriod('week') },
    { keys: '3', handler: () => setPeriod('month') },
    { keys: 'r', handler: () => load() },
  ])

  const exportCsv = useCallback(async () => {
    try { await reportsApi.exportCsv({ start_date: currentRange.start, end_date: currentRange.end }) }
    catch (e) { console.error('export csv:', e) }
  }, [currentRange])

  const k = stats?.global
  const totalSales = k?.total_sales ?? 0
  const growth = k?.sales_growth ?? 0
  const previousSales = useMemo(() => {
    if (!k || !k.sales_growth) return undefined
    const g = k.sales_growth / 100
    if (g === -1) return undefined
    return totalSales / (1 + g)
  }, [k, totalSales])

  const paymentEntries = useMemo(() => {
    const pm = stats?.payment_methods ?? {}
    return Object.entries(pm)
      .filter(([, v]) => v > 0)
      .sort((a, b) => b[1] - a[1])
  }, [stats])
  const paymentTotal = paymentEntries.reduce((a, [, v]) => a + v, 0)
  const doughnutData = useMemo(() => ({
    labels: paymentEntries.map(([m]) => m),
    datasets: [{
      data: paymentEntries.map(([, v]) => v),
      backgroundColor: paymentEntries.map(([m]) => PAYMENT_COLORS[m] ?? OTHER_COLOR),
      borderColor: 'rgba(15,23,42,0.95)',
      borderWidth: 2,
      hoverOffset: 6,
    }],
  }), [paymentEntries])

  const hourly = stats?.hourly_distribution ?? []
  const currentHour = now.getHours()
  const isTodayRange = currentRange.start === todayStr() && currentRange.end === todayStr()
  const chartData = useMemo(() => ({
    labels: hourly.map((h) => `${String(h.hour).padStart(2, '0')}:00`),
    datasets: [{
      label: 'Revenue',
      data: hourly.map((h) => h.amount),
      backgroundColor: hourly.map((h) =>
        isTodayRange && h.hour === currentHour
          ? 'rgba(52,211,153,0.95)'
          : 'rgba(16,185,129,0.55)',
      ),
      borderColor: hourly.map((h) =>
        isTodayRange && h.hour === currentHour ? '#34d399' : '#10b981',
      ),
      borderWidth: 1,
      borderRadius: 5,
      hoverBackgroundColor: '#34d399',
    }],
  }), [hourly, currentHour, isTodayRange])

  const chartOptions = useMemo(() => ({
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: 'rgba(15,23,42,0.95)',
        titleColor: '#fff',
        bodyColor: '#10b981',
        borderColor: 'rgba(255,255,255,0.1)',
        borderWidth: 1,
        displayColors: false,
        padding: 10,
        callbacks: { label: (ctx: { raw: unknown }) => formatCurrency(Number(ctx.raw) || 0) },
      },
    },
    scales: {
      x: { grid: { display: false }, ticks: { color: '#64748b', font: { size: 10, family: 'monospace' } } },
      y: { grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { display: false } },
    },
    animation: { duration: 700, easing: 'easeOutQuart' as const },
  }), [])

  const branchesAll = stats?.branches ?? []
  const branches = useMemo(() => {
    const q = branchSearch.trim().toLowerCase()
    let list = branchesAll.filter((b) => !q || b.name.toLowerCase().includes(q))
    if (branchSort === 'sales') list = [...list].sort((a, b) => (b.total_sales || 0) - (a.total_sales || 0))
    else if (branchSort === 'name') list = [...list].sort((a, b) => a.name.localeCompare(b.name))
    else list = [...list].sort((a, b) => (b.critical_stock || 0) - (a.critical_stock || 0))
    return list
  }, [branchesAll, branchSearch, branchSort])
  const maxBranchSales = Math.max(1, ...branches.map((b) => b.total_sales || 0))
  const activeCount = branchesAll.filter((b) => b.status === 'ONLINE').length

  const topProducts = stats?.top_products ?? []
  const topProductsRevenue = topProducts.reduce((a, p) => a + p.value, 0) || 1

  const alerts = stats?.alerts ?? []
  const alertsByType = useMemo(() => {
    const groups: Record<string, typeof alerts> = {}
    for (const a of alerts) { (groups[a.type] ||= []).push(a) }
    return Object.entries(groups).sort((a, b) => b[1].length - a[1].length)
  }, [alerts])
  const unreadAlertsCount = alerts.filter((a) => !readAlerts.has(alertKey(a))).length
  const dominantAlertType = alertsByType[0]?.[0] ?? null

  const markAllRead = () => {
    const next = new Set(readAlerts)
    alerts.forEach((a) => next.add(alertKey(a)))
    setReadAlerts(next)
    saveReadAlerts(next)
  }

  const sinceFmt = (iso: string | undefined): string => {
    if (!iso || iso === 'Ahora') return 'Ahora'
    const parsed = new Date(iso)
    if (!Number.isFinite(parsed.getTime())) return iso
    return formatDate(parsed, 'time')
  }

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-black text-white tracking-widest uppercase" style={{ textShadow: '0 0 24px rgba(16,185,129,0.45)' }}>
              Operaciones
            </h1>
            <span className="text-[11px] font-mono text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20 tabular-nums">
              {now.toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
            </span>
            {branchesAll.length > 0 && (
              <span className="text-[10px] font-bold text-emerald-300 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20 tabular-nums">
                {activeCount}/{branchesAll.length} activas
              </span>
            )}
          </div>
          <div className="flex items-center gap-2 mt-0.5">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
            </span>
            <span className="text-[9px] font-bold text-emerald-500/70 uppercase tracking-widest">Live · Auto-refresh</span>
            <span className="text-slate-700">·</span>
            <span className="text-[9px] text-slate-600 font-mono">
              Últ. sync: {lastSync ? lastSync.toLocaleTimeString('es-MX') : '—'}
            </span>
          </div>
        </div>
        <div className="text-[10px] text-slate-500 font-mono">
          Próxima actualización en <span className="text-emerald-400 font-bold ml-1">{countdown}s</span>
        </div>
      </div>

      {/* Filters bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/5 pb-4">
        <div className="flex items-center gap-2 flex-wrap">
          {(['today', 'yesterday', '7d', 'week', 'month'] as const).map((p) => {
            const active = period === p
            const icon = p === 'today' ? 'fa-calendar-day'
              : p === 'yesterday' ? 'fa-clock-rotate-left'
              : p === '7d' ? 'fa-chart-line'
              : p === 'week' ? 'fa-calendar-week'
              : 'fa-calendar-alt'
            return (
              <button key={p} onClick={() => setPeriod(p)}
                className={`px-3 py-2 text-xs font-bold uppercase tracking-wider rounded-lg border transition ${
                  active
                    ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
                    : 'bg-transparent text-slate-500 hover:text-slate-300 border-transparent hover:bg-slate-800/50'
                }`}>
                <i className={`fas ${icon} mr-1.5`} /> {PERIOD_LABELS[p]}
              </button>
            )
          })}
          <button onClick={() => setPeriod('custom')}
            className={`px-3 py-2 text-xs font-bold uppercase tracking-wider rounded-lg border transition ${
              period === 'custom'
                ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
                : 'bg-transparent text-slate-500 hover:text-slate-300 border-transparent hover:bg-slate-800/50'
            }`}>
            <i className="fas fa-sliders mr-1.5" /> Rango
          </button>
          {period === 'custom' && (
            <div className="flex items-center gap-2 ml-2">
              <input type="date" value={customStart} max={customEnd}
                onChange={(e) => setCustomStart(e.target.value)}
                className="bg-slate-800/80 border border-slate-700 rounded px-2 py-1 text-xs text-slate-300" />
              <span className="text-slate-600 text-xs">→</span>
              <input type="date" value={customEnd} min={customStart} max={todayStr()}
                onChange={(e) => setCustomEnd(e.target.value)}
                className="bg-slate-800/80 border border-slate-700 rounded px-2 py-1 text-xs text-slate-300" />
            </div>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button onClick={exportCsv} title="Exportar CSV"
            className="px-3 py-1.5 text-[10px] font-bold uppercase tracking-wider rounded-lg bg-slate-800/80 border border-slate-700 hover:border-emerald-500/50 hover:text-emerald-400 text-slate-400 transition">
            <i className="fas fa-download mr-1" /> CSV
          </button>
          <button onClick={load} title="Actualizar ahora (R)"
            className="dax-btn-icon w-9 h-9 flex items-center justify-center rounded-full bg-slate-800/80 border border-slate-700 hover:bg-emerald-500/20 hover:border-emerald-500/50 hover:text-emerald-400 transition text-slate-400">
            <i className={`fas fa-sync-alt text-xs ${loading ? 'fa-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Quick nav */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { to: '/hq/branches', label: 'Sucursales', icon: 'fa-network-wired', color: 'emerald' },
          { to: '/hq/inventory', label: 'Inventario Global', icon: 'fa-boxes', color: 'sky' },
          { to: '/hq/sales', label: 'Log de Ventas', icon: 'fa-cash-register', color: 'amber' },
          { to: '/admin/catalog', label: 'Catálogo Global', icon: 'fa-list-check', color: 'violet' },
        ].map((n) => (
          <Link key={n.to} to={n.to}
            className={`dax-card p-4 rounded-xl hover:bg-white/5 transition group flex flex-col items-center justify-center text-center gap-2 border border-white/5 hover:border-${n.color}-500/30`}>
            <div className={`w-10 h-10 rounded-full bg-${n.color}-500/15 text-${n.color}-400 flex items-center justify-center text-lg group-hover:scale-110 transition`}>
              <i className={`fas ${n.icon}`} />
            </div>
            <span className="text-[11px] font-bold text-slate-300 group-hover:text-white">{n.label}</span>
          </Link>
        ))}
      </div>

      {loading && !stats ? (
        <Spinner text="Cargando operaciones..." />
      ) : (
        <>
          {/* KPI Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <KPICard
              label={`Revenue · ${PERIOD_VS[period]}`}
              value={totalSales}
              previous={previousSales}
              icon="fa-coins"
              tone="emerald"
              format={(n) => formatCurrency(n)}
            />

            <div className="dax-card p-5 rounded-2xl border-t-2 border-t-sky-500/50 relative overflow-hidden group hover:border-t-sky-400 transition-all">
              <div className="flex justify-between items-end mb-1">
                <p className="text-[10px] font-black uppercase text-slate-500 tracking-widest">Tickets</p>
                <span className="text-[10px] font-bold text-sky-400 bg-sky-500/10 px-1.5 py-0.5 rounded border border-sky-500/20 tabular-nums">
                  {(k?.items_per_ticket || 0).toFixed(1)} IPT
                </span>
              </div>
              <h2 className="text-3xl font-bold text-white tabular-nums">{k?.total_tickets ?? 0}</h2>
              <div className="mt-1 flex justify-between items-center text-xs font-mono">
                <span className="text-slate-400">Avg: <span className="text-white font-bold tabular-nums">{formatCurrency(k?.ticket_average || 0)}</span></span>
                {(k?.returns_total ?? 0) > 0 && (
                  <span className="text-rose-400">Dev: <span className="tabular-nums">{formatCurrency(k?.returns_total || 0)}</span></span>
                )}
              </div>
            </div>

            {/* Payment methods doughnut */}
            <div className="dax-card p-5 rounded-2xl border-t-2 border-t-violet-500/50 relative group hover:border-t-violet-400 transition-all">
              <p className="text-[10px] font-black uppercase text-slate-500 tracking-widest mb-1">Métodos de Pago</p>
              {paymentEntries.length === 0 ? (
                <div className="h-20 flex items-center justify-center text-[10px] text-slate-600 italic">Sin pagos registrados</div>
              ) : (
                <div className="flex items-center gap-3">
                  <div className="relative w-20 h-20 shrink-0">
                    <Doughnut
                      data={doughnutData}
                      options={{
                        responsive: true, maintainAspectRatio: false, cutout: '65%',
                        plugins: {
                          legend: { display: false },
                          tooltip: {
                            backgroundColor: 'rgba(15,23,42,0.95)', bodyColor: '#fff', borderColor: 'rgba(255,255,255,0.1)', borderWidth: 1, padding: 8,
                            callbacks: {
                              label: (ctx: { label: string; raw: unknown }) => {
                                const v = Number(ctx.raw) || 0
                                const pct = paymentTotal > 0 ? ((v / paymentTotal) * 100).toFixed(0) : '0'
                                return `${ctx.label}: ${formatCurrency(v)} (${pct}%)`
                              },
                            },
                          },
                        },
                      }}
                    />
                    <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                      <span className="text-[9px] font-bold text-slate-400 tabular-nums">{paymentEntries.length}</span>
                    </div>
                  </div>
                  <div className="flex-1 min-w-0 space-y-1">
                    {paymentEntries.slice(0, 3).map(([m, v]) => {
                      const pct = paymentTotal > 0 ? (v / paymentTotal) * 100 : 0
                      return (
                        <div key={m} className="flex items-center justify-between gap-2 text-[10px] font-mono">
                          <span className="flex items-center gap-1.5 min-w-0 truncate" style={{ color: PAYMENT_COLORS[m] ?? OTHER_COLOR }}>
                            <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: PAYMENT_COLORS[m] ?? OTHER_COLOR }} />
                            <span className="truncate">{m}</span>
                          </span>
                          <span className="text-slate-400 tabular-nums shrink-0">{pct.toFixed(0)}%</span>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}
            </div>

            {/* Alerts */}
            <Link to="/hq/control"
              className="dax-card p-5 rounded-2xl border-t-2 border-t-rose-500/50 relative overflow-hidden flex flex-col justify-center items-center text-center group hover:border-t-rose-400 transition-all cursor-pointer hover:bg-rose-500/5">
              <div className="h-10 w-10 rounded-full bg-rose-500/10 flex items-center justify-center text-rose-500 mb-2 ring-1 ring-rose-500/30 animate-pulse">
                <i className="fas fa-triangle-exclamation text-lg" />
              </div>
              <h2 className="text-3xl font-bold text-white tabular-nums" style={{ textShadow: '0 0 12px rgba(244,63,94,0.5)' }}>
                {alerts.length}
              </h2>
              <p className="text-[10px] font-black uppercase text-rose-400 tracking-widest">Alertas Críticas</p>
              {dominantAlertType && (
                <p className="text-[9px] text-slate-500 mt-0.5">
                  dominante: <span className="text-rose-300 font-bold">{dominantAlertType}</span>
                </p>
              )}
              {unreadAlertsCount > 0 && (
                <span className="absolute top-2 right-2 text-[9px] bg-rose-500 text-white px-1.5 py-0.5 rounded font-bold tabular-nums">
                  {unreadAlertsCount} nuevas
                </span>
              )}
              <p className="text-[9px] text-slate-600 mt-1">Ver Control HQ →</p>
            </Link>
          </div>

          {/* Charts + Branch Matrix */}
          {/* Apilado a una columna el `minHeight` fijo no tiene sentido:
              solo desde `lg`, donde las tres cajas conviven de lado. */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-5 lg:min-h-[380px]">
            <div className="dax-card rounded-2xl p-5 border border-white/5 lg:col-span-2 flex flex-col relative overflow-hidden">
              <div className="flex justify-between items-center mb-3">
                <h3 className="text-xs font-black uppercase text-white tracking-widest flex items-center gap-2">
                  <i className="fas fa-wave-square text-emerald-500" /> Sales Velocity (Hourly)
                </h3>
                <span className="flex items-center gap-2">
                  {isTodayRange && (
                    <span className="text-[9px] font-mono text-emerald-400/70">
                      Hora actual: {String(currentHour).padStart(2, '0')}:00
                    </span>
                  )}
                  <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                </span>
              </div>
              <div className="flex-1 relative w-full h-full">
                {hourly.length > 0 ? (
                  <Bar data={chartData} options={chartOptions} />
                ) : (
                  <div className="flex items-center justify-center h-full text-xs text-slate-600 italic">Sin datos</div>
                )}
              </div>
            </div>

            <div className="dax-card rounded-2xl p-0 border border-white/5 flex flex-col overflow-hidden">
              <div className="p-4 border-b border-white/5 bg-slate-900/40 space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <h3 className="text-xs font-black uppercase text-white tracking-widest flex items-center gap-2">
                    <i className="fas fa-network-wired text-sky-500" /> Branch Status
                  </h3>
                  <select value={branchSort} onChange={(e) => setBranchSort(e.target.value as BranchSort)}
                    className="text-[10px] bg-slate-800/80 border border-slate-700 rounded px-1.5 py-0.5 text-slate-300">
                    <option value="sales">Ventas</option>
                    <option value="name">Nombre</option>
                    <option value="alerts">Alertas</option>
                  </select>
                </div>
                <input type="search" value={branchSearch} onChange={(e) => setBranchSearch(e.target.value)}
                  placeholder="Buscar sucursal..."
                  className="w-full bg-slate-800/80 border border-slate-700 rounded px-2 py-1 text-xs text-slate-300 placeholder-slate-600" />
              </div>
              {/* En teléfono la lista fluye y el scroll lo hace la página:
              dos cajas de scroll interno dentro del scroll de la página
              dejaban al dedo sin saber cuál mueve (I-4). */}
              <div className="lg:flex-1 lg:overflow-y-auto max-lg:overscroll-contain p-3 space-y-2 bg-slate-900/20">
                {branches.length === 0 ? (
                  <div className="text-xs text-slate-600 italic p-4 text-center">
                    {branchesAll.length === 0 ? 'No hay sucursales configuradas.' : 'Sin resultados.'}
                  </div>
                ) : (
                  branches.map((b) => {
                    const pct = Math.round(((b.total_sales || 0) / maxBranchSales) * 100)
                    const online = b.status === 'ONLINE'
                    const users = (b.pending_users || []).map((u) => u.user).join(', ')
                    return (
                      <Link key={b.id} to={`/hq/branches/${b.id}`}
                        className="block p-3 rounded-xl bg-slate-800/50 hover:bg-slate-700/60 border border-white/5 hover:border-sky-500/30 transition group">
                        <div className="flex items-center justify-between mb-2">
                          <div className="flex items-center gap-2 min-w-0">
                            <div className={`w-2 h-2 rounded-full shrink-0 ${online ? 'bg-emerald-500' : 'bg-slate-600'}`}
                              style={online ? { boxShadow: '0 0 8px rgba(16,185,129,0.5)' } : undefined} />
                            <p className="text-xs font-bold text-white group-hover:text-sky-400 transition truncate">
                              {b.name}
                              {b.is_hq && <span className="text-[9px] bg-indigo-500 px-1 rounded ml-1">HQ</span>}
                            </p>
                            <span className={`text-[9px] font-bold uppercase shrink-0 ${online ? 'text-emerald-400' : 'text-slate-500'}`}>
                              · {online ? 'Online' : 'Offline'}
                            </span>
                          </div>
                          <div className="text-right shrink-0">
                            {b.pending_cuts > 0 && (
                              <span className="text-[9px] text-amber-400 font-bold block animate-pulse">CORTE: {users}</span>
                            )}
                            {b.critical_stock > 0 && (
                              <span className="text-[9px] text-rose-400 font-bold block">
                                {b.critical_stock} Alerta{b.critical_stock !== 1 ? 's' : ''}
                              </span>
                            )}
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <div className="flex-1 h-1 bg-slate-700 rounded-full overflow-hidden">
                            <div className="h-full bg-emerald-500/60 rounded-full transition-all duration-700" style={{ width: `${pct}%` }} />
                          </div>
                          <span className="text-[10px] font-mono text-emerald-400 shrink-0">{formatCurrency(b.total_sales || 0)}</span>
                        </div>
                      </Link>
                    )
                  })
                )}
              </div>
            </div>
          </div>

          {/* Bottom: Top Performers + Live Alerts Feed */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 pb-6">
            <div className="dax-card rounded-2xl p-5 border border-white/5">
              <h3 className="text-xs font-black uppercase text-white tracking-widest mb-4 flex items-center gap-2">
                <i className="fas fa-rocket text-amber-500" /> Top Performers
              </h3>
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-slate-800">
                  <thead className="bg-slate-900/80">
                    <tr>
                      <th className="px-3 py-3 text-left text-[10px] font-bold text-slate-400 uppercase tracking-wider">Producto</th>
                      <th className="px-3 py-3 text-right text-[10px] font-bold text-slate-400 uppercase tracking-wider">Revenue</th>
                      <th className="px-3 py-3 text-right text-[10px] font-bold text-slate-400 uppercase tracking-wider">% del top</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/50 text-sm">
                    {topProducts.length === 0 ? (
                      <tr><td colSpan={3} className="py-4 text-center text-xs text-slate-600 italic">Sin datos</td></tr>
                    ) : (
                      topProducts.map((p, i) => {
                        const pct = (p.value / topProductsRevenue) * 100
                        return (
                          <tr key={i} className="hover:bg-slate-800/60 transition group">
                            <td className="px-3 py-3 font-bold text-white group-hover:text-emerald-400 transition text-xs truncate max-w-none md:max-w-[140px]">{p.name}</td>
                            <td className="px-3 py-3 text-right font-mono text-emerald-400 font-bold text-xs">{formatCurrency(p.value)}</td>
                            <td className="px-3 py-3 text-right">
                              <div className="flex items-center justify-end gap-2">
                                <span className="text-[10px] font-mono text-slate-400 tabular-nums">{pct.toFixed(0)}%</span>
                                <div className="w-16 h-1 bg-slate-700 rounded-full overflow-hidden">
                                  <div className="h-full bg-emerald-500 rounded-full" style={{ width: `${Math.round(pct)}%` }} />
                                </div>
                              </div>
                            </td>
                          </tr>
                        )
                      })
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="dax-card rounded-2xl p-5 border border-white/5">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-xs font-black uppercase text-white tracking-widest flex items-center gap-2">
                  <i className="fas fa-satellite-dish text-violet-500" /> Live Comm Feed
                </h3>
                {unreadAlertsCount > 0 && (
                  <button onClick={markAllRead}
                    className="text-[10px] font-bold uppercase text-slate-500 hover:text-emerald-400 transition">
                    Marcar leídas
                  </button>
                )}
              </div>
              <div className="space-y-3 lg:max-h-64 lg:overflow-y-auto max-lg:overscroll-contain">
                {alertsByType.length === 0 ? (
                  <div className="text-center text-xs text-slate-600 py-4 italic flex items-center justify-center gap-2">
                    <i className="fas fa-check-circle text-emerald-500" /> All Systems Nominal.
                  </div>
                ) : (
                  alertsByType.map(([type, items]) => (
                    <div key={type} className="space-y-2">
                      <div className="flex items-center gap-2 text-[9px] font-bold uppercase tracking-widest text-rose-400/70">
                        <i className="fas fa-tag" /> {type}
                        <span className="bg-rose-500/10 border border-rose-500/20 px-1.5 rounded tabular-nums">{items.length}</span>
                      </div>
                      {items.map((a, i) => {
                        const read = readAlerts.has(alertKey(a))
                        return (
                          <div key={i}
                            className={`flex gap-3 text-xs p-2.5 rounded-xl border transition ${
                              read
                                ? 'bg-slate-800/30 border-slate-700/40 opacity-60'
                                : 'bg-rose-500/10 border-rose-500/20'
                            }`}>
                            <i className={`fas fa-exclamation-triangle mt-0.5 shrink-0 ${read ? 'text-slate-500' : 'text-rose-500'}`} />
                            <div className="flex-1 min-w-0">
                              <p className={`font-bold ${read ? 'text-slate-400' : 'text-rose-200'}`}>{a.msg}</p>
                              <p className="text-[9px] text-rose-400/60 mt-0.5 uppercase tracking-wide">
                                {a.source} · {sinceFmt(a.time)}
                              </p>
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
