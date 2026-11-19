import { useMemo } from 'react'
import { DaxCard } from '../ui/DaxCard'

interface Kpis {
  total_skus: number
  active_pos: number
  pending_approval: number
  no_branch: number
  critical_stock: number
  zero_stock: number
  threshold: number
}

interface Props {
  data: Kpis | null
  loading: boolean
  onFilterPending?: () => void
  onFilterNoBranch?: () => void
}

const CARD_BASE =
  'p-3 rounded-xl border bg-gradient-to-br transition-all duration-200'

export function CatalogKpis({ data, loading, onFilterPending, onFilterNoBranch }: Props) {
  const skeleton = loading && !data
  const safe = useMemo(() => data ?? {
    total_skus: 0, active_pos: 0, pending_approval: 0,
    no_branch: 0, critical_stock: 0, zero_stock: 0, threshold: 5,
  }, [data])

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
      <Card
        label="Total SKUs"
        value={safe.total_skus}
        color="indigo"
        icon="fa-cubes"
        skeleton={skeleton}
      />
      <Card
        label="Activos POS"
        value={safe.active_pos}
        color="emerald"
        icon="fa-store"
        skeleton={skeleton}
        sub={safe.total_skus > 0 ? `${Math.round(safe.active_pos / safe.total_skus * 100)}%` : undefined}
      />
      <Card
        label="Pendientes"
        value={safe.pending_approval}
        color={safe.pending_approval > 0 ? 'amber' : 'slate'}
        icon="fa-hourglass-half"
        skeleton={skeleton}
        interactive={safe.pending_approval > 0 && !!onFilterPending}
        onClick={safe.pending_approval > 0 ? onFilterPending : undefined}
      />
      <Card
        label="Sin sucursal"
        value={safe.no_branch}
        color={safe.no_branch > 0 ? 'fuchsia' : 'slate'}
        icon="fa-link-slash"
        skeleton={skeleton}
        interactive={safe.no_branch > 0 && !!onFilterNoBranch}
        onClick={safe.no_branch > 0 ? onFilterNoBranch : undefined}
      />
      <Card
        label="Stock crítico"
        value={safe.critical_stock}
        color={safe.critical_stock > 0 ? 'orange' : 'slate'}
        icon="fa-triangle-exclamation"
        skeleton={skeleton}
        sub={`≤ ${safe.threshold}`}
      />
      <Card
        label="Stock cero"
        value={safe.zero_stock}
        color={safe.zero_stock > 0 ? 'rose' : 'slate'}
        icon="fa-ban"
        skeleton={skeleton}
      />
    </div>
  )
}

interface CardProps {
  label: string
  value: number
  color: 'indigo' | 'emerald' | 'amber' | 'fuchsia' | 'orange' | 'rose' | 'slate'
  icon: string
  skeleton?: boolean
  sub?: string
  interactive?: boolean
  onClick?: () => void
}

const COLOR_CLASSES: Record<CardProps['color'], { border: string; from: string; text: string }> = {
  indigo:   { border: 'border-indigo-500/20',   from: 'from-indigo-500/10',   text: 'text-indigo-700 dark:text-indigo-300' },
  emerald:  { border: 'border-emerald-500/20',  from: 'from-emerald-500/10',  text: 'text-emerald-700 dark:text-emerald-300' },
  amber:    { border: 'border-amber-500/30',    from: 'from-amber-500/15',    text: 'text-amber-700 dark:text-amber-300' },
  fuchsia:  { border: 'border-fuchsia-500/25',  from: 'from-fuchsia-500/12',  text: 'text-fuchsia-700 dark:text-fuchsia-300' },
  orange:   { border: 'border-orange-500/25',   from: 'from-orange-500/12',   text: 'text-orange-700 dark:text-orange-300' },
  rose:     { border: 'border-rose-500/25',     from: 'from-rose-500/12',     text: 'text-rose-700 dark:text-rose-300' },
  slate:    { border: 'border-dax-border-dim',   from: 'from-dax-elevated',    text: 'text-dax-text' },
}

function Card({ label, value, color, icon, skeleton, sub, interactive, onClick }: CardProps) {
  const c = COLOR_CLASSES[color]
  const Wrapper: any = interactive ? 'button' : 'div'

  return (
    <Wrapper
      onClick={interactive ? onClick : undefined}
      className={`${CARD_BASE} ${c.border} ${c.from} to-transparent ${
        interactive ? 'hover:scale-[1.015] cursor-pointer text-left w-full' : ''
      }`}
    >
      <div className="flex items-start justify-between mb-1">
        <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">
          {label}
        </p>
        <i className={`fa-solid ${icon} ${c.text} text-xs`} />
      </div>
      {skeleton ? (
        <div className="h-7 w-16 rounded bg-slate-700/40 animate-pulse" />
      ) : (
        <div className="flex items-baseline gap-2">
          <p className={`text-2xl font-black tabular-nums ${c.text}`}>
            {value.toLocaleString('es-MX')}
          </p>
          {sub && <span className="text-[11px] font-semibold text-slate-500">{sub}</span>}
        </div>
      )}
    </Wrapper>
  )
}
