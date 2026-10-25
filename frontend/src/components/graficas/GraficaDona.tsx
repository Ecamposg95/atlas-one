// frontend/src/components/graficas/GraficaDona.tsx
import { useMemo, type ReactNode } from 'react'
import type { ChartData, ChartOptions } from 'chart.js'
import { Doughnut } from 'react-chartjs-2'
import './registro'
import { formatCurrency } from '../../utils/currency'
import { useTemaGrafica } from './tema'

export interface ParteDona {
  nombre: string
  valor: number
  color: string
}

/**
 * Dona plana con el total al centro (spec §3.1/§3.2). Un método con neta
 * negativa (más devuelto que cobrado) se pinta como 0: un gajo negativo no
 * existe; la lista bajo la dona sí enseña el número real.
 */
export function GraficaDona({ partes, centro, alto = 224, ariaLabel }: { partes: ParteDona[]; centro?: ReactNode; alto?: number; ariaLabel?: string }) {
  const tema = useTemaGrafica()
  const valores = useMemo(() => partes.map((p) => Math.max(0, p.valor)), [partes])
  const total = valores.reduce((s, v) => s + v, 0)

  const data = useMemo<ChartData<'doughnut'>>(() => ({
    labels: partes.map((p) => p.nombre),
    datasets: [{
      data: valores,
      backgroundColor: partes.map((p) => p.color),
      borderColor: tema.cardSolid,
      borderWidth: 2,
      hoverOffset: 6,
    }],
  }), [partes, valores, tema])

  const opciones = useMemo<ChartOptions<'doughnut'>>(() => ({
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 300 },
    cutout: '70%',
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: tema.cardSolid, borderColor: tema.borde, borderWidth: 1,
        titleColor: tema.texto, bodyColor: tema.texto,
        callbacks: {
          label: (ctx) => {
            const v = Number(ctx.parsed)
            const pct = total > 0 ? Math.round((v / total) * 100) : 0
            return `${ctx.label}: ${formatCurrency(v)} (${pct} %)`
          },
        },
      },
    },
  }), [tema, total])

  return (
    <div className="relative" style={{ height: alto }}>
      <Doughnut data={data} options={opciones} role={ariaLabel ? 'img' : undefined} aria-label={ariaLabel} />
      {centro && (
        <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">{centro}</div>
      )}
    </div>
  )
}
