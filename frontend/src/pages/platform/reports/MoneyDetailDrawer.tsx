import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { SideDrawer } from '../../../components/platform/SideDrawer'
import { reportsMoneyApi } from '../../../api/reportsMoney'
import type { ReportParams } from '../../../types/reports'
import type { CashCutDetail, CancellationsDetail, MoneyTab, ReturnsDetail } from '../../../types/reportsMoney'

type Payload =
  | { kind: 'cortes'; data: CashCutDetail }
  | { kind: 'devoluciones'; data: ReturnsDetail }
  | { kind: 'cancelaciones'; data: CancellationsDetail }

interface Props {
  tab: MoneyTab
  branchId: number | null
  branchLabel: string
  params: ReportParams
  onClose: () => void
}

function money(s: string): string {
  const n = Number(s)
  return Number.isFinite(n)
    ? n.toLocaleString('es-MX', { style: 'currency', currency: 'MXN', maximumFractionDigits: 2 })
    : s
}

function fmtWhen(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isFinite(d.getTime()) ? d.toLocaleString('es-MX') : iso
}

const rowStyle: React.CSSProperties = {
  display: 'flex', justifyContent: 'space-between', gap: 12,
  padding: '8px 0', borderBottom: '1px solid var(--p-border-2)', fontSize: 12,
}

/** El drawer pide una sola página. Callarlo hacía creer que eso era todo. */
function Truncado({ mostrados, total }: { mostrados: number; total: number }) {
  if (total <= mostrados) return null
  return (
    <p className="hint" style={{ margin: '10px 0 0', fontSize: 11 }}>
      Mostrando los primeros {mostrados} de {total}. Usa el CSV para la lista completa.
    </p>
  )
}

export function MoneyDetailDrawer({ tab, branchId, branchLabel, params, onClose }: Props) {
  const [payload, setPayload] = useState<Payload | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (branchId === null || tab === 'quincenal') { setPayload(null); return }
    let cancel = false
    setLoading(true)
    const fetcher =
      tab === 'cortes' ? reportsMoneyApi.getCashCutDetail(branchId, params).then((d) => ({ kind: 'cortes', data: d } as Payload))
      : tab === 'devoluciones' ? reportsMoneyApi.getReturnsDetail(branchId, params).then((d) => ({ kind: 'devoluciones', data: d } as Payload))
      : reportsMoneyApi.getCancellationsDetail(branchId, params).then((d) => ({ kind: 'cancelaciones', data: d } as Payload))
    fetcher
      .then((p) => { if (!cancel) setPayload(p) })
      .catch(() => { if (!cancel) setPayload(null) })
      .finally(() => { if (!cancel) setLoading(false) })
    return () => { cancel = true }
  }, [tab, branchId, JSON.stringify(params)])

  if (branchId === null || tab === 'quincenal') return null

  return (
    <SideDrawer open title={branchLabel} subtitle={loading ? 'Cargando…' : undefined} onClose={onClose}>
      {payload?.kind === 'cortes' && (
        <>
          <h4 className="hint" style={{ margin: '4px 0 8px', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Por cajera</h4>
          {payload.data.by_cashier.map((c) => (
            <div key={c.user_id} style={rowStyle}>
              <span>{c.full_name} <span className="hint">· {c.sessions} corte(s)</span></span>
              <span className="mono pv2-tone-down">{money(c.shortage_total)}</span>
            </div>
          ))}
          <h4 className="hint" style={{ margin: '14px 0 8px', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Cortes</h4>
          {payload.data.sessions.map((s) => (
            <div key={s.session_id} style={rowStyle}>
              <span>
                <Link to={`/platform/cash-audit/${s.session_id}`} style={{ color: 'var(--p-accent)' }}>
                  #{s.session_id}
                </Link>
                {' · '}{s.cashier} <span className="hint">{fmtWhen(s.closed_at)}</span>
              </span>
              <span className="mono">{money(s.difference)}</span>
            </div>
          ))}
          <Truncado mostrados={payload.data.sessions.length} total={payload.data.total} />
        </>
      )}
      {payload?.kind === 'devoluciones' && (
        <>
          {payload.data.items.map((r) => (
            <div key={r.return_id} style={rowStyle}>
              <span>{r.folio} · {r.status} <span className="hint">{r.reason}</span></span>
              <span className="mono">{money(r.amount)}</span>
            </div>
          ))}
          <Truncado mostrados={payload.data.items.length} total={payload.data.total} />
        </>
      )}
      {payload?.kind === 'cancelaciones' && (
        <>
          {payload.data.items.map((c) => (
            <div key={c.event_id} style={rowStyle}>
              <span>{c.folio} · {c.user} <span className="hint">{c.reason}</span></span>
              <span className="mono">{money(c.amount)}</span>
            </div>
          ))}
          <Truncado mostrados={payload.data.items.length} total={payload.data.total} />
        </>
      )}
    </SideDrawer>
  )
}
