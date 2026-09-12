import { useEffect, useState } from 'react'
import { reportApi } from '../../api/platform'
import { SideDrawer } from './SideDrawer'
import type {
  ReportTab,
  ReportFilters,
  ProductDetailResponse,
  BranchDetailResponse,
  SellerDetailResponse,
  CustomerDetailResponse,
} from '../../types/reports'

interface Props {
  tab: ReportTab
  entityId: string | number | null
  entityLabel: string
  filters: ReportFilters
  onClose: () => void
}

type DetailPayload =
  | { kind: 'productos'; data: ProductDetailResponse }
  | { kind: 'sucursales'; data: BranchDetailResponse }
  | { kind: 'vendedores'; data: SellerDetailResponse }
  | { kind: 'clientes'; data: CustomerDetailResponse }

const cellStyle: React.CSSProperties = {
  padding: '10px 12px',
  borderBottom: '1px solid var(--p-border-2)',
  fontSize: 12,
  color: 'var(--p-text)',
  verticalAlign: 'middle',
}

const headerStyle: React.CSSProperties = {
  padding: '8px 12px',
  textAlign: 'left',
  color: 'var(--p-hint)',
  fontSize: 10,
  textTransform: 'uppercase',
  letterSpacing: '0.12em',
  fontWeight: 500,
  borderBottom: '1px solid var(--p-border)',
}

const sectionTitle: React.CSSProperties = {
  fontFamily: 'var(--font-display)',
  fontSize: 14,
  fontWeight: 600,
  margin: '4px 0 10px',
  color: 'var(--p-text)',
  letterSpacing: '-0.01em',
}

function fmtDate(iso: string): string {
  const d = new Date(iso)
  if (!Number.isFinite(d.getTime())) return iso
  return d.toLocaleString('es-MX', { dateStyle: 'short', timeStyle: 'short' })
}

function fmtMoney(s: string): string {
  const n = Number(s)
  if (!Number.isFinite(n)) return s
  return n.toLocaleString('es-MX', { style: 'currency', currency: 'MXN', maximumFractionDigits: 2 })
}

function isoDate(d: Date): string {
  const yy = d.getFullYear()
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  return `${yy}-${mm}-${dd}`
}

function resolveRange(filters: ReportFilters): { start?: string; end?: string } {
  if (filters.range === 'custom') return { start: filters.start, end: filters.end }
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const end = isoDate(today)
  const startDate = new Date(today)
  if (filters.range === '7d')      startDate.setDate(startDate.getDate() - 7)
  else if (filters.range === '90d') startDate.setDate(startDate.getDate() - 90)
  else if (filters.range === '12m') startDate.setFullYear(startDate.getFullYear() - 1)
  else                              startDate.setDate(startDate.getDate() - 30)
  return { start: isoDate(startDate), end }
}

function detailParams(filters: ReportFilters): Record<string, any> {
  const out: Record<string, any> = { limit: 100, offset: 0 }
  const { start, end } = resolveRange(filters)
  if (start) out.start = start
  if (end) out.end = end
  if (filters.org_id !== undefined) out.org_id = filters.org_id
  if (filters.branch_id !== undefined) out.branch_id = filters.branch_id
  return out
}

export function ReportDrillDownDrawer({ tab, entityId, entityLabel, filters, onClose }: Props) {
  const [payload, setPayload] = useState<DetailPayload | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const open = entityId !== null

  const fetchDetail = async () => {
    if (entityId === null) return
    setLoading(true)
    setError(null)
    setPayload(null)
    try {
      const params = detailParams(filters)
      if (tab === 'productos') {
        const data = await reportApi.getProductDetail(String(entityId), params)
        setPayload({ kind: 'productos', data })
      } else if (tab === 'sucursales') {
        const data = await reportApi.getBranchDetail(Number(entityId), params)
        setPayload({ kind: 'sucursales', data })
      } else if (tab === 'vendedores') {
        const data = await reportApi.getSellerDetail(Number(entityId), params)
        setPayload({ kind: 'vendedores', data })
      } else {
        const data = await reportApi.getCustomerDetail(Number(entityId), params)
        setPayload({ kind: 'clientes', data })
      }
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? e?.message ?? 'Error cargando detalle')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchDetail()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entityId, tab, JSON.stringify(filters)])

  return (
    <SideDrawer
      open={open}
      title={entityLabel || 'Detalle'}
      subtitle={open ? `Drill-down · ${tab}` : undefined}
      onClose={onClose}
      width={720}
    >
      {loading && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {Array.from({ length: 6 }).map((_, i) => (
            <div
              key={i}
              style={{
                height: 28,
                background: 'var(--p-surface-2)',
                borderRadius: 6,
                opacity: 0.6,
              }}
            />
          ))}
        </div>
      )}

      {error && !loading && (
        <div style={{
          padding: 16,
          border: '1px solid var(--p-border)',
          borderRadius: 10,
          background: 'rgba(239, 68, 68, 0.08)',
          color: 'var(--p-text)',
          fontSize: 13,
          display: 'flex',
          flexDirection: 'column',
          gap: 10,
        }}>
          <span>{error}</span>
          <button
            type="button"
            onClick={fetchDetail}
            style={{
              alignSelf: 'flex-start',
              background: 'var(--p-surface-2)',
              border: '1px solid var(--p-border)',
              color: 'var(--p-text)',
              padding: '6px 12px',
              borderRadius: 8,
              fontSize: 12,
              cursor: 'pointer',
            }}
          >
            Reintentar
          </button>
        </div>
      )}

      {!loading && !error && payload && (
        <DrillDownContent payload={payload} />
      )}
    </SideDrawer>
  )
}

function DrillDownContent({ payload }: { payload: DetailPayload }) {
  if (payload.kind === 'productos') {
    const { data } = payload
    return (
      <div>
        <h3 style={sectionTitle}>{data.product_name}</h3>
        <p style={{ fontSize: 12, color: 'var(--p-muted)', margin: '0 0 14px' }}>
          {data.total} venta(s) en el rango.
        </p>
        <div className="pv2-scroll-x">
          <table style={{ width: '100%', borderCollapse: 'separate', borderSpacing: 0, minWidth: 640 }}>
            <thead>
              <tr>
                <th style={headerStyle}>Folio</th>
                <th style={headerStyle}>Fecha</th>
                <th style={headerStyle}>Org</th>
                <th style={headerStyle}>Sucursal</th>
                <th style={headerStyle}>Cajero</th>
                <th style={{ ...headerStyle, textAlign: 'right' }}>Cant</th>
                <th style={{ ...headerStyle, textAlign: 'right' }}>Unit</th>
                <th style={{ ...headerStyle, textAlign: 'right' }}>Total</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((r) => (
                <tr key={r.document_id + ':' + r.folio}>
                  <td style={cellStyle}>{r.series}-{r.folio}</td>
                  <td style={cellStyle}>{fmtDate(r.created_at)}</td>
                  <td style={cellStyle}>{r.org_name}</td>
                  <td style={cellStyle}>{r.branch_name}</td>
                  <td style={cellStyle}>{r.seller_name}</td>
                  <td style={{ ...cellStyle, textAlign: 'right', fontFamily: 'var(--font-mono)' }}>{r.quantity}</td>
                  <td style={{ ...cellStyle, textAlign: 'right', fontFamily: 'var(--font-mono)' }}>{fmtMoney(r.unit_price)}</td>
                  <td style={{ ...cellStyle, textAlign: 'right', fontFamily: 'var(--font-mono)' }}>{fmtMoney(r.total_line)}</td>
                </tr>
              ))}
              {data.items.length === 0 && (
                <tr><td style={{ ...cellStyle, textAlign: 'center', color: 'var(--p-muted)' }} colSpan={8}>Sin movimientos.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    )
  }

  if (payload.kind === 'sucursales') {
    const { data } = payload
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
        <h3 style={sectionTitle}>{data.branch_name}</h3>

        <div>
          <h4 style={{ ...sectionTitle, fontSize: 12, color: 'var(--p-hint)', textTransform: 'uppercase', letterSpacing: '0.12em' }}>
            Top productos
          </h4>
          <div className="pv2-scroll-x">
            <table style={{ width: '100%', borderCollapse: 'separate', borderSpacing: 0, minWidth: 640 }}>
              <thead>
                <tr>
                  <th style={headerStyle}>SKU</th>
                  <th style={headerStyle}>Nombre</th>
                  <th style={{ ...headerStyle, textAlign: 'right' }}>Unidades</th>
                  <th style={{ ...headerStyle, textAlign: 'right' }}>Revenue</th>
                </tr>
              </thead>
              <tbody>
                {data.top_products.map((p, i) => (
                  <tr key={i}>
                    <td style={{ ...cellStyle, fontFamily: 'var(--font-mono)' }}>{p.sku}</td>
                    <td style={cellStyle}>{p.name}</td>
                    <td style={{ ...cellStyle, textAlign: 'right', fontFamily: 'var(--font-mono)' }}>{p.units}</td>
                    <td style={{ ...cellStyle, textAlign: 'right', fontFamily: 'var(--font-mono)' }}>{fmtMoney(p.revenue)}</td>
                  </tr>
                ))}
                {data.top_products.length === 0 && (
                  <tr><td style={{ ...cellStyle, textAlign: 'center', color: 'var(--p-muted)' }} colSpan={4}>Sin productos.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div>
          <h4 style={{ ...sectionTitle, fontSize: 12, color: 'var(--p-hint)', textTransform: 'uppercase', letterSpacing: '0.12em' }}>
            Top vendedores
          </h4>
          <div className="pv2-scroll-x">
            <table style={{ width: '100%', borderCollapse: 'separate', borderSpacing: 0, minWidth: 640 }}>
              <thead>
                <tr>
                  <th style={headerStyle}>Nombre</th>
                  <th style={{ ...headerStyle, textAlign: 'right' }}>Transacciones</th>
                  <th style={{ ...headerStyle, textAlign: 'right' }}>Revenue</th>
                </tr>
              </thead>
              <tbody>
                {data.top_sellers.map((s, i) => (
                  <tr key={i}>
                    <td style={cellStyle}>{s.full_name}</td>
                    <td style={{ ...cellStyle, textAlign: 'right', fontFamily: 'var(--font-mono)' }}>{s.transactions}</td>
                    <td style={{ ...cellStyle, textAlign: 'right', fontFamily: 'var(--font-mono)' }}>{fmtMoney(s.revenue)}</td>
                  </tr>
                ))}
                {data.top_sellers.length === 0 && (
                  <tr><td style={{ ...cellStyle, textAlign: 'center', color: 'var(--p-muted)' }} colSpan={3}>Sin vendedores.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    )
  }

  if (payload.kind === 'vendedores') {
    const { data } = payload
    return (
      <div>
        <h3 style={sectionTitle}>{data.full_name}</h3>
        <p style={{ fontSize: 12, color: 'var(--p-muted)', margin: '0 0 14px' }}>
          {data.total} venta(s).
        </p>
        <div className="pv2-scroll-x">
          <table style={{ width: '100%', borderCollapse: 'separate', borderSpacing: 0, minWidth: 640 }}>
            <thead>
              <tr>
                <th style={headerStyle}>Folio</th>
                <th style={headerStyle}>Fecha</th>
                <th style={headerStyle}>Sucursal</th>
                <th style={headerStyle}>Cliente</th>
                <th style={{ ...headerStyle, textAlign: 'right' }}>Total</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((r) => (
                <tr key={r.document_id}>
                  <td style={cellStyle}>{r.folio}</td>
                  <td style={cellStyle}>{fmtDate(r.created_at)}</td>
                  <td style={cellStyle}>{r.branch_name}</td>
                  <td style={cellStyle}>{r.customer_name ?? <span style={{ color: 'var(--p-muted)' }}>—</span>}</td>
                  <td style={{ ...cellStyle, textAlign: 'right', fontFamily: 'var(--font-mono)' }}>{fmtMoney(r.total_amount)}</td>
                </tr>
              ))}
              {data.items.length === 0 && (
                <tr><td style={{ ...cellStyle, textAlign: 'center', color: 'var(--p-muted)' }} colSpan={5}>Sin ventas.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    )
  }

  // clientes
  const { data } = payload
  return (
    <div>
      <h3 style={sectionTitle}>{data.customer_name}</h3>
      <p style={{ fontSize: 12, color: 'var(--p-muted)', margin: '0 0 14px' }}>
        {data.total} ticket(s).
      </p>
      <div className="pv2-scroll-x">
        <table style={{ width: '100%', borderCollapse: 'separate', borderSpacing: 0, minWidth: 640 }}>
          <thead>
            <tr>
              <th style={headerStyle}>Folio</th>
              <th style={headerStyle}>Fecha</th>
              <th style={headerStyle}>Sucursal</th>
              <th style={headerStyle}>Pago</th>
              <th style={headerStyle}>Estado</th>
              <th style={{ ...headerStyle, textAlign: 'right' }}>Total</th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((r) => (
              <tr key={r.document_id}>
                <td style={cellStyle}>{r.folio}</td>
                <td style={cellStyle}>{fmtDate(r.created_at)}</td>
                <td style={cellStyle}>{r.branch_name}</td>
                <td style={cellStyle}>{r.payment_method ?? '—'}</td>
                <td style={cellStyle}>{r.status}</td>
                <td style={{ ...cellStyle, textAlign: 'right', fontFamily: 'var(--font-mono)' }}>{fmtMoney(r.total_amount)}</td>
              </tr>
            ))}
            {data.items.length === 0 && (
              <tr><td style={{ ...cellStyle, textAlign: 'center', color: 'var(--p-muted)' }} colSpan={6}>Sin tickets.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
