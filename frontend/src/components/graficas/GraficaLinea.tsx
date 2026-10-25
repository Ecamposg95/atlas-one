// frontend/src/components/graficas/GraficaLinea.tsx
import { useMemo } from 'react'
import type { ChartData, ChartOptions } from 'chart.js'
import { Line } from 'react-chartjs-2'
import './registro'
import { formatCurrency } from '../../utils/currency'
import { dineroCorto } from './formato'
import { useTemaGrafica } from './tema'

export interface SerieLinea {
  nombre: string
  valores: number[]
  /** Serie de referencia (periodo anterior): tenue y discontinua. */
  comparativo?: boolean
}

/** Línea plana (spec §3.3): acento para la serie principal, tenue para el comparativo, sin relleno. */
export function GraficaLinea({ etiquetas, series, alto = 224 }: { etiquetas: string[]; series: SerieLinea[]; alto?: number }) {
  const tema = useTemaGrafica()
  const data = useMemo<ChartData<'line'>>(() => ({
    labels: etiquetas,
    datasets: series.map((s) => ({
      label: s.nombre,
      data: s.valores,
      borderColor: s.comparativo ? tema.faint : tema.acento,
      backgroundColor: s.comparativo ? tema.faint : tema.acento,
      borderWidth: s.comparativo ? 1.5 : 2,
      borderDash: s.comparativo ? [4, 4] : undefined,
      pointRadius: 0,
      pointHoverRadius: 4,
      tension: 0.3,
      fill: false,
    })),
  }), [etiquetas, series, tema])

  const opciones = useMemo<ChartOptions<'line'>>(() => ({
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 300 },
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: tema.cardSolid, borderColor: tema.borde, borderWidth: 1,
        titleColor: tema.texto, bodyColor: tema.texto,
        callbacks: { label: (ctx) => `${ctx.dataset.label ?? ''}: ${formatCurrency(Number(ctx.parsed.y ?? 0))}` },
      },
    },
    scales: {
      x: { grid: { display: false }, ticks: { color: tema.muted, font: { size: 10 }, maxRotation: 0, autoSkipPadding: 8 } },
      y: {
        beginAtZero: true, grid: { color: tema.borde }, border: { display: false },
        ticks: { color: tema.muted, font: { size: 10 }, callback: (v) => dineroCorto(Number(v)) },
      },
    },
  }), [tema])

  return <div style={{ height: alto }}><Line data={data} options={opciones} /></div>
}
