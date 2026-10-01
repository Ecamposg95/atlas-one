import { useEffect, useState, useCallback } from 'react'
import { reportsApi, type DashboardData } from '../../api/reports'
import { DaxCard } from '../../components/ui/DaxCard'
import { BarraFiltros, ParFechas } from '../../components/ui/BarraFiltros'
import { CabeceraPagina } from '../../components/ui/CabeceraPagina'
import { Spinner } from '../../components/ui/Spinner'
import { useTheme } from '../../context/ThemeContext'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  PointElement,
  LineElement,
  Tooltip,
  Legend,
} from 'chart.js'
import { Bar } from 'react-chartjs-2'
import { formatCurrency } from '../../utils/currency'
import { todayStr, daysAgoStr } from '../../utils/dates'

ChartJS.register(CategoryScale, LinearScale, BarElement, PointElement, LineElement, Tooltip, Legend)

const PRESETS = [
  { label: 'Hoy', start: () => todayStr(), end: () => todayStr() },
  { label: 'Ayer', start: () => daysAgoStr(1), end: () => daysAgoStr(1) },
  { label: 'Semana', start: () => daysAgoStr(7), end: () => todayStr() },
  { label: 'Mes', start: () => daysAgoStr(30), end: () => todayStr() },
]

export function Reports() {
  const { theme } = useTheme()
  const chartGrid  = theme === 'dark' ? 'rgba(255,255,255,0.05)' : 'rgba(99,102,241,0.08)'
  const chartTicks = theme === 'dark' ? '#64748b' : '#94a3b8'
  const [data, setData] = useState<DashboardData | null>(null)
  const [loading, setLoading] = useState(true)
  const [startDate, setStartDate] = useState(todayStr())
  const [endDate, setEndDate] = useState(todayStr())

  const load = useCallback(async (start: string, end: string) => {
    setLoading(true)
    try {
      const res = await reportsApi.dashboard({ start_date: start, end_date: end })
      setData(res)
    } catch {
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load(startDate, endDate) }, [])

  const applyPreset = (p: typeof PRESETS[0]) => {
    const s = p.start(), e = p.end()
    setStartDate(s); setEndDate(e); load(s, e)
  }

  const hourlyLabels = data?.charts?.hourly?.labels ?? []
  const hourlyValues = data?.charts?.hourly?.data ?? []

  const chartData = {
    labels: hourlyLabels,
    datasets: [{
      label: 'Ventas',
      data: hourlyValues,
      backgroundColor: 'rgba(99, 102, 241, 0.7)',
      borderColor: 'rgb(99, 102, 241)',
      borderWidth: 1,
      borderRadius: 4,
    }],
  }

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: {
      x: { grid: { color: chartGrid }, ticks: { color: chartTicks, font: { size: 10 } } },
      y: { grid: { color: chartGrid }, ticks: { color: chartTicks, font: { size: 10 }, callback: (v: unknown) => formatCurrency(Number(v)) } },
    },
  }

  const methodColor = (m: string) =>
    m === 'CASH' ? 'text-emerald-400' : m === 'CARD' ? 'text-indigo-400' : 'text-blue-400'

  const paymentMethods = data?.charts?.payments
    ? Object.entries(data.charts.payments).map(([method, v]) => ({ method, ...v }))
    : []

  const topMethod = paymentMethods.length
    ? paymentMethods.reduce((a, b) => b.total > a.total ? b : a).method
    : '—'

  return (
    <div className="space-y-5">
      <CabeceraPagina
        titulo={
          <div className="flex items-center gap-3">
            <i className="fa-solid fa-chart-pie text-indigo-400 text-xl" />
            <h1 className="text-2xl font-black text-white">Reportes</h1>
          </div>
        }
      />

      {/* Filtros */}
      <BarraFiltros
        className="items-center"
        accion={
          <button onClick={() => load(startDate, endDate)} className="dax-btn-primary text-xs">
            <i className="fa-solid fa-search" /> Filtrar
          </button>
        }
      >
        {/* Atajos de fecha: 4 en una fila en telefono; sm:contents los deja sueltos como hoy */}
        <div className="grid grid-cols-4 gap-2 sm:contents">
          {PRESETS.map((p) => (
            <button
              key={p.label}
              onClick={() => applyPreset(p)}
              className={`px-3 py-1.5 max-sm:min-h-[44px] rounded-lg text-xs font-semibold transition-colors ${
                startDate === p.start() && endDate === p.end()
                  ? 'bg-indigo-600 text-white'
                  : 'bg-slate-700/50 text-slate-400 hover:text-white'
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
        <ParFechas>
          <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className="dax-input w-36 text-xs" />
          <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} className="dax-input w-36 text-xs" />
        </ParFechas>
      </BarraFiltros>

      {loading ? <Spinner text="Cargando reportes..." /> : !data ? (
        <DaxCard>
          <div className="p-12 text-center text-slate-600">Sin datos para el período seleccionado</div>
        </DaxCard>
      ) : (
        <>
          {/* KPIs */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[
              { label: 'Total ventas', value: formatCurrency(data.kpis.sales), icon: 'fa-coins', color: 'text-emerald-400' },
              { label: 'Transacciones', value: String(data.kpis.orders), icon: 'fa-receipt', color: 'text-white' },
              { label: 'Ticket promedio', value: formatCurrency(data.kpis.avg_ticket), icon: 'fa-chart-bar', color: 'text-indigo-400' },
              { label: 'Método top', value: topMethod, icon: 'fa-credit-card', color: 'text-slate-300' },
            ].map((k) => (
              <DaxCard key={k.label}>
                <div className="flex items-center gap-2 mb-1">
                  <i className={`fa-solid ${k.icon} text-slate-500 text-xs`} />
                  <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">{k.label}</p>
                </div>
                <p className={`text-xl font-black tabular-nums ${k.color}`}>{k.value}</p>
              </DaxCard>
            ))}
          </div>

          {/* Gráfica por hora */}
          {hourlyValues.length > 0 && (
            <DaxCard>
              <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-3">Ventas por Hora</p>
              <div style={{ height: 200 }}>
                <Bar data={chartData} options={chartOptions as never} />
              </div>
            </DaxCard>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {/* Por método de pago */}
            {paymentMethods.length > 0 && (
              <DaxCard>
                <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-3">Por Método de Pago</p>
                <div className="space-y-2">
                  {paymentMethods.map((m) => (
                    <div key={m.method} className="flex items-center justify-between text-sm">
                      <div className="flex items-center gap-2">
                        <i className={`fa-solid ${m.method === 'CASH' ? 'fa-money-bill' : m.method === 'CARD' ? 'fa-credit-card' : 'fa-mobile-screen'} text-xs ${methodColor(m.method)}`} />
                        <span className="text-slate-400">{m.method}</span>
                        <span className="text-slate-600 text-xs">({m.count} tx)</span>
                      </div>
                      <span className={`font-semibold tabular-nums ${methodColor(m.method)}`}>{formatCurrency(m.total)}</span>
                    </div>
                  ))}
                </div>
              </DaxCard>
            )}

            {/* Top productos */}
            {data.top_products && data.top_products.length > 0 && (
              <DaxCard>
                <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-3">Top Productos</p>
                <div className="space-y-2">
                  {data.top_products.slice(0, 5).map((p, i) => (
                    <div key={i} className="flex items-center gap-2 text-sm">
                      <span className="text-slate-600 font-bold w-4 text-right">{i + 1}</span>
                      <span className="text-slate-300 flex-1 truncate">{p.name}</span>
                      <span className="text-emerald-400 font-semibold tabular-nums">{p.qty} u.</span>
                    </div>
                  ))}
                </div>
              </DaxCard>
            )}
          </div>

          {/* Ventas recientes */}
          {data.recent_sales && data.recent_sales.length > 0 && (
            <DaxCard>
              <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-3">Ventas Recientes</p>
              <div className="space-y-1">
                {data.recent_sales.map((s, i) => (
                  <div key={i} className="flex items-center justify-between text-xs py-1 border-b border-slate-700/30">
                    <div className="flex items-center gap-3">
                      <span className="font-mono text-indigo-400">{s.folio}</span>
                      <span className="text-slate-400">{s.customer}</span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="text-slate-500">{s.time}</span>
                      <span className="text-emerald-400 font-semibold tabular-nums">{formatCurrency(s.total)}</span>
                    </div>
                  </div>
                ))}
              </div>
            </DaxCard>
          )}
        </>
      )}
    </div>
  )
}
