import { useEffect, useMemo, useState } from 'react'
import { platformApi, AuditLog, PlatformUser } from '../../api/platform'
import { toast } from '../../store/toastStore'

import '../../styles/platform-v2.css'

// ── Constants ────────────────────────────────────────────────────────────────

const PAGE_SIZE = 50

// Common action kinds offered as quick-filter chips. The user can still type
// arbitrary values in the free-text search; these are just fast paths.
const ACTION_CHIPS: string[] = [
  'CREATE',
  'UPDATE',
  'DELETE',
  'ARCHIVE',
  'ACTIVATE',
  'SUSPEND',
  'IMPERSONATE',
  'BOOTSTRAP',
]

// ── Helpers ──────────────────────────────────────────────────────────────────

interface ActionColor {
  token: string   // css var name (for full color)
  bg: string      // rgba for soft background
}

function actionColor(action: string): ActionColor {
  const A = action.toUpperCase()
  // IMPERSONATE first — reuses --p-magenta exclusively here.
  if (A.startsWith('IMPERSONATE')) {
    return { token: 'var(--p-magenta)', bg: 'rgba(211, 96, 38,0.12)' }
  }
  if (
    A.startsWith('DELETE') ||
    A.startsWith('ARCHIVE') ||
    A.startsWith('SUSPEND') ||
    A.startsWith('REVOKE')
  ) {
    return { token: 'var(--p-danger)', bg: 'rgba(239,68,68,0.12)' }
  }
  if (
    A.startsWith('CREATE') ||
    A.startsWith('BOOTSTRAP') ||
    A.startsWith('ACTIVATE') ||
    A.startsWith('UNARCHIVE') ||
    A.startsWith('INVITE')
  ) {
    return { token: 'var(--p-success)', bg: 'rgba(34,197,94,0.12)' }
  }
  if (
    A.startsWith('UPDATE') ||
    A.startsWith('PATCH') ||
    A.startsWith('CHANGE') ||
    A.startsWith('TOGGLE') ||
    A.startsWith('APPLY')
  ) {
    return { token: 'var(--p-accent)', bg: 'rgba(246, 121, 59,0.12)' }
  }
  return { token: 'var(--p-muted)', bg: 'rgba(107,107,120,0.18)' }
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return '?'
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
}

function parsePayload(payload: string | null): unknown {
  if (!payload) return null
  try { return JSON.parse(payload) } catch { return payload }
}

function formatPayload(value: unknown): string {
  if (value == null) return ''
  if (typeof value === 'string') return value
  try { return JSON.stringify(value, null, 2) } catch { return String(value) }
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

function formatClock(iso: string): string {
  return new Date(iso).toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' })
}

function dayKey(iso: string): string {
  const d = new Date(iso)
  d.setHours(0, 0, 0, 0)
  return d.toISOString().slice(0, 10)
}

function dayLabel(iso: string): string {
  const d = new Date(iso)
  d.setHours(0, 0, 0, 0)
  const today = new Date(); today.setHours(0, 0, 0, 0)
  const yday = new Date(today); yday.setDate(yday.getDate() - 1)
  const sameYear = d.getFullYear() === today.getFullYear()
  const dayStr = d.toLocaleDateString('es-MX', {
    day: '2-digit',
    month: 'short',
    ...(sameYear ? {} : { year: 'numeric' }),
  })
  if (d.getTime() === today.getTime()) return `Hoy · ${dayStr}`
  if (d.getTime() === yday.getTime()) return `Ayer · ${dayStr}`
  return dayStr
}

// ── Component ────────────────────────────────────────────────────────────────

export function PlatformAuditLog() {
  const [logs, setLogs] = useState<AuditLog[]>([])
  const [users, setUsers] = useState<PlatformUser[]>([])
  const [loading, setLoading] = useState(true)
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE)

  // Filters
  const [actionChips, setActionChips] = useState<string[]>([])
  const [entityType, setEntityType] = useState<string>('')
  const [actorQuery, setActorQuery] = useState<string>('')
  const [startDate, setStartDate] = useState<string>('')
  const [endDate, setEndDate] = useState<string>('')

  // Expanded payload rows
  const [expanded, setExpanded] = useState<Set<number>>(new Set())

  // ── Fetch users once (for actor display) ───────────────────────────────────
  useEffect(() => {
    platformApi.getUsers({ include_inactive: true })
      .then(setUsers)
      .catch(() => { /* silent — fall back to id only */ })
  }, [])

  // ── Fetch logs when server-side filters change ─────────────────────────────
  useEffect(() => {
    setLoading(true)
    setVisibleCount(PAGE_SIZE)
    const params: Record<string, unknown> = { limit: 1000, offset: 0 }
    if (startDate) params.start_date = startDate
    if (endDate) params.end_date = `${endDate}T23:59:59`
    if (entityType) params.entity_type = entityType
    platformApi.getAuditLogs(params as never)
      .then((res) => setLogs(res.items))
      .catch((err: { response?: { data?: { detail?: string } } }) =>
        toast.error(err?.response?.data?.detail || 'No se pudo cargar el audit log')
      )
      .finally(() => setLoading(false))
  }, [startDate, endDate, entityType])

  // ── Index users by id ──────────────────────────────────────────────────────
  const userMap = useMemo(() => {
    const m = new Map<number, PlatformUser>()
    users.forEach((u) => m.set(u.id, u))
    return m
  }, [users])

  const actorLabel = (id: number): string => {
    const u = userMap.get(id)
    if (!u) return `User #${id}`
    return u.full_name || u.username || `User #${id}`
  }

  // ── Client-side filters: action chips + actor text ─────────────────────────
  const filtered = useMemo(() => {
    const q = actorQuery.trim().toLowerCase()
    return logs.filter((l) => {
      if (actionChips.length > 0) {
        const A = l.action.toUpperCase()
        const match = actionChips.some((kind) => A.startsWith(kind))
        if (!match) return false
      }
      if (q) {
        const u = userMap.get(l.actor_user_id)
        const hay = [
          u?.full_name ?? '',
          u?.username ?? '',
          u?.email ?? '',
          `user #${l.actor_user_id}`,
        ].join(' ').toLowerCase()
        if (!hay.includes(q)) return false
      }
      return true
    })
  }, [logs, actionChips, actorQuery, userMap])

  // ── Sort DESC then group by day, slicing to visibleCount ───────────────────
  const { groups, totalFiltered } = useMemo(() => {
    const sorted = [...filtered].sort(
      (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
    )
    const slice = sorted.slice(0, visibleCount)
    const map = new Map<string, { label: string; items: AuditLog[] }>()
    for (const log of slice) {
      const k = dayKey(log.created_at)
      if (!map.has(k)) {
        map.set(k, { label: dayLabel(log.created_at), items: [] })
      }
      map.get(k)!.items.push(log)
    }
    return {
      groups: Array.from(map.entries()).map(([key, v]) => ({ key, ...v })),
      totalFiltered: sorted.length,
    }
  }, [filtered, visibleCount])

  // ── Unique entity types for select ─────────────────────────────────────────
  const entityTypes = useMemo(() => {
    const s = new Set<string>()
    logs.forEach((l) => s.add(l.entity_type))
    return Array.from(s).sort()
  }, [logs])

  const hasFilters =
    actionChips.length > 0 || entityType !== '' || actorQuery !== '' ||
    startDate !== '' || endDate !== ''

  const clearFilters = () => {
    setActionChips([])
    setEntityType('')
    setActorQuery('')
    setStartDate('')
    setEndDate('')
  }

  const toggleChip = (kind: string) => {
    setActionChips((prev) =>
      prev.includes(kind) ? prev.filter((k) => k !== kind) : [...prev, kind]
    )
  }

  const toggleExpanded = (id: number) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <main className="pv2-main">
      {/* Breadcrumb */}
      <div className="crumb">
        <span>Platform</span>
        <span className="sep">/</span>
        <span className="now">Audit log</span>
      </div>

      {/* Page head */}
      <div className="page-head">
        <div>
          <h1>Audit log</h1>
          <div className="sub">
            Bitácora editorial de acciones cross-tenant · timeline inverso por día
          </div>
        </div>
        {hasFilters && (
          <div className="right">
            <button
              type="button"
              className="btn ghost"
              onClick={clearFilters}
              aria-label="Limpiar filtros"
            >
              <i className="fa-solid fa-xmark" />
              Limpiar filtros
            </button>
          </div>
        )}
      </div>

      {/* Filter bar */}
      <section
        className="card"
        aria-label="Filtros"
        style={{ padding: '16px 18px' }}
      >
        <div
          className="audit-filters"
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: 16,
            alignItems: 'flex-end',
          }}
        >
          {/* Action chips */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, minWidth: 0, flex: '1 1 420px' }}>
            <span style={filterLabelStyle}>Acción</span>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {ACTION_CHIPS.map((kind) => {
                const active = actionChips.includes(kind)
                const c = actionColor(kind)
                return (
                  <button
                    key={kind}
                    type="button"
                    aria-pressed={active}
                    onClick={() => toggleChip(kind)}
                    style={{
                      ...chipStyle,
                      background: active ? c.bg : 'var(--p-surface-2)',
                      color: active ? c.token : 'var(--p-muted)',
                      borderColor: active ? c.token : 'var(--p-border)',
                    }}
                  >
                    {kind}
                  </button>
                )
              })}
            </div>
          </div>

          {/* Entity type */}
          <div style={filterColStyle}>
            <span style={filterLabelStyle}>Entidad</span>
            <select
              value={entityType}
              onChange={(e) => setEntityType(e.target.value)}
              style={inputStyle}
              aria-label="Tipo de entidad"
            >
              <option value="">Todas</option>
              {entityTypes.map((et) => (
                <option key={et} value={et}>{et}</option>
              ))}
            </select>
          </div>

          {/* From / To */}
          <div style={filterColStyle}>
            <span style={filterLabelStyle}>Desde</span>
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              style={inputStyle}
              aria-label="Fecha inicial"
            />
          </div>
          <div style={filterColStyle}>
            <span style={filterLabelStyle}>Hasta</span>
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              style={inputStyle}
              aria-label="Fecha final"
            />
          </div>

          {/* Actor search */}
          <div style={{ ...filterColStyle, flex: '1 1 220px' }}>
            <span style={filterLabelStyle}>Actor</span>
            <input
              type="text"
              value={actorQuery}
              onChange={(e) => setActorQuery(e.target.value)}
              placeholder="Buscar por nombre, email o #id"
              style={inputStyle}
              aria-label="Buscar actor"
            />
          </div>
        </div>
      </section>

      {/* Timeline body */}
      {loading ? (
        <TimelineSkeleton />
      ) : totalFiltered === 0 ? (
        <EmptyState hasFilters={hasFilters} onClear={clearFilters} />
      ) : (
        <>
          {groups.map((g) => (
            <section key={g.key} aria-label={g.label} style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <div style={daySeparatorStyle}>
                <span style={daySeparatorLabelStyle}>{g.label}</span>
                <span style={daySeparatorLineStyle} />
                <span style={{ ...daySeparatorLabelStyle, color: 'var(--p-hint)' }}>
                  {g.items.length} {g.items.length === 1 ? 'evento' : 'eventos'}
                </span>
              </div>

              <div className="card" style={{ padding: 0 }}>
                {g.items.map((log, idx) => {
                  const c = actionColor(log.action)
                  const isOpen = expanded.has(log.id)
                  const payload = parsePayload(log.payload)
                  const hasPayload = payload !== null && payload !== ''
                  const formatted = hasPayload ? formatPayload(payload) : ''
                  const label = actorLabel(log.actor_user_id)
                  const avatarInitials = initials(label)

                  return (
                    <div
                      key={log.id}
                      role={hasPayload ? 'button' : undefined}
                      tabIndex={hasPayload ? 0 : -1}
                      aria-expanded={hasPayload ? isOpen : undefined}
                      onClick={hasPayload ? () => toggleExpanded(log.id) : undefined}
                      onKeyDown={
                        hasPayload
                          ? (e) => {
                              if (e.key === 'Enter' || e.key === ' ') {
                                e.preventDefault()
                                toggleExpanded(log.id)
                              }
                            }
                          : undefined
                      }
                      style={{
                        ...rowStyle,
                        borderBottom: idx === g.items.length - 1 ? 'none' : '1px solid var(--p-border-2)',
                        cursor: hasPayload ? 'pointer' : 'default',
                      }}
                    >
                      {/* Avatar */}
                      <div className="audit-avatar" style={avatarStyle} aria-hidden="true">
                        {avatarInitials}
                      </div>

                      {/* Main content */}
                      <div style={{ minWidth: 0, display: 'flex', flexDirection: 'column', gap: 4 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                          <span style={actorNameStyle}>{label}</span>
                          <span
                            style={{
                              ...actionChipStyle,
                              background: c.bg,
                              color: c.token,
                            }}
                          >
                            {log.action}
                          </span>
                        </div>
                        <div style={metaLineStyle}>
                          <span>{log.entity_type}</span>
                          {log.entity_id && (
                            <>
                              <span style={dotStyle} />
                              <span>#{log.entity_id}</span>
                            </>
                          )}
                          <span style={dotStyle} />
                          <span title={new Date(log.created_at).toLocaleString('es-MX')}>
                            {relativeTime(log.created_at)}
                          </span>
                        </div>

                        {hasPayload && (
                          <div style={{ marginTop: 6 }}>
                            <span style={disclosureStyle}>
                              <i
                                className={
                                  isOpen
                                    ? 'fa-solid fa-chevron-down'
                                    : 'fa-solid fa-chevron-right'
                                }
                                style={{ fontSize: 9, marginRight: 6 }}
                              />
                              payload
                            </span>
                            {isOpen && (
                              <pre style={payloadStyle} onClick={(e) => e.stopPropagation()}>
                                {formatted}
                              </pre>
                            )}
                          </div>
                        )}
                      </div>

                      {/* Clock */}
                      <div
                        className="audit-clock"
                        style={{
                          color: 'var(--p-muted)',
                          fontFamily: 'var(--font-mono)',
                          fontSize: 11,
                          whiteSpace: 'nowrap',
                          alignSelf: 'flex-start',
                        }}
                      >
                        {formatClock(log.created_at)}
                      </div>
                    </div>
                  )
                })}
              </div>
            </section>
          ))}

          {visibleCount < totalFiltered && (
            <div style={{ display: 'flex', justifyContent: 'center', padding: '8px 0 24px' }}>
              <button
                type="button"
                className="btn"
                onClick={() => setVisibleCount((c) => c + PAGE_SIZE)}
              >
                <i className="fa-solid fa-plus" />
                Cargar más · quedan {totalFiltered - visibleCount}
              </button>
            </div>
          )}
        </>
      )}

      {/* Inline responsive rules scoped to this page */}
      <style>{`
        @media (max-width: 900px) {
          .audit-filters { flex-direction: column; align-items: stretch !important; }
          .audit-filters > div { width: 100%; flex: 1 1 auto !important; }
          .audit-avatar { display: none !important; }
          .audit-clock { align-self: flex-end !important; }
        }
      `}</style>
    </main>
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

const chipStyle: React.CSSProperties = {
  fontFamily: 'var(--font-mono)',
  fontSize: 10,
  letterSpacing: '0.08em',
  textTransform: 'uppercase',
  padding: '4px 10px',
  borderRadius: 999,
  border: '1px solid var(--p-border)',
  background: 'var(--p-surface-2)',
  color: 'var(--p-muted)',
  cursor: 'pointer',
  userSelect: 'none',
  fontWeight: 600,
  lineHeight: 1.4,
}

const daySeparatorStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 12,
  padding: '4px 2px',
}

const daySeparatorLabelStyle: React.CSSProperties = {
  fontFamily: 'var(--font-mono)',
  fontSize: 11,
  letterSpacing: '0.12em',
  textTransform: 'uppercase',
  color: 'var(--p-muted)',
  fontWeight: 600,
  whiteSpace: 'nowrap',
}

const daySeparatorLineStyle: React.CSSProperties = {
  flex: 1,
  height: 1,
  background: 'var(--p-border-2)',
}

const rowStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: '32px 1fr auto',
  gap: 14,
  padding: '14px 18px',
  alignItems: 'flex-start',
}

const avatarStyle: React.CSSProperties = {
  width: 32,
  height: 32,
  borderRadius: 10,
  background: 'var(--p-surface-2)',
  border: '1px solid var(--p-border)',
  display: 'grid',
  placeItems: 'center',
  color: 'var(--p-text)',
  fontSize: 11,
  fontWeight: 600,
  letterSpacing: '0.02em',
  fontFamily: 'var(--font-mono)',
}

const actorNameStyle: React.CSSProperties = {
  color: 'var(--p-text)',
  fontSize: 13,
  fontWeight: 500,
}

const actionChipStyle: React.CSSProperties = {
  fontFamily: 'var(--font-mono)',
  fontSize: 10,
  letterSpacing: '0.08em',
  textTransform: 'uppercase',
  padding: '3px 10px',
  borderRadius: 999,
  fontWeight: 600,
  whiteSpace: 'nowrap',
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
  cursor: 'text',
}

// ── Sub-components ───────────────────────────────────────────────────────────

function EmptyState({ hasFilters, onClear }: { hasFilters: boolean; onClear: () => void }) {
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
        <i className="fa-solid fa-ghost" />
      </div>
      <div>
        <div style={{ color: 'var(--p-text)', fontSize: 15, fontWeight: 600 }}>
          Sin eventos en este rango
        </div>
        <div style={{ color: 'var(--p-muted)', fontSize: 12, marginTop: 4 }}>
          Ajusta los filtros o amplía el rango de fechas para ver más actividad.
        </div>
      </div>
      {hasFilters && (
        <button type="button" className="btn" onClick={onClear}>
          <i className="fa-solid fa-expand" />
          Ampliar rango
        </button>
      )}
    </div>
  )
}

function TimelineSkeleton() {
  return (
    <>
      {Array.from({ length: 2 }).map((_, gi) => (
        <section key={gi} style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div style={daySeparatorStyle}>
            <span className="sk" style={{ display: 'inline-block', width: 120, height: 10, borderRadius: 6 }} />
            <span style={daySeparatorLineStyle} />
          </div>
          <div className="card" style={{ padding: 0 }}>
            {Array.from({ length: 4 }).map((_, i) => (
              <div
                key={i}
                style={{
                  ...rowStyle,
                  borderBottom: i === 3 ? 'none' : '1px solid var(--p-border-2)',
                }}
              >
                <span className="sk" style={{ width: 32, height: 32, borderRadius: 10 }} />
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8, minWidth: 0 }}>
                  <span className="sk" style={{ width: '60%', height: 12, borderRadius: 6 }} />
                  <span className="sk" style={{ width: '40%', height: 10, borderRadius: 6 }} />
                </div>
                <span className="sk" style={{ width: 40, height: 10, borderRadius: 6 }} />
              </div>
            ))}
          </div>
        </section>
      ))}
    </>
  )
}
