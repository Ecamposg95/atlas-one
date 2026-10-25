// frontend/src/components/ui/KpiCard.tsx
import type { ReactNode } from 'react'
import type { Variacion } from '../../utils/variacion'

/**
 * KpiCard — una cifra del kit (spec 2026-10-23 §3.3): etiqueta
 * (`dax-kpi-label`), valor (`dax-kpi-value`), variación contra su referencia
 * (▲ en success, ▼ en danger, "Igual"/"Sin referencia" en muted) y un detalle
 * opcional. Sustituye a `components/reports/KPICard` (conteo animado y
 * chispas) y a la `Cifra` local del Inicio. Solo tokens; sin colores fijos.
 */
export type TonoKpi = 'success' | 'warning' | 'danger'
const TONO: Record<TonoKpi, string> = { success: 'text-dax-success', warning: 'text-dax-warning', danger: 'text-dax-danger' }

export interface KpiCardProps {
  etiqueta: string
  /** Ya formateado ("$1,234.50", "12"). */
  valor: string
  detalle?: ReactNode
  variacion?: Variacion
  tono?: TonoKpi
  'data-testid'?: string
}

export function KpiCard({ etiqueta, valor, detalle, variacion, tono, 'data-testid': testId }: KpiCardProps) {
  return (
    <div className="dax-card p-4" data-testid={testId}>
      <p className="dax-kpi-label">{etiqueta}</p>
      <p className={tono ? `dax-kpi-value mt-1 ${TONO[tono]}` : 'dax-kpi-value mt-1'}>{valor}</p>
      {variacion && <TextoVariacion v={variacion} />}
      {detalle != null && detalle !== '' && <p className="text-xs text-dax-muted mt-1">{detalle}</p>}
    </div>
  )
}

function TextoVariacion({ v }: { v: Variacion }) {
  if (v.pct === null) return <p className="text-xs text-dax-muted mt-1" data-testid="variacion">Sin referencia · {v.texto}</p>
  if (v.pct === 0) return <p className="text-xs text-dax-muted mt-1" data-testid="variacion">Igual · {v.texto}</p>
  const sube = v.pct > 0
  const bien = v.invertida ? !sube : sube
  return (
    <p className={`text-xs font-bold tabular-nums mt-1 ${bien ? 'text-dax-success' : 'text-dax-danger'}`} data-testid="variacion">
      <span className="sr-only">{sube ? 'Sube' : 'Baja'} </span>
      <span aria-hidden="true">{sube ? '▲' : '▼'}</span> {Math.abs(v.pct)} %{' '}
      <span className="font-normal text-dax-muted">{v.texto}</span>
    </p>
  )
}

export default KpiCard
