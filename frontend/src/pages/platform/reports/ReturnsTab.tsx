import { useEffect, useState } from 'react'
import { reportsMoneyApi } from '../../../api/reportsMoney'
import type { ReportFilters, ReportParams } from '../../../types/reports'
import type { ReturnsRow } from '../../../types/reportsMoney'
import { MoneyTable, type MoneyColumn } from './MoneyTable'

interface Props {
  params: ReportParams
  filters: ReportFilters
  page: number
  onPageChange: (p: number) => void
  onRowClick: (branchId: number, label: string) => void
}

function money(s: string): string {
  const n = Number(s)
  return Number.isFinite(n)
    ? n.toLocaleString('es-MX', { style: 'currency', currency: 'MXN', maximumFractionDigits: 2 })
    : s
}

function hours(s: string | null): string {
  if (s === null) return '—'
  const n = Number(s)
  return Number.isFinite(n) ? `${n.toFixed(1)} h` : '—'
}

export function ReturnsTab({ params, page, onPageChange, onRowClick }: Props) {
  const [rows, setRows] = useState<ReturnsRow[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancel = false
    setLoading(true)
    reportsMoneyApi.getReturns(params)
      .then((data) => { if (!cancel) { setRows(data.items); setTotal(data.total); setError(null) } })
      .catch((e: any) => { if (!cancel) setError(e?.response?.data?.detail ?? 'No se pudo cargar el reporte') })
      .finally(() => { if (!cancel) setLoading(false) })
    return () => { cancel = true }
  }, [JSON.stringify(params)])

  const columns: MoneyColumn<ReturnsRow>[] = [
    { key: 'name', label: 'Sucursal', render: (r) => <span>{r.name} <span className="hint">· {r.org_name}</span></span> },
    { key: 'pending', label: 'Pendientes', align: 'right', render: (r) => <span>{r.pending_count} <span className="hint">· {money(r.pending_amount)}</span></span> },
    { key: 'approved', label: 'Aprobadas', align: 'right', render: (r) => <span>{r.approved_count} <span className="hint">· {money(r.approved_amount)}</span></span> },
    { key: 'cash', label: 'Efectivo', align: 'right', render: (r) => money(r.by_method.cash) },
    { key: 'card', label: 'Tarjeta', align: 'right', render: (r) => money(r.by_method.card) },
    { key: 'avg_hours_to_approve', label: 'Horas a aprobar', align: 'right', render: (r) => hours(r.avg_hours_to_approve) },
    { key: 'top_reasons', label: 'Motivos', render: (r) => r.top_reasons.join(' · ') || '—' },
  ]

  if (error) {
    return <div style={{ padding: 18, color: 'var(--p-danger)', fontSize: 13 }}>{error}</div>
  }
  return (
    <div style={{ opacity: loading ? 0.55 : 1, transition: 'opacity 0.15s ease' }}>
      <MoneyTable
        rows={rows}
        columns={columns}
        rowKey={(r) => r.branch_id}
        onRowClick={(r) => onRowClick(r.branch_id, r.name)}
        emptyMessage="Sin devoluciones en el periodo"
        total={total}
        page={page}
        onPageChange={onPageChange}
        pageSize={params.limit}
      />
    </div>
  )
}
