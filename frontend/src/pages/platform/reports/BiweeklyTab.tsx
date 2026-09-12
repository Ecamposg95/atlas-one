import { useEffect, useState } from 'react'
import { reportsMoneyApi } from '../../../api/reportsMoney'
import type { ReportFilters, ReportParams } from '../../../types/reports'
import type { BiweeklyRow, BiweeklyUnit } from '../../../types/reportsMoney'
import { MoneyTable, type MoneyColumn } from './MoneyTable'

interface Props {
  params: ReportParams
  filters: ReportFilters
  unit: BiweeklyUnit
  onUnitChange: (u: BiweeklyUnit) => void
  page: number
  onPageChange: (p: number) => void
}

function money(s: string): string {
  const n = Number(s)
  return Number.isFinite(n)
    ? n.toLocaleString('es-MX', { style: 'currency', currency: 'MXN', maximumFractionDigits: 2 })
    : s
}

export function BiweeklyTab({ params, unit, onUnitChange, page, onPageChange }: Props) {
  const [rows, setRows] = useState<BiweeklyRow[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancel = false
    setLoading(true)
    reportsMoneyApi.getBiweekly({ ...params, unit })
      .then((data) => { if (!cancel) { setRows(data.items); setTotal(data.total); setError(null) } })
      .catch((e: any) => { if (!cancel) setError(e?.response?.data?.detail ?? 'No se pudo cargar el reporte') })
      .finally(() => { if (!cancel) setLoading(false) })
    return () => { cancel = true }
  }, [JSON.stringify(params), unit])

  const columns: MoneyColumn<BiweeklyRow>[] = [
    { key: 'period_label', label: 'Quincena', render: (r) => r.period_label },
    {
      key: 'name',
      label: unit === 'org' ? 'Org' : 'Sucursal',
      render: (r) => unit === 'branch'
        ? <span>{r.name} <span className="hint">· {r.org_name}</span></span>
        : <span>{r.name}</span>,
    },
    { key: 'cash_net', label: 'Efectivo', align: 'right', render: (r) => money(r.cash_net) },
    { key: 'card', label: 'Tarjeta', align: 'right', render: (r) => money(r.card) },
    { key: 'transfer', label: 'Transferencia', align: 'right', render: (r) => money(r.transfer) },
    { key: 'other', label: 'Otros', align: 'right', render: (r) => money(r.other) },
    { key: 'total', label: 'Total', align: 'right', render: (r) => money(r.total) },
    { key: 'tickets', label: 'Tickets', align: 'right', render: (r) => r.tickets },
  ]

  if (error) {
    return <div style={{ padding: 18, color: 'var(--p-danger)', fontSize: 13 }}>{error}</div>
  }
  return (
    <div>
      <div className="pv2-segmented" role="tablist" aria-label="Unidad" style={{ marginBottom: 14 }}>
        <button type="button" role="tab" aria-selected={unit === 'branch'} className={unit === 'branch' ? 'active' : ''} onClick={() => onUnitChange('branch')}>Sucursal</button>
        <button type="button" role="tab" aria-selected={unit === 'org'} className={unit === 'org' ? 'active' : ''} onClick={() => onUnitChange('org')}>Org</button>
      </div>
      <div className={`pv2-money-loading${loading ? ' is-loading' : ''}`}>
        <MoneyTable
          rows={rows}
          columns={columns}
          rowKey={(r) => `${r.period}-${r.unit_id}`}
          emptyMessage="Sin ventas en el periodo"
          total={total}
          page={page}
          onPageChange={onPageChange}
          pageSize={params.limit}
        />
      </div>
    </div>
  )
}
