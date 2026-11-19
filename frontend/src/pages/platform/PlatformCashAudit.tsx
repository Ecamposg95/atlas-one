import { useState, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  cashAuditApi,
  CashAuditLogResponse,
  CashSessionSummary,
  CashAuditEvent,
} from '../../api/cashAudit'
import { formatCurrency } from '../../utils/currency'
import '../../styles/platform-v2.css'

const EVENT_LABELS: Record<string, { label: string; icon: string; color: string }> = {
  SALE_CREATED:      { label: 'Venta',           icon: 'fa-cart-shopping',     color: 'var(--p-success)' },
  PAYMENT_RECORDED:  { label: 'Pago',            icon: 'fa-money-bill',        color: 'var(--p-success)' },
  REFUND_APPROVED:   { label: 'Devolución OK',   icon: 'fa-rotate-left',       color: 'var(--p-warning, #fbbf24)' },
  REFUND_REJECTED:   { label: 'Devolución NO',   icon: 'fa-ban',               color: 'var(--p-muted)' },
  MANUAL_INFLOW:     { label: 'Entrada manual',  icon: 'fa-arrow-down',        color: 'var(--p-success)' },
  MANUAL_OUTFLOW:    { label: 'Salida manual',   icon: 'fa-arrow-up',          color: 'var(--p-warning, #fbbf24)' },
  SESSION_OPENED:    { label: 'Caja abierta',    icon: 'fa-lock-open',         color: 'var(--p-accent)' },
  SESSION_CLOSED:    { label: 'Caja cerrada',    icon: 'fa-lock',              color: 'var(--p-accent)' },
  INVARIANT_FAILED:  { label: 'Invariante FAIL', icon: 'fa-triangle-exclamation', color: 'var(--p-danger)' },
  CLOSURE_WARNING:   { label: 'Aviso cierre',    icon: 'fa-circle-exclamation',color: 'var(--p-warning, #fbbf24)' },
}

function fmtTs(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('es-MX', {
    day: '2-digit', month: '2-digit', year: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
}

function BreakdownLine({ label, amount, sign = '+', bold = false }: { label: string; amount: number; sign?: '+' | '−' | '='; bold?: boolean }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: bold ? 600 : 400 }}>
      <span style={{ color: 'var(--p-text)' }}>{label}</span>
      <span style={{ color: 'var(--p-text)' }}>{sign} {formatCurrency(Math.abs(amount))}</span>
    </div>
  )
}

function SummaryCard({ summary }: { summary: CashSessionSummary }) {
  const cash = summary.payments?.cash?.total ?? 0
  const card = summary.payments?.card?.total ?? 0
  const transfer = summary.payments?.transfer?.total ?? 0
  const refundCash = summary.returns?.cash_refunds ?? 0
  const inflows = summary.movements?.inflows ?? 0
  const outflows = summary.movements?.outflows ?? 0
  const opening = summary.session.opening_balance
  const expected = summary.expected.cash_physical
  const reported = summary.reconciliation.reported
  const diff = summary.reconciliation.difference
  return (
    <div className="card">
      <div className="head"><div className="title">DESGLOSE MATEMÁTICO</div></div>
      <div className="body">
        <BreakdownLine label="Fondo inicial" amount={opening} sign="+" />
        <BreakdownLine label="Ventas efectivo (neto)" amount={cash} sign="+" />
        <BreakdownLine label="Entradas manuales" amount={inflows} sign="+" />
        <BreakdownLine label="Salidas manuales" amount={outflows} sign="−" />
        <BreakdownLine label="Reembolsos efectivo" amount={refundCash} sign="−" />
        <div style={{ borderTop: '1px solid var(--p-border)', margin: '6px 0' }} />
        <BreakdownLine label="ESPERADO en caja" amount={expected} sign="=" bold />
        <BreakdownLine label="Reportado (contado)" amount={reported} sign="=" />
        <div style={{ borderTop: '1px solid var(--p-border)', margin: '6px 0' }} />
        <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', fontFamily: 'var(--font-mono)', fontSize: 14, fontWeight: 600, color: diff < 0 ? 'var(--p-danger)' : (diff > 0 ? 'var(--p-warning, #fbbf24)' : 'var(--p-success)') }}>
          <span>DIFERENCIA</span>
          <span>{diff < 0 ? '−' : (diff > 0 ? '+' : '')} {formatCurrency(Math.abs(diff))}</span>
        </div>
        <div style={{ marginTop: 16, fontSize: 11, color: 'var(--p-muted)', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4 }}>
          <span>Tarjeta: {formatCurrency(card)}</span>
          <span>Transfer: {formatCurrency(transfer)}</span>
          <span>Tickets: {summary.kpis.total_tickets}</span>
          <span>Promedio: {formatCurrency(summary.kpis.avg_ticket)}</span>
        </div>
      </div>
    </div>
  )
}

function TimelineRow({ ev }: { ev: CashAuditEvent }) {
  const meta = EVENT_LABELS[ev.event_type] ?? { label: ev.event_type, icon: 'fa-circle', color: 'var(--p-muted)' }
  return (
    <div style={{
      display: 'grid', gridTemplateColumns: '160px 32px 1fr 130px 100px',
      alignItems: 'center', gap: 12, padding: '10px 12px',
      borderBottom: '1px solid var(--p-border)', fontSize: 12,
    }}>
      <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--p-muted)' }}>{fmtTs(ev.ts)}</span>
      <i className={`fa-solid ${meta.icon}`} style={{ color: meta.color }} />
      <div>
        <div style={{ color: 'var(--p-text)', fontWeight: 500 }}>{meta.label}</div>
        {ev.payload?.reason && <div style={{ fontSize: 10, color: 'var(--p-muted)' }}>{ev.payload.reason}</div>}
        {ev.payload?.warnings && ev.payload.warnings.length > 0 && (
          <div style={{ fontSize: 10, color: 'var(--p-warning, #fbbf24)', marginTop: 2 }}>
            {ev.payload.warnings.length} aviso(s): {ev.payload.warnings.map((w: any) => w.code).join(', ')}
          </div>
        )}
      </div>
      <span style={{ fontFamily: 'var(--font-mono)', textAlign: 'right', color: 'var(--p-text)' }}>
        {ev.amount != null ? formatCurrency(ev.amount) : '—'}
      </span>
      <span style={{ fontFamily: 'var(--font-mono)', textAlign: 'right', color: 'var(--p-muted)', fontSize: 10 }}>
        {ev.related_table}#{ev.related_id?.slice(0, 8) ?? ''}
      </span>
    </div>
  )
}

export function PlatformCashAudit() {
  const { sessionId: paramId } = useParams<{ sessionId: string }>()
  const navigate = useNavigate()
  const [inputId, setInputId] = useState(paramId ?? '')
  const [audit, setAudit] = useState<CashAuditLogResponse | null>(null)
  const [summary, setSummary] = useState<CashSessionSummary | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async (id: number) => {
    setLoading(true); setError(null); setAudit(null); setSummary(null)
    try {
      const [a, s] = await Promise.all([
        cashAuditApi.getAuditLog(id),
        cashAuditApi.getSummary(id),
      ])
      setAudit(a); setSummary(s)
    } catch (e: any) {
      setError(e?.response?.data?.detail || e.message || 'Error')
    } finally { setLoading(false) }
  }, [])

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const id = parseInt(inputId, 10)
    if (!Number.isFinite(id)) return
    navigate(`/platform/cash-audit/${id}`)
    load(id)
  }

  // Auto-load on mount if URL has id
  useState(() => {
    if (paramId) {
      const id = parseInt(paramId, 10)
      if (Number.isFinite(id)) load(id)
    }
  })

  return (
    <main className="pv2-main">
      <div className="crumb">
        <span>Platform</span><span className="sep">/</span>
        <span className="now">Cash Audit</span>
      </div>
      <div className="page-head">
        <div>
          <h1>Cash Audit</h1>
          <div className="sub">Inspección detallada de cualquier sesión de caja · ADMIN</div>
        </div>
        <form onSubmit={onSubmit} style={{ display: 'flex', gap: 8 }}>
          <input
            type="number" placeholder="ID sesión"
            value={inputId} onChange={(e) => setInputId(e.target.value)}
            style={{
              padding: '8px 12px', border: '1px solid var(--p-border)',
              background: 'var(--p-surface)', color: 'var(--p-text)',
              borderRadius: 6, fontFamily: 'var(--font-mono)', fontSize: 13,
              width: 120,
            }}
          />
          <button type="submit" className="btn primary">Inspeccionar</button>
        </form>
      </div>

      {error && (
        <div style={{ padding: 12, background: 'color-mix(in srgb, var(--p-danger) 12%, transparent)', color: 'var(--p-danger)', borderRadius: 6, marginBottom: 12 }}>
          {error}
        </div>
      )}

      {loading && <div style={{ padding: 24, color: 'var(--p-muted)' }}>Cargando…</div>}

      {summary && audit && (
        <>
          <div className="card" style={{ marginBottom: 16 }}>
            <div className="head"><div className="title">SESIÓN #{audit.session_id}</div></div>
            <div className="body" style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16 }}>
              <div><div style={{ fontSize: 11, color: 'var(--p-muted)', textTransform: 'uppercase' }}>Cajero</div><div style={{ fontWeight: 600 }}>{summary.session.user_name}</div></div>
              <div><div style={{ fontSize: 11, color: 'var(--p-muted)', textTransform: 'uppercase' }}>Sucursal</div><div style={{ fontWeight: 600 }}>{summary.session.branch_name}</div></div>
              <div><div style={{ fontSize: 11, color: 'var(--p-muted)', textTransform: 'uppercase' }}>Apertura</div><div style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>{fmtTs(summary.session.opened_at)}</div></div>
              <div><div style={{ fontSize: 11, color: 'var(--p-muted)', textTransform: 'uppercase' }}>Cierre</div><div style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>{summary.session.closed_at ? fmtTs(summary.session.closed_at) : 'OPEN'}</div></div>
            </div>
          </div>

          <section className="row-split" style={{ gridTemplateColumns: '1fr 2fr', marginBottom: 16 }}>
            <SummaryCard summary={summary} />
            <div className="card">
              <div className="head"><div className="title">TIMELINE ({audit.events.length} eventos)</div></div>
              <div className="body" style={{ padding: 0, maxHeight: 600, overflowY: 'auto' }}>
                {audit.events.length === 0 ? (
                  <div style={{ padding: 24, color: 'var(--p-muted)', fontSize: 13 }}>
                    Sin eventos auditados. Esta sesión es anterior a F3 (cash audit log) o no tuvo movimientos.
                  </div>
                ) : (
                  audit.events.map((ev) => <TimelineRow key={ev.id} ev={ev} />)
                )}
              </div>
            </div>
          </section>
        </>
      )}

      {!loading && !audit && !error && (
        <div style={{ padding: 24, color: 'var(--p-muted)', fontSize: 13 }}>
          Ingresá el ID de una sesión de caja para inspeccionar timeline + breakdown.
        </div>
      )}
    </main>
  )
}
