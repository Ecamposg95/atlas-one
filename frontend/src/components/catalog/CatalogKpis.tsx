import { useMemo, type CSSProperties } from 'react'

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

/**
 * Cifras del catálogo, con las clases del kit (`dax-kpi*`): icono en círculo,
 * rótulo y cifra ligera. "Total SKUs" es la tarjeta protagonista; las demás
 * solo toman color cuando hay algo que atender (pendientes, sin sucursal,
 * stock crítico o en cero). Solo tokens.
 */
export function CatalogKpis({ data, loading, onFilterPending, onFilterNoBranch }: Props) {
  const skeleton = loading && !data
  const safe = useMemo(() => data ?? {
    total_skus: 0, active_pos: 0, pending_approval: 0,
    no_branch: 0, critical_stock: 0, zero_stock: 0, threshold: 5,
  }, [data])

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
      <Card label="Total SKUs" value={safe.total_skus} icon="fa-cubes" skeleton={skeleton} destacada />
      <Card
        label="Activos POS"
        value={safe.active_pos}
        icon="fa-store"
        skeleton={skeleton}
        sub={safe.total_skus > 0 ? `${Math.round(safe.active_pos / safe.total_skus * 100)} % del catálogo` : undefined}
      />
      <Card
        label="Pendientes"
        value={safe.pending_approval}
        tono={safe.pending_approval > 0 ? 'text-dax-warning' : undefined}
        icon="fa-hourglass-half"
        skeleton={skeleton}
        sub={safe.pending_approval > 0 && onFilterPending ? 'Ver pendientes →' : undefined}
        onClick={safe.pending_approval > 0 ? onFilterPending : undefined}
      />
      <Card
        label="Sin sucursal"
        value={safe.no_branch}
        tono={safe.no_branch > 0 ? 'text-dax-warning' : undefined}
        icon="fa-link-slash"
        skeleton={skeleton}
        sub={safe.no_branch > 0 && onFilterNoBranch ? 'Ver cuáles →' : undefined}
        onClick={safe.no_branch > 0 ? onFilterNoBranch : undefined}
      />
      <Card
        label="Stock crítico"
        value={safe.critical_stock}
        tono={safe.critical_stock > 0 ? 'text-dax-warning' : undefined}
        icon="fa-triangle-exclamation"
        skeleton={skeleton}
        sub={`${safe.threshold} piezas o menos`}
      />
      <Card
        label="Stock cero"
        value={safe.zero_stock}
        tono={safe.zero_stock > 0 ? 'text-dax-danger' : undefined}
        icon="fa-ban"
        skeleton={skeleton}
      />
    </div>
  )
}

interface CardProps {
  label: string
  value: number
  icon: string
  /** Clase de color de la cifra cuando hay algo que atender. */
  tono?: string
  skeleton?: boolean
  sub?: string
  destacada?: boolean
  /** Con `onClick` la tarjeta es un botón que aplica su filtro. */
  onClick?: () => void
}

function Card({ label, value, icon, tono, skeleton, sub, destacada = false, onClick }: CardProps) {
  const texto = value.toLocaleString('es-MX')
  const clase = `dax-card dax-kpi p-4 ${destacada ? 'dax-kpi-ember' : ''}`
  const contenido = (
    <>
      <div className="flex items-center gap-2 mb-2">
        <span className="dax-kpi-icono" aria-hidden="true"><i className={`fa-solid ${icon}`} /></span>
        <p className="dax-kpi-label">{label}</p>
      </div>
      {skeleton ? (
        <div className="h-8 w-16 rounded-full bg-dax-elevated animate-pulse" />
      ) : (
        <p className={`dax-kpi-value ${tono && !destacada ? tono : ''}`} style={{ '--kpi-largo': texto.length } as CSSProperties}>
          {texto}
        </p>
      )}
      {sub && !skeleton && (
        <p className={`text-xs mt-1.5 ${destacada ? 'dax-kpi-ember-texto' : 'text-dax-muted'}`}>{sub}</p>
      )}
    </>
  )
  return onClick
    ? <button type="button" onClick={onClick} className={`${clase} text-left w-full cursor-pointer`}>{contenido}</button>
    : <div className={clase}>{contenido}</div>
}
