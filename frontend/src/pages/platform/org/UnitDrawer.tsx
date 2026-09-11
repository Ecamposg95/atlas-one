import type { CSSProperties, ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { SideDrawer } from '../../../components/platform/SideDrawer'
import { formatCurrency } from '../../../utils/currency'
import type { BranchOverviewRow } from '../../../types/platformOverview'
import { fmtDelta, fmtMix } from './orgFormat'

interface Props { row: BranchOverviewRow | null; onClose: () => void }

const TITULO: CSSProperties = {
  margin: '12px 0 4px', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.08em',
}

function Line({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div style={{
      display: 'flex', justifyContent: 'space-between', gap: 12, padding: '8px 0',
      borderBottom: '1px solid var(--p-border-2)', fontSize: 13,
    }}>
      <span className="muted">{label}</span><span className="mono">{value}</span>
    </div>
  )
}

/** El detalle del día de una sucursal de la organización seleccionada. */
export function UnitDrawer({ row, onClose }: Props) {
  if (!row) return null
  const c = row.cash
  return (
    <SideDrawer open title={row.name} subtitle={row.org_name} onClose={onClose}>
      <h4 className="hint" style={TITULO}>Ventas</h4>
      <Line label="Hoy" value={formatCurrency(row.sales_today)} />
      <Line label="Ayer" value={`${formatCurrency(row.sales_yesterday)} (${fmtDelta(row.delta_yesterday_pct).text})`} />
      <Line
        label="Mismo día semana pasada"
        value={`${formatCurrency(row.sales_same_weekday_last_week)} (${fmtDelta(row.delta_last_week_pct).text})`}
      />
      <Line label="Tickets · promedio" value={`${row.tickets_today} · ${row.avg_ticket === null ? '—' : formatCurrency(row.avg_ticket)}`} />
      <Line label="Efectivo / otros" value={fmtMix(row.mix)} />

      <h4 className="hint" style={TITULO}>Caja</h4>
      <Line
        label="Estado"
        value={c.status === 'OPEN' ? `${c.open_sessions} abierta(s) · ${c.open_hours} h`
          : c.status === 'CLOSED' ? 'cerrada' : 'sin caja'}
      />
      <Line label="Último corte" value={c.last_close_at ? new Date(c.last_close_at).toLocaleString('es-MX') : '—'} />
      <Line label="Diferencia" value={c.last_difference === null ? '—' : formatCurrency(c.last_difference)} />
      {c.last_session_id !== null && (
        <Link to={`/platform/cash-audit/${c.last_session_id}`} className="btn ghost" style={{ marginTop: 8 }}>
          Ver auditoría del último corte
        </Link>
      )}

      <h4 className="hint" style={TITULO}>Devoluciones y cancelaciones</h4>
      <Line label="Pendientes" value={`${row.returns.pending_count} · ${formatCurrency(row.returns.pending_amount)}`} />
      <Line label="La más vieja" value={row.returns.oldest_pending_days === null ? '—' : `${row.returns.oldest_pending_days} días`} />
      <Line label="Aprobadas hoy" value={`${row.returns.approved_today_count} · ${formatCurrency(row.returns.approved_today_amount)}`} />
      <Line label="Canceladas hoy" value={`${row.cancellations_today_count} · ${formatCurrency(row.cancellations_today_amount)}`} />

      <Link to={`/platform/organizations/${row.org_id}`} className="btn ghost" style={{ marginTop: 12 }}>
        Ver organización
      </Link>
    </SideDrawer>
  )
}
