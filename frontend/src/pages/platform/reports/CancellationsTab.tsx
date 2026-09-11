import { useEffect, useState } from 'react'
import { reportsMoneyApi } from '../../../api/reportsMoney'
import type { ReportFilters, ReportParams } from '../../../types/reports'
import type { CancellationsRow } from '../../../types/reportsMoney'
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

function who(r: CancellationsRow): string {
  const first = r.by_user[0]
  if (!first) return '—'
  const rest = r.by_user.length - 1
  return rest > 0 ? `${first.full_name} +${rest}` : first.full_name
}

export function CancellationsTab({ params, page, onPageChange, onRowClick }: Props) {
  const [rows, setRows] = useState<CancellationsRow[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancel = false
    setLoading(true)
    reportsMoneyApi.getCancellations(params)
      .then((data) => { if (!cancel) { setRows(data.items); setTotal(data.total); setError(null) } })
      .catch((e: any) => { if (!cancel) setError(e?.response?.data?.detail ?? 'No se pudo cargar el reporte') })
      .finally(() => { if (!cancel) setLoading(false) })
    return () => { cancel = true }
  }, [JSON.stringify(params)])

  const columns: MoneyColumn<CancellationsRow>[] = [
    { key: 'name', label: 'Sucursal', render: (r) => <span>{r.name} <span className="hint">· {r.org_name}</span></span> },
    { key: 'count', label: 'Canceladas', align: 'right', render: (r) => r.count },
    { key: 'amount', label: 'Monto', align: 'right', render: (r) => money(r.amount) },
    { key: 'by_user', label: 'Quién', render: (r) => who(r) },
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
        emptyMessage="Sin cancelaciones en el periodo"
        total={total}
        page={page}
        onPageChange={onPageChange}
        pageSize={params.limit}
      />
    </div>
  )
}
