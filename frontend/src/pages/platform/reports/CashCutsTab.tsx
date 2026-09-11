import { useEffect, useState } from 'react'
import { reportsMoneyApi } from '../../../api/reportsMoney'
import type { ReportFilters, ReportParams } from '../../../types/reports'
import type { CashCutRow } from '../../../types/reportsMoney'
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

export function CashCutsTab({ params, page, onPageChange, onRowClick }: Props) {
  const [rows, setRows] = useState<CashCutRow[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancel = false
    setLoading(true)
    reportsMoneyApi.getCashCuts(params)
      .then((data) => { if (!cancel) { setRows(data.items); setTotal(data.total); setError(null) } })
      .catch((e: any) => { if (!cancel) setError(e?.response?.data?.detail ?? 'No se pudo cargar el reporte') })
      .finally(() => { if (!cancel) setLoading(false) })
    return () => { cancel = true }
  }, [JSON.stringify(params)])

  const columns: MoneyColumn<CashCutRow>[] = [
    { key: 'name', label: 'Sucursal', render: (r) => <span>{r.name} <span className="hint">· {r.org_name}</span></span> },
    { key: 'sessions_closed', label: 'Cortes', align: 'right', render: (r) => r.sessions_closed },
    { key: 'sessions_with_difference', label: 'Con diferencia', align: 'right', render: (r) => r.sessions_with_difference },
    { key: 'shortage_total', label: 'Faltante al cierre', align: 'right', render: (r) => <span className="pv2-tone-down">{money(r.shortage_total)}</span> },
    { key: 'overage_total', label: 'Sobrante al cierre', align: 'right', render: (r) => money(r.overage_total) },
    { key: 'avg_abs_difference', label: 'Dif. prom. al cierre', align: 'right', render: (r) => money(r.avg_abs_difference) },
    { key: 'sessions_open_unclosed', label: 'Sin cerrar', align: 'right', render: (r) => r.sessions_open_unclosed || '—' },
  ]

  if (error) {
    return <div style={{ padding: 18, color: 'var(--p-danger)', fontSize: 13 }}>{error}</div>
  }
  return (
    <div className={`pv2-money-loading${loading ? ' is-loading' : ''}`}>
      <MoneyTable
        rows={rows}
        columns={columns}
        rowKey={(r) => r.branch_id}
        onRowClick={(r) => onRowClick(r.branch_id, r.name)}
        emptyMessage="Sin cortes en el periodo"
        total={total}
        page={page}
        onPageChange={onPageChange}
        pageSize={params.limit}
      />
    </div>
  )
}
