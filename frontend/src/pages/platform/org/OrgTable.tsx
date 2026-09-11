import { DataTable, type DataTableColumn } from '../../../components/platform/DataTable'
import { formatCurrency } from '../../../utils/currency'
import type { BranchOverviewRow } from '../../../types/platformOverview'
import { fmtDelta, fmtMix, sortRowsBySales } from './orgFormat'

function Delta({ pct }: { pct: number | null }) {
  const d = fmtDelta(pct)
  return <span className={`mono pv2-tone-${d.tone}`}>{d.text}</span>
}

function CashBadge({ row }: { row: BranchOverviewRow }) {
  const c = row.cash
  if (c.status === 'OPEN') {
    const late = (c.open_hours ?? 0) > 14
    return (
      <span className={late ? 'pv2-badge-nocut' : 'pv2-badge-open'}>
        {late ? `sin corte ${c.open_hours} h` : 'abierta'}
      </span>
    )
  }
  if (c.status === 'CLOSED') {
    if (c.last_difference && c.last_difference !== 0) {
      return <span className="pv2-badge-diff">{formatCurrency(c.last_difference)} corte</span>
    }
    return <span className="muted">cerrada ✓</span>
  }
  return <span className="hint">sin caja</span>
}

interface Props {
  rows: BranchOverviewRow[]
  onRowClick: (row: BranchOverviewRow) => void
}

/** Las sucursales de la organización seleccionada, ordenadas por venta. */
export function OrgTable({ rows, onRowClick }: Props) {
  const columns: DataTableColumn<BranchOverviewRow>[] = [
    { key: 'name', label: 'Sucursal', sortable: true, sortValue: (r) => r.name,
      accessor: (r) => <span>{r.name}</span> },
    { key: 'sales_today', label: 'Venta hoy', sortable: true, sortValue: (r) => r.sales_today,
      accessor: (r) => <span className="mono">{formatCurrency(r.sales_today)}</span> },
    { key: 'delta_yesterday_pct', label: 'Δ ayer', sortable: true,
      sortValue: (r) => r.delta_yesterday_pct ?? -Infinity,
      accessor: (r) => <Delta pct={r.delta_yesterday_pct} /> },
    { key: 'delta_last_week_pct', label: 'Δ sem.', sortable: true,
      sortValue: (r) => r.delta_last_week_pct ?? -Infinity,
      accessor: (r) => <Delta pct={r.delta_last_week_pct} /> },
    { key: 'mix', label: 'Efec. / otros', sortable: true, sortValue: (r) => r.mix.cash_pct ?? -1,
      accessor: (r) => <span className="mono">{fmtMix(r.mix)}</span> },
    { key: 'avg_ticket', label: 'Tkt prom.', sortable: true, sortValue: (r) => r.avg_ticket ?? -1,
      accessor: (r) => <span className="mono">{r.avg_ticket === null ? '—' : formatCurrency(r.avg_ticket)}</span> },
    { key: 'cash', label: 'Caja', accessor: (r) => <CashBadge row={r} /> },
    { key: 'returns', label: 'Dev. pend.', sortable: true, sortValue: (r) => r.returns.pending_amount,
      accessor: (r) => r.returns.pending_count === 0 ? <span className="hint">—</span>
        : <span className="mono">{r.returns.pending_count} · {formatCurrency(r.returns.pending_amount)}</span> },
  ]
  return (
    <div>
      <div className="pv2-org-toolbar">
        <span className="hint">{rows.length} sucursales · ordenado por venta</span>
      </div>
      <DataTable<BranchOverviewRow>
        data={sortRowsBySales(rows)}
        columns={columns}
        rowKey={(r) => r.id}
        searchable
        searchKeys={(r) => r.name}
        pageSize={50}
        onRowClick={onRowClick}
        emptyMessage="Esta organización no tiene sucursales activas que vendan"
      />
    </div>
  )
}
