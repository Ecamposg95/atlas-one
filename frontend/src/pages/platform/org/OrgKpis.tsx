import { formatCurrency } from '../../../utils/currency'
import type { OverviewTotals } from '../../../types/platformOverview'
import { fmtMix } from './orgFormat'

/** Totales de UNA organización: nunca mezclan el dinero de dos clientes. */
export function OrgKpis({ totals }: { totals: OverviewTotals }) {
  const cashShort = totals.units_with_open_session < totals.units
  const returnsPending = totals.returns_pending_count > 0
  return (
    <section className="pv2-org-kpis" aria-label="Totales de la organización">
      <div className="kpi">
        <div className="row">
          <span className="label">Venta hoy</span>
          <i className="fa-solid fa-sack-dollar icon" aria-hidden="true" />
        </div>
        <div className="value">{formatCurrency(totals.sales_today)}</div>
        <div className="foot">{totals.tickets_today} tickets</div>
      </div>

      <div className="kpi">
        <div className="row">
          <span className="label">Cajas abiertas</span>
          <i className="fa-solid fa-cash-register icon" aria-hidden="true" />
        </div>
        <div className="value">{totals.units_with_open_session} / {totals.units}</div>
        <div className="foot">
          <span className={cashShort ? 'pv2-badge-nocut' : undefined}>{totals.open_sessions} sesiones</span>
        </div>
      </div>

      <div className="kpi">
        <div className="row">
          <span className="label">Dev. pendientes</span>
          <i className="fa-solid fa-rotate-left icon" aria-hidden="true" />
        </div>
        <div className="value">{totals.returns_pending_count}</div>
        <div className="foot">
          <span className={returnsPending ? 'pv2-tone-down' : undefined}>
            {formatCurrency(totals.returns_pending_amount)}
          </span>
        </div>
      </div>

      <div className="kpi">
        <div className="row">
          <span className="label">Efectivo / otros</span>
          <i className="fa-solid fa-money-bill-wave icon" aria-hidden="true" />
        </div>
        <div className="value">{fmtMix(totals.mix)}</div>
        <div className="foot">
          {totals.avg_ticket !== null ? `ticket prom. ${formatCurrency(totals.avg_ticket)}` : 'sin ventas'}
        </div>
      </div>
    </section>
  )
}
