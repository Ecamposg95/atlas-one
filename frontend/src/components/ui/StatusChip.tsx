import type { CSSProperties } from 'react'
import type { TableStatus } from '../../types/tables'
import type { KdsStatus, ItemStatus } from '../../types/kitchen'

/**
 * Chip de estado unificado — fuente única de verdad para los estados de
 * mesas, tickets de cocina (KDS) e items. Reemplaza los 3 mapas que antes
 * divergían en FloorPlan, KDS y ComandaTables.
 *
 * Los tonos usan rgba/soft para leerse tanto sobre superficies oscuras
 * (KDS/FloorPlan hoy) como claras (modo operación).
 */

export type Tone = 'green' | 'amber' | 'sky' | 'slate' | 'violet' | 'red'

interface ToneStyle { fg: string; bg: string; dot: string; border: string }

export const TONE: Record<Tone, ToneStyle> = {
  green:  { fg: '#0e8a4e', bg: 'rgba(16,185,129,0.14)',  dot: '#22c55e', border: 'rgba(16,185,129,0.55)' },
  amber:  { fg: '#b7791f', bg: 'rgba(245,158,11,0.16)',  dot: '#f59e0b', border: 'rgba(245,158,11,0.6)' },
  sky:    { fg: '#58524C', bg: 'rgba(132, 124, 115,0.15)',  dot: '#847C73', border: 'rgba(132, 124, 115,0.55)' },
  slate:  { fg: '#7A726B', bg: 'rgba(100,116,139,0.16)', dot: '#A8A29A', border: 'rgba(100,116,139,0.5)' },
  violet: { fg: '#898078', bg: 'rgba(255, 161, 74,0.15)',  dot: '#FFA14A', border: 'rgba(255, 161, 74,0.5)' },
  red:    { fg: '#c2410c', bg: 'rgba(239,68,68,0.14)',   dot: '#ef4444', border: 'rgba(239,68,68,0.5)' },
}

export interface StatusMeta { label: string; tone: Tone }

export const TABLE_STATUS: Record<TableStatus, StatusMeta> = {
  AVAILABLE:      { label: 'Libre',        tone: 'green' },
  OCCUPIED:       { label: 'Ocupada',      tone: 'amber' },
  BILL_REQUESTED: { label: 'Pidió cuenta', tone: 'sky' },
  CLEANING:       { label: 'Limpieza',     tone: 'slate' },
  RESERVED:       { label: 'Reservada',    tone: 'violet' },
}

export const KDS_STATUS: Record<KdsStatus, StatusMeta> = {
  NEW:         { label: 'Nueva',      tone: 'sky' },
  IN_PROGRESS: { label: 'En marcha',  tone: 'amber' },
  READY:       { label: 'Lista',      tone: 'green' },
  SERVED:      { label: 'Servida',    tone: 'slate' },
  CANCELED:    { label: 'Cancelada',  tone: 'slate' },
}

export const ITEM_STATUS: Record<ItemStatus, StatusMeta> = {
  PENDING:   { label: 'Pendiente',  tone: 'sky' },
  PREPARING: { label: 'Preparando', tone: 'amber' },
  READY:     { label: 'Listo',      tone: 'green' },
  SERVED:    { label: 'Servido',    tone: 'slate' },
  VOIDED:    { label: 'Anulado',    tone: 'red' },
}

interface StatusChipProps {
  tone: Tone
  label?: string
  dotOnly?: boolean
  /** 'sm' compact for dense grids, 'md' default */
  size?: 'sm' | 'md'
  style?: CSSProperties
  /** brighten fg/dot for dark surfaces (KDS/FloorPlan today) */
  onDark?: boolean
}

export function StatusChip({ tone, label, dotOnly, size = 'md', style, onDark }: StatusChipProps) {
  const t = TONE[tone]
  const fg = onDark ? t.dot : t.fg
  const dot = <span style={{ width: 8, height: 8, borderRadius: 999, background: t.dot, flex: 'none' }} />
  if (dotOnly) return <span style={{ display: 'inline-flex', ...style }}>{dot}</span>
  return (
    <span
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 6,
        padding: size === 'sm' ? '2px 8px' : '3px 10px',
        borderRadius: 999,
        fontSize: size === 'sm' ? 10 : 11,
        fontWeight: 700, letterSpacing: 0.2,
        color: fg, background: t.bg,
        border: `1px solid ${t.border}`,
        whiteSpace: 'nowrap',
        ...style,
      }}
    >
      {dot}
      {label}
    </span>
  )
}

/** Border color of a status tone — for card rings (FloorPlan / KDS). */
export function toneBorder(tone: Tone): string { return TONE[tone].border }
export function toneBg(tone: Tone): string { return TONE[tone].bg }
