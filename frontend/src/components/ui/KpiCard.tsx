// frontend/src/components/ui/KpiCard.tsx
import type { CSSProperties, ReactNode } from 'react'
import type { Variacion } from '../../utils/variacion'

/**
 * KpiCard — una cifra del kit (spec 2026-10-23 §3.3): etiqueta
 * (`dax-kpi-label`), valor (`dax-kpi-value`), variación contra su referencia
 * (píldora ▲ en success, ▼ en danger; "Igual"/"Sin referencia" en muted), un
 * detalle opcional, un icono opcional y la variante `destacada` (card ember). Sustituye a `components/reports/KPICard` (conteo animado y
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
  /** Clase del icono de Font Awesome (`fa-coins`); va en un círculo junto a la etiqueta. */
  icono?: string
  /** Tarjeta protagonista (card ember). Una por pantalla, para la cifra que manda. */
  destacada?: boolean
  'data-testid'?: string
}

export function KpiCard({ etiqueta, valor, detalle, variacion, tono, icono, destacada = false, 'data-testid': testId }: KpiCardProps) {
  // Sobre la tarjeta ember el texto va en tinta clara: el tono y el gris del tema no se leen ahí.
  const claseValor = tono && !destacada ? `dax-kpi-value mt-1 ${TONO[tono]}` : 'dax-kpi-value mt-1'
  return (
    <div className={destacada ? 'dax-card dax-kpi dax-kpi-ember p-5' : 'dax-card dax-kpi p-5'} data-testid={testId}>
      <div className="flex items-center gap-2 mb-3">
        {icono && <span className="dax-kpi-icono" aria-hidden="true"><i className={`fa-solid ${icono}`} /></span>}
        <p className="dax-kpi-label">{etiqueta}</p>
      </div>
      {/* --kpi-largo: con él `.dax-kpi .dax-kpi-value` encoge la cifra para que quepa en la tarjeta. */}
      <p className={claseValor}
        style={{ '--kpi-largo': Math.max(valor.length, 1) } as CSSProperties}>{valor}</p>
      {variacion && <TextoVariacion v={variacion} destacada={destacada} />}
      {detalle != null && detalle !== '' && (
        <p className={`text-xs mt-1.5 ${destacada ? 'dax-kpi-ember-texto' : 'text-dax-muted'}`}>{detalle}</p>
      )}
    </div>
  )
}

function TextoVariacion({ v, destacada }: { v: Variacion; destacada: boolean }) {
  const gris = destacada ? 'dax-kpi-ember-texto' : 'text-dax-muted'
  if (v.pct === null) return <p className={`text-xs mt-2 ${gris}`} data-testid="variacion">Sin referencia · {v.texto}</p>
  if (v.pct === 0) return <p className={`text-xs mt-2 ${gris}`} data-testid="variacion">Igual · {v.texto}</p>
  const sube = v.pct > 0
  const bien = v.invertida ? !sube : sube
  // En la tarjeta ember la píldora no se tiñe de verde/rojo (chocaría con el naranja):
  // la flecha y el "Sube"/"Baja" de lectores de pantalla llevan el sentido.
  const color = destacada ? 'dax-kpi-ember-texto' : bien ? 'text-dax-success' : 'text-dax-danger'
  return (
    <p className={`text-xs tabular-nums mt-2 ${color}`} data-testid="variacion">
      <span className="dax-kpi-pildora">
        <span className="sr-only">{sube ? 'Sube' : 'Baja'} </span>
        <span aria-hidden="true">{sube ? '▲' : '▼'}</span> {Math.abs(v.pct)} %
      </span>{' '}
      <span className={`font-normal ${gris}`}>{v.texto}</span>
    </p>
  )
}

export default KpiCard
