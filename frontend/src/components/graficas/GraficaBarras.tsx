// frontend/src/components/graficas/GraficaBarras.tsx
import { useMemo } from 'react'
import type { ChartData, ChartOptions } from 'chart.js'
import { Bar } from 'react-chartjs-2'
import './registro'
import { formatCurrency } from '../../utils/currency'
import { dineroCorto } from './formato'
import { useTemaGrafica } from './tema'

export interface GraficaBarrasProps {
  etiquetas: string[]
  valores: number[]
  /** Índice que se pinta con el acento (la hora actual); el resto va tenue. Sin él, todas en acento. */
  resaltar?: number | null
  /** Barras horizontales (sucursales). */
  horizontal?: boolean
  alto?: number
  /** Nombre de la serie en el tooltip. */
  nombre?: string
  /** Texto corto para lectores de pantalla: el canvas va como `role="img"`. */
  ariaLabel?: string
}

/** Barras planas (spec §3.3): un solo color por barra, sin degradados; ejes con `dineroCorto`. */
export function GraficaBarras({ etiquetas, valores, resaltar = null, horizontal = false, alto = 224, nombre = 'Venta', ariaLabel }: GraficaBarrasProps) {
  const tema = useTemaGrafica()
  const data = useMemo<ChartData<'bar'>>(() => ({
    labels: etiquetas,
    datasets: [{
      label: nombre,
      data: valores,
      backgroundColor: valores.map((_, i) => (resaltar === null || i === resaltar ? tema.acento : tema.faint)),
      borderWidth: 0,
      borderRadius: 3,
      maxBarThickness: 28,
    }],
  }), [etiquetas, valores, resaltar, nombre, tema])

  const opciones = useMemo<ChartOptions<'bar'>>(() => ({
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 300 },
    indexAxis: horizontal ? 'y' : 'x',
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: tema.cardSolid, borderColor: tema.borde, borderWidth: 1,
        titleColor: tema.texto, bodyColor: tema.texto,
        callbacks: { label: (ctx) => `${nombre}: ${formatCurrency(Number(horizontal ? ctx.parsed.x : ctx.parsed.y))}` },
      },
    },
    scales: horizontal
      ? {
          x: { beginAtZero: true, grid: { color: tema.borde }, border: { display: false }, ticks: { color: tema.muted, font: { size: 10 }, callback: (v) => dineroCorto(Number(v)) } },
          y: { grid: { display: false }, ticks: { color: tema.muted, font: { size: 10 } } },
        }
      : {
          x: { grid: { display: false }, ticks: { color: tema.muted, font: { size: 10 }, maxRotation: 0, autoSkipPadding: 8 } },
          y: { beginAtZero: true, grid: { color: tema.borde }, border: { display: false }, ticks: { color: tema.muted, font: { size: 10 }, callback: (v) => dineroCorto(Number(v)) } },
        },
  }), [tema, horizontal, nombre])

  return <div style={{ height: alto }}><Bar data={data} options={opciones} role={ariaLabel ? 'img' : undefined} aria-label={ariaLabel} /></div>
}
