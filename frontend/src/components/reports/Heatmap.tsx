import { useMemo, useState } from 'react'
import { formatCurrency } from '../../utils/currency'

/**
 * SalesHeatmap — rejilla día de la semana × hora (spec 2026-10-23 §3.2),
 * pintada con el verde del tema: la intensidad es `amount / max` en cinco
 * escalones de `color-mix(var(--dax-success) N%)`, así se repinta sola en
 * claro y oscuro. Convención de PostgreSQL: day 0 = domingo … 6 = sábado;
 * aquí el lunes va arriba. La ventana de horas la decide quien llama
 * (`recortarHoras` del kit); por defecto 9..21.
 */
export interface HeatmapCell {
  day: number   // 0..6 (0 = domingo)
  hour: number  // 0..23
  amount: number
  tickets: number
}

interface Props {
  data: HeatmapCell[]
  hourStart?: number
  hourEnd?: number
}

const WEEK_ORDER_PG = [1, 2, 3, 4, 5, 6, 0]
const WEEK_LABELS = ['L', 'M', 'X', 'J', 'V', 'S', 'D']
const WEEK_LONG = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']

/** Porcentaje del verde del tema por escalón (0 = sin venta). */
export const INTENSIDAD = [0, 20, 40, 60, 80, 100]

export function escalon(ratio: number): number {
  if (!(ratio > 0)) return 0
  if (ratio < 0.2) return 1
  if (ratio < 0.4) return 2
  if (ratio < 0.6) return 3
  if (ratio < 0.8) return 4
  return 5
}

const fondo = (pct: number) => `color-mix(in srgb, var(--dax-success) ${pct}%, transparent)`

export function SalesHeatmap({ data, hourStart = 9, hourEnd = 21 }: Props) {
  const hours = useMemo(
    () => Array.from({ length: Math.max(0, hourEnd - hourStart + 1) }, (_, i) => hourStart + i),
    [hourStart, hourEnd],
  )

  const { cells, maxAmount } = useMemo(() => {
    const map = new Map<string, HeatmapCell>()
    let max = 0
    for (const c of data) {
      map.set(`${c.day}-${c.hour}`, c)
      if (c.amount > max) max = c.amount
    }
    return { cells: map, maxAmount: max }
  }, [data])

  const [hover, setHover] = useState<{ dayIdx: number; hour: number; amount: number; tickets: number } | null>(null)

  return (
    <div className="relative">
      <div className="overflow-x-auto">
        <table className="w-full border-separate" style={{ borderSpacing: '3px' }}>
          <thead>
            <tr>
              <th className="w-6" />
              {hours.map((h) => (
                <th key={h} className="text-[9px] font-mono font-bold text-dax-faint text-center">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {WEEK_ORDER_PG.map((pgDay, rowIdx) => (
              <tr key={pgDay}>
                <td className="text-[10px] font-bold text-dax-muted pr-1 w-6 text-right align-middle">{WEEK_LABELS[rowIdx]}</td>
                {hours.map((h) => {
                  const c = cells.get(`${pgDay}-${h}`)
                  const amt = c?.amount ?? 0
                  const pct = INTENSIDAD[escalon(maxAmount > 0 ? amt / maxAmount : 0)]
                  return (
                    <td
                      key={`${pgDay}-${h}`}
                      data-testid={`celda-${pgDay}-${h}`}
                      data-intensidad={pct}
                      className={`relative h-6 rounded-sm cursor-pointer transition-all duration-200 hover:ring-2 hover:ring-dax-accent ${pct === 0 ? 'bg-dax-elevated' : ''}`}
                      style={pct > 0 ? { background: fondo(pct) } : undefined} /* estilo dinámico: la intensidad es el dato */
                      onMouseEnter={() => setHover({ dayIdx: rowIdx, hour: h, amount: amt, tickets: c?.tickets ?? 0 })}
                      onMouseLeave={() => setHover(null)}
                    />
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-3 flex items-center justify-end gap-1.5">
        <span className="text-[9px] font-bold uppercase tracking-wider text-dax-faint">Menos</span>
        {INTENSIDAD.map((pct) => (
          <div key={pct} className={`h-2 w-4 rounded-sm ${pct === 0 ? 'bg-dax-elevated' : ''}`}
            style={pct > 0 ? { background: fondo(pct) } : undefined} /* estilo dinámico: la leyenda repite los escalones */ />
        ))}
        <span className="text-[9px] font-bold uppercase tracking-wider text-dax-faint">Más</span>
      </div>

      {hover && (
        <div role="tooltip" className="pointer-events-none absolute top-0 right-0 bg-dax-card border border-dax-border rounded-lg px-3 py-2 shadow-lg z-10">
          <p className="text-[10px] font-bold uppercase tracking-wider text-dax-success">
            {WEEK_LONG[hover.dayIdx]} · {hover.hour}:00
          </p>
          <p className="text-sm font-black tabular-nums text-dax-text">{formatCurrency(hover.amount)}</p>
          <p className="text-[10px] text-dax-muted">{hover.tickets} {hover.tickets === 1 ? 'ticket' : 'tickets'}</p>
        </div>
      )}
    </div>
  )
}
