import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  alertsApi,
  PlatformAlert,
  PlatformAlertCounts,
} from '../../api/platform'
import { KPICardV2 } from '../../components/platform/v2/KPICardV2'
import { toast } from '../../store/toastStore'
import '../../styles/platform-v2.css'

// ── Types & constants ────────────────────────────────────────────────────────

type SeverityFilter = 'all' | 'critical' | 'warning' | 'info'

const SEVERITY_CHIPS: { value: SeverityFilter; label: string }[] = [
  { value: 'all', label: 'Todas' },
  { value: 'critical', label: 'Critical' },
  { value: 'warning', label: 'Warning' },
  { value: 'info', label: 'Info' },
]

const KIND_OPTIONS = [
  { value: '', label: 'Todos' },
  { value: 'revenue_drop', label: 'Caída de ingresos' },
  { value: 'no_sales_24h', label: 'Sin ventas 24h' },
  { value: 'user_churn', label: 'Churn de usuarios' },
  { value: 'custom', label: 'Custom' },
]

interface SeverityColor {
  token: string
  bg: string
}

function severityColor(severity: string): SeverityColor {
  switch (severity) {
    case 'critical':
      return { token: 'var(--p-danger)', bg: 'rgba(239,68,68,0.12)' }
    case 'warning':
      return { token: 'var(--p-warning)', bg: 'rgba(245,158,11,0.12)' }
    case 'info':
      return { token: 'var(--p-accent)', bg: 'rgba(246, 121, 59,0.12)' }
    default:
      return { token: 'var(--p-muted)', bg: 'rgba(107,107,120,0.18)' }
  }
}

function kindLabel(kind: string): string {
  switch (kind) {
    case 'revenue_drop': return 'Caída de ingresos'
    case 'no_sales_24h': return 'Sin ventas 24h'
    case 'user_churn': return 'Churn'
    case 'custom': return 'Custom'
    default: return kind
  }
}

function relativeTime(iso: string): string {
  const then = new Date(iso).getTime()
  if (!Number.isFinite(then)) return ''
  const diffMs = Date.now() - then
  const sec = Math.floor(diffMs / 1000)
  if (sec < 45) return 'hace un momento'
  const min = Math.floor(sec / 60)
  if (min < 60) return `hace ${min} min`
  const hr = Math.floor(min / 60)
  if (hr < 24) return `hace ${hr} h`
  const day = Math.floor(hr / 24)
  if (day < 7) return `hace ${day} d`
  return new Date(iso).toLocaleDateString('es-MX', { day: '2-digit', month: 'short' })
}

function parseDetail(detail: string | null): unknown {
  if (!detail) return null
  try { return JSON.parse(detail) } catch { return detail }
}

function formatDetail(value: unknown): string {
  if (value == null) return ''
  if (typeof value === 'string') return value
  try { return JSON.stringify(value, null, 2) } catch { return String(value) }
}

// ── Component ────────────────────────────────────────────────────────────────

export function PlatformAlerts() {
  const [alerts, setAlerts] = useState<PlatformAlert[]>([])
  const [counts, setCounts] = useState<PlatformAlertCounts | null>(null)
  const [loading, setLoading] = useState(true)
  const [scanning, setScanning] = useState(false)

  // Filters
  const [severityFilter, setSeverityFilter] = useState<SeverityFilter>('all')
  const [kindFilter, setKindFilter] = useState<string>('')
  const [onlyUnacked, setOnlyUnacked] = useState(false)

  // UI state
  const [expanded, setExpanded] = useState<Set<number>>(new Set())

  const loadAll = () => {
    setLoading(true)
    Promise.all([
      alertsApi.listAlerts({ limit: 500 }),
      alertsApi.alertCounts(),
    ])
      .then(([items, c]) => {
        setAlerts(items)
        setCounts(c)
      })
      .catch((err: { response?: { data?: { detail?: string } } }) =>
        toast.error(err?.response?.data?.detail || 'No se pudieron cargar las alertas')
      )
      .finally(() => setLoading(false))
  }

  useEffect(() => { loadAll() }, [])

  const handleScan = async () => {
    setScanning(true)
    try {
      const res = await alertsApi.scanAlerts()
      if (res.created > 0) {
        toast.success(`Escaneo completado · ${res.created} alertas nuevas · ${res.skipped} duplicadas`)
      } else {
        toast.info(`Sin anomalías nuevas · ${res.skipped} duplicadas`)
      }
      loadAll()
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } }
      toast.error(e?.response?.data?.detail || 'Error al escanear')
    } finally {
      setScanning(false)
    }
  }

  const handleAck = async (id: number) => {
    try {
      await alertsApi.ackAlert(id)
      const now = new Date().toISOString()
      setAlerts(prev => prev.map(a =>
        a.id === id ? { ...a, acked_at: a.acked_at ?? now } : a
      ))
      setCounts(prev => prev ? { ...prev, acked: prev.acked + 1 } : prev)
      toast.success('Alerta marcada como atendida')
    } catch {
      toast.error('No se pudo marcar como atendida')
    }
  }

  const handleResolve = async (id: number) => {
    try {
      await alertsApi.resolveAlert(id)
      const now = new Date().toISOString()
      setAlerts(prev => prev.map(a =>
        a.id === id ? { ...a, resolved_at: a.resolved_at ?? now } : a
      ))
      setCounts(prev => prev
        ? { ...prev, active: Math.max(0, prev.active - 1), resolved: prev.resolved + 1 }
        : prev
      )
      toast.success('Alerta resuelta')
    } catch {
      toast.error('No se pudo resolver la alerta')
    }
  }

  const toggleExpanded = (id: number) => {
    setExpanded(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const filtered = useMemo(() => {
    return alerts.filter(a => {
      if (severityFilter !== 'all' && a.severity !== severityFilter) return false
      if (kindFilter && a.kind !== kindFilter) return false
      if (onlyUnacked && a.acked_at) return false
      return true
    })
  }, [alerts, severityFilter, kindFilter, onlyUnacked])

  const { active, resolved } = useMemo(() => {
    const act: PlatformAlert[] = []
    const res: PlatformAlert[] = []
    for (const a of filtered) {
      if (a.resolved_at) res.push(a)
      else act.push(a)
    }
    return { active: act, resolved: res }
  }, [filtered])

  const resolvedLast7d = useMemo(() => {
    const cutoff = Date.now() - 7 * 24 * 60 * 60 * 1000
    return alerts.filter(a => a.resolved_at && new Date(a.resolved_at).getTime() >= cutoff).length
  }, [alerts])

  const unackedCount = useMemo(
    () => alerts.filter(a => !a.acked_at && !a.resolved_at).length,
    [alerts]
  )

  // ── Render ───────────────────────────────────────────────────────────────

  return (
    <main className="pv2-main">
      {/* Breadcrumb */}
      <div className="crumb">
        <span>Platform</span>
        <span className="sep">/</span>
        <span className="now">Alerts</span>
      </div>

      {/* Page head */}
      <div className="page-head">
        <div>
          <h1>Alertas</h1>
          <div className="sub">
            Anomalías detectadas en la plataforma · revenue drops, inactividad, churn
          </div>
        </div>
        <div className="right" style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div role="group" aria-label="Filtro por severidad" style={pillGroupStyle}>
            {SEVERITY_CHIPS.map(chip => {
              const activeChip = severityFilter === chip.value
              const color = chip.value === 'all'
                ? { token: 'var(--p-text)', bg: 'var(--p-surface-2)' }
                : severityColor(chip.value)
              return (
                <button
                  key={chip.value}
                  type="button"
                  aria-pressed={activeChip}
                  onClick={() => setSeverityFilter(chip.value)}
                  style={{
                    ...pillStyle,
                    background: activeChip ? color.bg : 'transparent',
                    color: activeChip ? color.token : 'var(--p-muted)',
                    borderColor: activeChip ? color.token : 'transparent',
                  }}
                >
                  {chip.label}
                </button>
              )
            })}
          </div>
          <button
            type="button"
            className="btn primary"
            onClick={handleScan}
            disabled={scanning}
            aria-label="Escanear anomalías ahora"
          >
            <i className={scanning ? 'fa-solid fa-spinner fa-spin' : 'fa-solid fa-radar'} />
            {scanning ? 'Escaneando…' : 'Escanear ahora'}
          </button>
        </div>
      </div>

      {/* KPIs */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))',
          gap: 14,
        }}
      >
        <KPICardV2
          label="Activas"
          value={counts?.active ?? '—'}
          icon="fa-bell"
        />
        <KPICardV2
          label="Críticas"
          value={counts?.critical ?? '—'}
          icon="fa-triangle-exclamation"
        />
        <KPICardV2
          label="Sin atender"
          value={unackedCount}
          icon="fa-circle-exclamation"
        />
        <KPICardV2
          label="Resueltas 7d"
          value={resolvedLast7d}
          icon="fa-circle-check"
        />
      </div>

      {/* Filter bar */}
      <section className="card" aria-label="Filtros" style={{ padding: '16px 18px' }}>
        <div
          className="alerts-filters"
          style={{ display: 'flex', flexWrap: 'wrap', gap: 16, alignItems: 'flex-end' }}
        >
          <div style={filterColStyle}>
            <span style={filterLabelStyle}>Tipo</span>
            <select
              value={kindFilter}
              onChange={e => setKindFilter(e.target.value)}
              style={inputStyle}
              aria-label="Tipo de alerta"
            >
              {KIND_OPTIONS.map(o => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>

          <label style={{ ...filterColStyle, cursor: 'pointer', gap: 8 }}>
            <span style={filterLabelStyle}>Estado</span>
            <span style={{ display: 'flex', alignItems: 'center', gap: 8, height: 34 }}>
              <input
                type="checkbox"
                checked={onlyUnacked}
                onChange={e => setOnlyUnacked(e.target.checked)}
                style={{ accentColor: 'var(--p-accent)' }}
              />
              <span style={{ color: 'var(--p-text)', fontSize: 13 }}>
                Solo sin atender
              </span>
            </span>
          </label>
        </div>
      </section>

      {/* Body */}
      {loading ? (
        <AlertsSkeleton />
      ) : filtered.length === 0 ? (
        <EmptyState onScan={handleScan} scanning={scanning} />
      ) : (
        <>
          {active.length > 0 && (
            <section aria-label="Alertas activas" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <div style={sectionHeaderStyle}>
                <span style={sectionHeaderLabelStyle}>Activas</span>
                <span style={sectionHeaderLineStyle} />
                <span style={{ ...sectionHeaderLabelStyle, color: 'var(--p-hint)' }}>
                  {active.length}
                </span>
              </div>
              <div className="card" style={{ padding: 0 }}>
                {active.map((a, idx) => (
                  <AlertRow
                    key={a.id}
                    alert={a}
                    isLast={idx === active.length - 1}
                    isExpanded={expanded.has(a.id)}
                    onToggle={() => toggleExpanded(a.id)}
                    onAck={() => handleAck(a.id)}
                    onResolve={() => handleResolve(a.id)}
                  />
                ))}
              </div>
            </section>
          )}

          {resolved.length > 0 && (
            <details style={{ marginTop: 12 }}>
              <summary style={resolvedSummaryStyle}>
                <i className="fa-solid fa-chevron-right" style={{ marginRight: 8, fontSize: 10 }} />
                Resueltas ({resolved.length})
              </summary>
              <div className="card" style={{ padding: 0, marginTop: 10 }}>
                {resolved.map((a, idx) => (
                  <AlertRow
                    key={a.id}
                    alert={a}
                    isLast={idx === resolved.length - 1}
                    isExpanded={expanded.has(a.id)}
                    onToggle={() => toggleExpanded(a.id)}
                    onAck={() => handleAck(a.id)}
                    onResolve={() => handleResolve(a.id)}
                    muted
                  />
                ))}
              </div>
            </details>
          )}
        </>
      )}

      <style>{`
        @media (max-width: 900px) {
          .alerts-filters { flex-direction: column; align-items: stretch !important; }
          .alerts-filters > * { width: 100%; flex: 1 1 auto !important; }
          .alerts-row { grid-template-columns: 10px 1fr !important; }
          .alerts-row .alerts-actions { grid-column: 1 / -1 !important; justify-content: flex-end; }
        }
      `}</style>
    </main>
  )
}

// ── Row component ────────────────────────────────────────────────────────────

interface AlertRowProps {
  alert: PlatformAlert
  isLast: boolean
  isExpanded: boolean
  onToggle: () => void
  onAck: () => void
  onResolve: () => void
  muted?: boolean
}

function AlertRow({
  alert, isLast, isExpanded, onToggle, onAck, onResolve, muted,
}: AlertRowProps) {
  const color = severityColor(alert.severity)
  const detail = parseDetail(alert.detail)
  const hasDetail = detail !== null && detail !== ''
  const formatted = hasDetail ? formatDetail(detail) : ''
  const isAcked = !!alert.acked_at
  const isResolved = !!alert.resolved_at

  return (
    <div
      className="alerts-row"
      style={{
        display: 'grid',
        gridTemplateColumns: '10px 1fr auto',
        gap: 14,
        padding: '14px 18px',
        alignItems: 'flex-start',
        borderBottom: isLast ? 'none' : '1px solid var(--p-border-2)',
        opacity: muted || isResolved ? 0.55 : isAcked ? 0.8 : 1,
      }}
    >
      {/* Severity dot */}
      <div
        aria-hidden="true"
        style={{
          width: 10,
          height: 10,
          borderRadius: '50%',
          background: color.token,
          marginTop: 6,
          boxShadow: `0 0 0 3px ${color.bg}`,
        }}
      />

      {/* Main content */}
      <div style={{ minWidth: 0, display: 'flex', flexDirection: 'column', gap: 4 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          {alert.organization_id ? (
            <Link
              to={`/platform/organizations/${alert.organization_id}`}
              style={{
                color: 'var(--p-text)',
                fontSize: 13,
                fontWeight: 600,
                textDecoration: 'none',
              }}
            >
              {alert.organization_name || `Org #${alert.organization_id}`}
            </Link>
          ) : (
            <span style={{ color: 'var(--p-text)', fontSize: 13, fontWeight: 600 }}>
              Plataforma
            </span>
          )}
          <span
            style={{
              ...chipStyle,
              background: color.bg,
              color: color.token,
            }}
          >
            {alert.severity}
          </span>
          <span
            style={{
              ...chipStyle,
              background: 'var(--p-surface-2)',
              color: 'var(--p-muted)',
              borderColor: 'var(--p-border)',
            }}
          >
            {kindLabel(alert.kind)}
          </span>
        </div>

        <div style={{ color: 'var(--p-text)', fontSize: 13, fontWeight: 500 }}>
          {alert.title}
        </div>

        <div style={metaLineStyle}>
          <span title={new Date(alert.first_seen).toLocaleString('es-MX')}>
            {relativeTime(alert.first_seen)}
          </span>
          {isAcked && (
            <>
              <span style={dotStyle} />
              <span>Atendida</span>
            </>
          )}
          {isResolved && (
            <>
              <span style={dotStyle} />
              <span>Resuelta</span>
            </>
          )}
        </div>

        {hasDetail && (
          <div style={{ marginTop: 6 }}>
            <button
              type="button"
              onClick={onToggle}
              style={disclosureStyle}
              aria-expanded={isExpanded}
            >
              <i
                className={isExpanded ? 'fa-solid fa-chevron-down' : 'fa-solid fa-chevron-right'}
                style={{ fontSize: 9, marginRight: 6 }}
              />
              detalle
            </button>
            {isExpanded && (
              <pre style={payloadStyle}>{formatted}</pre>
            )}
          </div>
        )}
      </div>

      {/* Actions */}
      <div
        className="alerts-actions"
        style={{ display: 'flex', gap: 6, alignSelf: 'flex-start' }}
      >
        {!isResolved && (
          <>
            {!isAcked && (
              <button
                type="button"
                className="btn primary"
                onClick={onAck}
                style={{ height: 28, padding: '0 10px', fontSize: 11 }}
              >
                <i className="fa-solid fa-check" />
                Ack
              </button>
            )}
            <button
              type="button"
              className="btn ghost"
              onClick={onResolve}
              style={{ height: 28, padding: '0 10px', fontSize: 11 }}
            >
              <i className="fa-solid fa-circle-check" />
              Resolver
            </button>
          </>
        )}
      </div>
    </div>
  )
}

// ── Empty + skeleton ────────────────────────────────────────────────────────

function EmptyState({ onScan, scanning }: { onScan: () => void; scanning: boolean }) {
  return (
    <div
      className="card"
      style={{
        padding: '56px 32px',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 16,
        textAlign: 'center',
      }}
    >
      <div
        style={{
          width: 56, height: 56, borderRadius: 16,
          background: 'var(--p-surface-2)',
          border: '1px solid var(--p-border)',
          display: 'grid', placeItems: 'center',
          color: 'var(--p-muted)', fontSize: 20,
        }}
      >
        <i className="fa-solid fa-bell-slash" />
      </div>
      <div>
        <div style={{ color: 'var(--p-text)', fontSize: 15, fontWeight: 600 }}>
          Todo tranquilo
        </div>
        <div style={{ color: 'var(--p-muted)', fontSize: 12, marginTop: 4 }}>
          No hay alertas coincidentes. Ejecuta un escaneo para detectar anomalías recientes.
        </div>
      </div>
      <button type="button" className="btn primary" onClick={onScan} disabled={scanning}>
        <i className={scanning ? 'fa-solid fa-spinner fa-spin' : 'fa-solid fa-radar'} />
        {scanning ? 'Escaneando…' : 'Escanear ahora'}
      </button>
    </div>
  )
}

function AlertsSkeleton() {
  return (
    <div className="card" style={{ padding: 0 }}>
      {Array.from({ length: 4 }).map((_, i) => (
        <div
          key={i}
          style={{
            display: 'grid',
            gridTemplateColumns: '10px 1fr auto',
            gap: 14,
            padding: '14px 18px',
            alignItems: 'flex-start',
            borderBottom: i === 3 ? 'none' : '1px solid var(--p-border-2)',
          }}
        >
          <span className="sk" style={{ width: 10, height: 10, borderRadius: '50%', marginTop: 6 }} />
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, minWidth: 0 }}>
            <span className="sk" style={{ width: '45%', height: 12, borderRadius: 6 }} />
            <span className="sk" style={{ width: '65%', height: 10, borderRadius: 6 }} />
            <span className="sk" style={{ width: '30%', height: 10, borderRadius: 6 }} />
          </div>
          <span className="sk" style={{ width: 64, height: 26, borderRadius: 8 }} />
        </div>
      ))}
    </div>
  )
}

// ── Styles ───────────────────────────────────────────────────────────────────

const filterLabelStyle: React.CSSProperties = {
  fontSize: 10,
  letterSpacing: '0.12em',
  textTransform: 'uppercase',
  color: 'var(--p-muted)',
  fontWeight: 600,
}

const filterColStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: 6,
  minWidth: 160,
}

const inputStyle: React.CSSProperties = {
  background: 'var(--p-surface-2)',
  border: '1px solid var(--p-border)',
  color: 'var(--p-text)',
  padding: '7px 10px',
  borderRadius: 8,
  fontSize: 13,
  fontFamily: 'inherit',
  height: 34,
  minWidth: 0,
}

const pillGroupStyle: React.CSSProperties = {
  display: 'inline-flex',
  background: 'var(--p-surface)',
  border: '1px solid var(--p-border)',
  borderRadius: 999,
  padding: 3,
  gap: 2,
}

const pillStyle: React.CSSProperties = {
  border: '1px solid transparent',
  padding: '4px 12px',
  borderRadius: 999,
  fontSize: 11,
  fontWeight: 600,
  cursor: 'pointer',
  fontFamily: 'inherit',
  letterSpacing: '0.04em',
  transition: 'background 0.15s ease, color 0.15s ease',
}

const chipStyle: React.CSSProperties = {
  fontFamily: 'var(--font-mono)',
  fontSize: 10,
  letterSpacing: '0.08em',
  textTransform: 'uppercase',
  padding: '3px 10px',
  borderRadius: 999,
  border: '1px solid transparent',
  fontWeight: 700,
  whiteSpace: 'nowrap',
}

const sectionHeaderStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 12,
  padding: '4px 2px',
}

const sectionHeaderLabelStyle: React.CSSProperties = {
  fontFamily: 'var(--font-mono)',
  fontSize: 11,
  letterSpacing: '0.12em',
  textTransform: 'uppercase',
  color: 'var(--p-muted)',
  fontWeight: 600,
  whiteSpace: 'nowrap',
}

const sectionHeaderLineStyle: React.CSSProperties = {
  flex: 1,
  height: 1,
  background: 'var(--p-border-2)',
}

const metaLineStyle: React.CSSProperties = {
  color: 'var(--p-muted)',
  fontFamily: 'var(--font-mono)',
  fontSize: 11,
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  flexWrap: 'wrap',
}

const dotStyle: React.CSSProperties = {
  width: 3,
  height: 3,
  background: 'var(--p-hint)',
  borderRadius: '50%',
  display: 'inline-block',
}

const disclosureStyle: React.CSSProperties = {
  fontFamily: 'var(--font-mono)',
  fontSize: 10,
  letterSpacing: '0.08em',
  textTransform: 'uppercase',
  color: 'var(--p-hint)',
  cursor: 'pointer',
  userSelect: 'none',
  background: 'transparent',
  border: 'none',
  padding: 0,
}

const payloadStyle: React.CSSProperties = {
  marginTop: 8,
  padding: 12,
  background: 'var(--p-sidebar)',
  border: '1px solid var(--p-border)',
  borderRadius: 10,
  fontFamily: 'var(--font-mono)',
  fontSize: 12,
  color: 'var(--p-text)',
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-word',
  maxHeight: 320,
  overflow: 'auto',
  lineHeight: 1.5,
}

const resolvedSummaryStyle: React.CSSProperties = {
  color: 'var(--p-muted)',
  fontFamily: 'var(--font-mono)',
  fontSize: 11,
  letterSpacing: '0.12em',
  textTransform: 'uppercase',
  fontWeight: 600,
  cursor: 'pointer',
  userSelect: 'none',
  padding: '6px 2px',
}
