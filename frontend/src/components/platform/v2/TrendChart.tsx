import { useMemo, useState } from 'react'
import {
  Chart as ChartJS, CategoryScale, LinearScale, PointElement, LineElement, Filler, Tooltip,
  type ChartData, type ChartOptions,
} from 'chart.js'
import { Line } from 'react-chartjs-2'
import { formatCurrency } from '../../../utils/currency'
import { conAlpha, token, useTemaActual } from '../../../utils/cssToken'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Filler, Tooltip)

export interface TrendPoint {
  date: string
  label: string
  revenue: number
  ma7?: number | null
  sales?: number
  signups?: number
}

interface Props {
  data: TrendPoint[]
  height?: number
  showGrid?: boolean
  showLegend?: boolean
  /** Optional secondary series (sales count). When provided + toggled on, renders a second line. */
  salesSeries?: TrendPoint[]
  /** Optional tertiary series (signups count). When provided + toggled on, renders a third line. */
  signupsSeries?: TrendPoint[]
  /** When true, render 3 toggle pills above the chart (Revenue / Sales / Signups). Default false. */
  showSeriesToggles?: boolean
}

function chartCurrencyShort(value: number): string {
  if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`
  if (value >= 1_000) return `$${(value / 1_000).toFixed(1)}k`
  return `$${value.toFixed(0)}`
}

function intShort(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}k`
  return `${value.toFixed(0)}`
}

export function TrendChart({
  data,
  height = 300,
  showGrid = true,
  showLegend = true,
  salesSeries,
  signupsSeries,
  showSeriesToggles = false,
}: Props) {
  const tema = useTemaActual()
  const [revOn, setRevOn] = useState(true)
  const [salesOn, setSalesOn] = useState(false)
  const [signupsOn, setSignupsOn] = useState(false)

  // Las series opcionales se funden por índice, igual que antes con recharts.
  const merged = useMemo(() => {
    if (!data || data.length === 0) return []
    return data.map((p, i) => ({
      ...p,
      sales: salesSeries?.[i]?.revenue ?? salesSeries?.[i]?.sales ?? p.sales ?? 0,
      signups: signupsSeries?.[i]?.revenue ?? signupsSeries?.[i]?.signups ?? p.signups ?? 0,
    }))
  }, [data, salesSeries, signupsSeries])

  const hasSales = !!salesSeries && salesSeries.length > 0
  const hasSignups = !!signupsSeries && signupsSeries.length > 0
  const ejeDerecho = (hasSales && salesOn) || (hasSignups && signupsOn)

  const chartData = useMemo<ChartData<'line'>>(() => {
    const acento = token('--p-accent', '#6366f1')
    const muted = token('--p-muted', '#94a3b8')
    const datasets: ChartData<'line'>['datasets'] = []
    if (revOn) {
      datasets.push({
        label: 'Ventas diarias', yAxisID: 'y',
        data: merged.map((p) => p.revenue),
        borderColor: acento, borderWidth: 1.75, pointRadius: 0, tension: 0.35,
        fill: true, backgroundColor: conAlpha(acento, 0.18),
      })
      datasets.push({
        label: 'Promedio móvil 7d', yAxisID: 'y',
        data: merged.map((p) => p.ma7 ?? null),
        borderColor: muted, borderWidth: 1.25, borderDash: [3, 3], pointRadius: 0, tension: 0.35,
        spanGaps: true,
      })
    }
    if (hasSales && salesOn) {
      datasets.push({
        label: 'Tickets', yAxisID: 'y2',
        data: merged.map((p) => p.sales ?? 0),
        borderColor: token('--p-success', '#4ade80'), borderWidth: 1.5, pointRadius: 0, tension: 0.35,
      })
    }
    if (hasSignups && signupsOn) {
      datasets.push({
        label: 'Signups', yAxisID: 'y2',
        data: merged.map((p) => p.signups ?? 0),
        borderColor: token('--p-warning', '#fbbf24'), borderWidth: 1.5, pointRadius: 0, tension: 0.35,
      })
    }
    return { labels: merged.map((p) => p.label), datasets }
  }, [merged, revOn, salesOn, signupsOn, hasSales, hasSignups, tema])

  const options = useMemo<ChartOptions<'line'>>(() => {
    const hint = token('--p-hint', '#64748b')
    const borde = token('--p-border', '#1f2937')
    const mono = token('--font-mono', 'ui-monospace, monospace')
    return {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: token('--p-sidebar', '#0f172a'),
          borderColor: borde, borderWidth: 1,
          titleColor: token('--p-text', '#e2e8f0'), bodyColor: token('--p-text', '#e2e8f0'),
          callbacks: {
            title: (items) => `Día ${items[0]?.label ?? ''}`,
            label: (ctx) => {
              const v = typeof ctx.parsed.y === 'number' ? ctx.parsed.y : 0
              const esDinero = ctx.dataset.yAxisID === 'y'
              return `${ctx.dataset.label}: ${esDinero ? formatCurrency(v) : v}`
            },
          },
        },
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { color: hint, font: { size: 10, family: mono }, maxTicksLimit: 12, maxRotation: 0 },
        },
        y: {
          position: 'left',
          grid: { display: showGrid, color: borde, tickBorderDash: [2, 4] },
          border: { display: false },
          ticks: { color: hint, font: { size: 10, family: mono }, callback: (v) => chartCurrencyShort(Number(v)) },
        },
        y2: {
          position: 'right',
          display: ejeDerecho,
          grid: { drawOnChartArea: false },
          border: { display: false },
          ticks: { color: hint, font: { size: 10, family: mono }, callback: (v) => intShort(Number(v)) },
        },
      },
    }
  }, [showGrid, ejeDerecho, tema])

  if (!data || data.length === 0) {
    return (
      <div style={{ height, display: 'grid', placeItems: 'center', color: 'var(--p-muted)', fontSize: 13 }}>
        Sin datos de tendencia.
      </div>
    )
  }

  return (
    <div className="chart-wrap">
      {showSeriesToggles && (
        <div className="series-toggles" role="group" aria-label="Series">
          <button type="button" className={'pill ' + (revOn ? 'active' : '')} aria-pressed={revOn} onClick={() => setRevOn((v) => !v)}>
            Revenue
          </button>
          {hasSales && (
            <button type="button" className={'pill ' + (salesOn ? 'active' : '')} aria-pressed={salesOn} onClick={() => setSalesOn((v) => !v)}>
              Sales
            </button>
          )}
          {hasSignups && (
            <button type="button" className={'pill ' + (signupsOn ? 'active' : '')} aria-pressed={signupsOn} onClick={() => setSignupsOn((v) => !v)}>
              Signups
            </button>
          )}
        </div>
      )}
      {showLegend && (
        <div className="chart-caption">
          <span className="legend-inline">
            <span className="a"><span className="sw" />Ventas diarias</span>
            <span className="b"><span className="sw" />Promedio móvil 7d</span>
          </span>
          <span className="mono">USD</span>
        </div>
      )}
      <div style={{ height, width: '100%' }}>
        <Line data={chartData} options={options} />
      </div>
    </div>
  )
}
