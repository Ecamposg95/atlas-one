import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  incidentsApi,
  platformApi,
  PlatformIncident,
  IncidentScopeType,
  IncidentStatusFilter,
  IncidentCreatePayload,
  IndustryPreset,
  PlatformOrg,
  NOMBRE_PLAN,
  nombrePlan,
} from '../../api/platform'
import { KPICardV2 } from '../../components/platform/v2/KPICardV2'
import { SideDrawer } from '../../components/platform/SideDrawer'
import { ConfirmModal } from '../../components/platform/ConfirmModal'
import { toast } from '../../store/toastStore'
import '../../styles/platform-v2.css'

// ── Constants ────────────────────────────────────────────────────────────────

// Claves del catalogo de planes (fuente unica: NOMBRE_PLAN). Se guarda la
// clave; en pantalla se muestra el nombre comercial con `nombrePlan`.
const PLANS: string[] = Object.keys(NOMBRE_PLAN)
type Plan = string

const STATUS_FILTERS: { key: IncidentStatusFilter; label: string }[] = [
  { key: 'active',   label: 'Activos' },
  { key: 'resolved', label: 'Resueltos' },
  { key: 'all',      label: 'Todos' },
]

// ── Helpers ──────────────────────────────────────────────────────────────────

function relativeTime(iso: string | null): string {
  if (!iso) return ''
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

function parseOrgIds(text: string): number[] {
  return text
    .split(/[,\s]+/)
    .map((s) => s.trim())
    .filter(Boolean)
    .map((s) => Number(s))
    .filter((n) => Number.isFinite(n) && n > 0)
}

interface ScopeChipMeta {
  label: string
  token: string
  bg: string
  border: string
}

function scopeMeta(scope: IncidentScopeType, value: string | null, affected: number): ScopeChipMeta {
  switch (scope) {
    case 'industry':
      return {
        label: `INDUSTRY: ${value || '—'}`,
        token: 'var(--p-warning)',
        bg: 'rgba(245,158,11,0.12)',
        border: 'rgba(245,158,11,0.35)',
      }
    case 'plan':
      return {
        label: `PLAN: ${value || '—'}`,
        token: 'var(--p-accent)',
        bg: 'var(--p-accent-soft)',
        border: 'var(--p-accent-line)',
      }
    case 'org_ids':
      return {
        label: `ORGS: ${affected}`,
        token: 'var(--p-muted)',
        bg: 'var(--p-surface-2)',
        border: 'var(--p-border)',
      }
    case 'all':
      return {
        label: 'ALL',
        token: 'var(--p-danger)',
        bg: 'rgba(239,68,68,0.12)',
        border: 'rgba(239,68,68,0.35)',
      }
  }
}

// ── Form state ───────────────────────────────────────────────────────────────

interface FormState {
  title: string
  reason: string
  scope_type: IncidentScopeType
  industry: string
  plan: Plan
  org_ids_text: string
  banner_html: string
}

const EMPTY_FORM: FormState = {
  title: '',
  reason: '',
  scope_type: 'industry',
  industry: '',
  plan: 'FREE',
  org_ids_text: '',
  banner_html: '',
}

// ── Page ─────────────────────────────────────────────────────────────────────

export function PlatformIncidents() {
  const [items, setItems] = useState<PlatformIncident[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<IncidentStatusFilter>('active')

  const [presets, setPresets] = useState<IndustryPreset[]>([])
  const [orgs, setOrgs] = useState<PlatformOrg[]>([])

  const [drawerOpen, setDrawerOpen] = useState(false)
  const [form, setForm] = useState<FormState>(EMPTY_FORM)

  const [confirmOpen, setConfirmOpen] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  const [toResolve, setToResolve] = useState<PlatformIncident | null>(null)
  const [resolving, setResolving] = useState(false)

  const [expanded, setExpanded] = useState<Set<number>>(new Set())

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [rows, ps, os] = await Promise.all([
        incidentsApi.list('all'),
        platformApi.getPresets().catch(() => [] as IndustryPreset[]),
        platformApi.getOrgs().catch(() => [] as PlatformOrg[]),
      ])
      setItems(Array.isArray(rows) ? rows : [])
      setPresets(Array.isArray(ps) ? ps : [])
      setOrgs(Array.isArray(os) ? os : [])
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } }
      toast.error(e?.response?.data?.detail || 'No se pudieron cargar los incidentes')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const industryOptions = useMemo(
    () => presets.map((p) => p.industry_type).sort(),
    [presets],
  )

  const activeOrgs = useMemo(
    () => orgs.filter((o) => o.is_active),
    [orgs],
  )

  const filtered = useMemo(() => {
    if (filter === 'all') return items
    if (filter === 'active') return items.filter((i) => i.is_active)
    return items.filter((i) => !i.is_active)
  }, [items, filter])

  // ── KPIs ─────────────────────────────────────────────────────────────────

  const kpiActive = useMemo(
    () => items.filter((i) => i.is_active).length,
    [items],
  )

  const kpiOrgsAffected = useMemo(
    () => items.filter((i) => i.is_active).reduce((acc, it) => acc + (it.affected_count || 0), 0),
    [items],
  )

  const kpiResolved7d = useMemo(() => {
    const cutoff = Date.now() - 7 * 24 * 60 * 60 * 1000
    return items.filter((i) => i.resolved_at && new Date(i.resolved_at).getTime() >= cutoff).length
  }, [items])

  // ── Preview count for form ───────────────────────────────────────────────

  const previewCount = useMemo(() => {
    if (form.scope_type === 'all') return activeOrgs.length
    if (form.scope_type === 'industry') {
      if (!form.industry) return 0
      return activeOrgs.filter((o) => (o.industry_type || '') === form.industry).length
    }
    if (form.scope_type === 'plan') {
      return activeOrgs.filter((o) => ((o as unknown as { plan?: string }).plan || 'FREE') === form.plan).length
    }
    // org_ids
    const ids = new Set(parseOrgIds(form.org_ids_text))
    if (ids.size === 0) return 0
    return activeOrgs.filter((o) => ids.has(o.id)).length
  }, [form, activeOrgs])

  // ── Handlers ─────────────────────────────────────────────────────────────

  const openCreate = () => {
    setForm(EMPTY_FORM)
    setDrawerOpen(true)
  }

  const closeDrawer = () => {
    setDrawerOpen(false)
  }

  const validateForm = (): string | null => {
    if (!form.title.trim()) return 'El título es requerido'
    const reason = form.reason.trim()
    if (reason.length < 10) return 'La razón debe tener al menos 10 caracteres'
    if (form.scope_type === 'industry' && !form.industry) return 'Selecciona una industria'
    if (form.scope_type === 'org_ids' && parseOrgIds(form.org_ids_text).length === 0) {
      return 'Ingresa al menos un ID de organización'
    }
    return null
  }

  const handleOpenConfirm = () => {
    const err = validateForm()
    if (err) {
      toast.error(err)
      return
    }
    setConfirmOpen(true)
  }

  const handleCreate = async () => {
    setSubmitting(true)
    try {
      let scope_value: string | null = null
      if (form.scope_type === 'industry') scope_value = form.industry
      else if (form.scope_type === 'plan') scope_value = form.plan
      else if (form.scope_type === 'org_ids') scope_value = parseOrgIds(form.org_ids_text).join(',')

      const payload: IncidentCreatePayload = {
        title: form.title.trim(),
        reason: form.reason.trim() || null,
        scope_type: form.scope_type,
        scope_value,
        banner_html: form.banner_html.trim() || null,
      }
      const force = form.scope_type === 'all' && previewCount > 100
      const row = await incidentsApi.create(payload, force)
      toast.success(`Incidente iniciado · ${row.affected_count} orgs suspendidas`)
      setConfirmOpen(false)
      setDrawerOpen(false)
      setForm(EMPTY_FORM)
      load()
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } }
      toast.error(e?.response?.data?.detail || 'No se pudo iniciar el incidente')
    } finally {
      setSubmitting(false)
    }
  }

  const handleResolve = async () => {
    if (!toResolve) return
    setResolving(true)
    try {
      const res = await incidentsApi.resolve(toResolve.id)
      toast.success(`Incidente resuelto · ${res.restored} restauradas · ${res.skipped} omitidas`)
      setToResolve(null)
      load()
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } }
      toast.error(e?.response?.data?.detail || 'No se pudo resolver el incidente')
    } finally {
      setResolving(false)
    }
  }

  const toggleExpanded = (id: number) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  // ── Render ───────────────────────────────────────────────────────────────

  return (
    <main className="pv2-main">
      {/* Breadcrumb */}
      <div className="crumb">
        <span>Platform</span>
        <span className="sep">/</span>
        <span className="now">Incidents</span>
      </div>

      {/* Page head */}
      <div className="page-head">
        <div>
          <h1>Incident mode</h1>
          <div className="sub">Kill-switch temporal por industria / plan / orgs</div>
        </div>
        <div className="right" style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div role="group" aria-label="Filtro de estado" style={pillGroupStyle}>
            {STATUS_FILTERS.map((chip) => {
              const selected = filter === chip.key
              return (
                <button
                  key={chip.key}
                  type="button"
                  aria-pressed={selected}
                  onClick={() => setFilter(chip.key)}
                  style={{
                    ...pillStyle,
                    background: selected ? 'var(--p-surface-2)' : 'transparent',
                    color: selected ? 'var(--p-text)' : 'var(--p-muted)',
                    borderColor: selected ? 'var(--p-border)' : 'transparent',
                  }}
                >
                  {chip.label}
                </button>
              )
            })}
          </div>
          <button
            type="button"
            onClick={openCreate}
            style={dangerBtnStyle}
            aria-label="Iniciar incidente"
          >
            <i className="fa-solid fa-fire" />
            Iniciar incidente
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
        <KPICardV2 label="Incidentes activos" value={kpiActive} icon="fa-fire" />
        <KPICardV2 label="Orgs afectadas" value={kpiOrgsAffected} icon="fa-building-shield" />
        <KPICardV2 label="Resueltos 7d" value={kpiResolved7d} icon="fa-circle-check" />
      </div>

      {/* Feed */}
      {loading ? (
        <IncidentsSkeleton />
      ) : filtered.length === 0 ? (
        <EmptyState onCreate={openCreate} filter={filter} />
      ) : (
        <section
          aria-label="Lista de incidentes"
          style={{ display: 'flex', flexDirection: 'column', gap: 12 }}
        >
          {filtered.map((inc) => (
            <IncidentCard
              key={inc.id}
              incident={inc}
              expanded={expanded.has(inc.id)}
              onToggle={() => toggleExpanded(inc.id)}
              onResolve={() => setToResolve(inc)}
            />
          ))}
        </section>
      )}

      {/* Start-incident drawer */}
      <SideDrawer
        open={drawerOpen}
        title="Iniciar incidente"
        subtitle="Suspende un conjunto de orgs — reversible en un click"
        onClose={closeDrawer}
        onSave={handleOpenConfirm}
        saveLabel="Continuar"
        saving={submitting}
        width={540}
      >
        <IncidentForm
          form={form}
          setForm={setForm}
          industryOptions={industryOptions}
          previewCount={previewCount}
          activeTotal={activeOrgs.length}
        />
      </SideDrawer>

      {/* Confirm start */}
      <ConfirmModal
        open={confirmOpen}
        title="Iniciar incidente"
        message={`Esto suspenderá ${previewCount} organización${previewCount === 1 ? '' : 'es'} inmediatamente. Podrás restaurarlas al resolver el incidente.`}
        resourceName="INICIAR"
        destructive
        onClose={() => setConfirmOpen(false)}
        onConfirm={handleCreate}
        busy={submitting}
      />

      {/* Confirm resolve */}
      <ConfirmModal
        open={!!toResolve}
        title="Resolver incidente"
        message={`Esto restaurará ${toResolve?.affected_count ?? 0} orgs a su estado previo. Las que ya fueron reactivadas manualmente serán omitidas.`}
        resourceName={toResolve ? (toResolve.title.length > 30 ? 'RESOLVER' : toResolve.title) : 'RESOLVER'}
        onClose={() => setToResolve(null)}
        onConfirm={handleResolve}
        busy={resolving}
      />
    </main>
  )
}

// ── Incident card ────────────────────────────────────────────────────────────

interface IncidentCardProps {
  incident: PlatformIncident
  expanded: boolean
  onToggle: () => void
  onResolve: () => void
}

function IncidentCard({ incident, expanded, onToggle, onResolve }: IncidentCardProps) {
  const active = incident.is_active
  const sMeta = scopeMeta(incident.scope_type, incident.scope_value, incident.affected_count)
  const color = active ? 'var(--p-danger)' : 'var(--p-muted)'
  const dotBg = active ? 'rgba(239,68,68,0.25)' : 'rgba(107,107,120,0.22)'

  const snapshotPreview = useMemo(() => {
    if (!incident.affected_snapshot) return []
    return incident.affected_snapshot.slice(0, 20)
  }, [incident.affected_snapshot])

  return (
    <article
      className="card"
      style={{
        padding: 0,
        opacity: active ? 1 : 0.7,
        borderLeft: `3px solid ${color}`,
      }}
    >
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'auto 1fr auto',
          gap: 16,
          padding: '16px 20px',
          alignItems: 'flex-start',
        }}
      >
        {/* Icon / dot */}
        <div
          aria-hidden="true"
          style={{
            width: 36, height: 36, borderRadius: 10,
            display: 'grid', placeItems: 'center',
            background: dotBg,
            color,
            marginTop: 2,
            position: 'relative',
          }}
        >
          <i className={active ? 'fa-solid fa-fire' : 'fa-solid fa-circle-check'} />
          {active && (
            <span
              aria-hidden="true"
              style={{
                position: 'absolute', top: -2, right: -2,
                width: 10, height: 10, borderRadius: '50%',
                background: 'var(--p-danger)',
                boxShadow: '0 0 0 3px rgba(239,68,68,0.22)',
                animation: 'pv2-pulse 1.6s ease-in-out infinite',
              }}
            />
          )}
        </div>

        {/* Main */}
        <div style={{ minWidth: 0, display: 'flex', flexDirection: 'column', gap: 6 }}>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'center' }}>
            <h3
              style={{
                margin: 0,
                fontFamily: 'var(--font-display)',
                fontSize: 15,
                fontWeight: 600,
                color: 'var(--p-text)',
                letterSpacing: '-0.01em',
              }}
            >
              {incident.title}
            </h3>
            <span
              style={{
                ...chipStyle,
                background: sMeta.bg,
                color: sMeta.token,
                borderColor: sMeta.border,
              }}
            >
              {sMeta.label}
            </span>
            <span
              style={{
                ...chipStyle,
                background: 'var(--p-surface-2)',
                color: 'var(--p-muted)',
                borderColor: 'var(--p-border)',
              }}
            >
              {incident.affected_count} orgs
            </span>
          </div>

          {incident.reason && (
            <div style={{ color: 'var(--p-muted)', fontSize: 13, lineHeight: 1.5 }}>
              {incident.reason}
            </div>
          )}

          <div style={metaLineStyle}>
            <span title={incident.started_at ? new Date(incident.started_at).toLocaleString('es-MX') : ''}>
              Iniciado {relativeTime(incident.started_at)}
            </span>
            {!active && incident.resolved_at && (
              <>
                <span style={dotSeparatorStyle} />
                <span title={new Date(incident.resolved_at).toLocaleString('es-MX')}>
                  Resuelto {relativeTime(incident.resolved_at)}
                </span>
              </>
            )}
          </div>

          {(snapshotPreview.length > 0 || incident.affected_snapshot) && (
            <div style={{ marginTop: 6 }}>
              <button
                type="button"
                onClick={onToggle}
                style={disclosureStyle}
                aria-expanded={expanded}
              >
                <i
                  className={expanded ? 'fa-solid fa-chevron-down' : 'fa-solid fa-chevron-right'}
                  style={{ fontSize: 9, marginRight: 6 }}
                />
                {active ? 'ver snapshot' : 'ver snapshot'}
              </button>
              {expanded && (
                <div style={snapshotBoxStyle}>
                  {snapshotPreview.length === 0 ? (
                    <span style={{ color: 'var(--p-muted)', fontSize: 12 }}>
                      Sin orgs afectadas (el scope no encontró orgs activas).
                    </span>
                  ) : (
                    <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 4 }}>
                      {snapshotPreview.map((s) => (
                        <li
                          key={s.id}
                          style={{
                            display: 'flex', gap: 8, alignItems: 'center',
                            color: 'var(--p-text)', fontSize: 12,
                          }}
                        >
                          <span style={{ color: 'var(--p-muted)', fontFamily: 'var(--font-mono)', fontSize: 11 }}>
                            #{s.id}
                          </span>
                          <span style={{ fontWeight: 500 }}>{s.name}</span>
                          <span style={{ marginLeft: 'auto', color: 'var(--p-hint)', fontSize: 11, fontFamily: 'var(--font-mono)' }}>
                            era {s.was_status}
                          </span>
                        </li>
                      ))}
                      {(incident.affected_snapshot?.length ?? 0) > snapshotPreview.length && (
                        <li style={{ color: 'var(--p-hint)', fontSize: 11, fontFamily: 'var(--font-mono)', marginTop: 4 }}>
                          +{(incident.affected_snapshot?.length ?? 0) - snapshotPreview.length} más…
                        </li>
                      )}
                    </ul>
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Actions */}
        <div style={{ display: 'flex', alignItems: 'flex-start' }}>
          {active && (
            <button
              type="button"
              onClick={onResolve}
              style={resolveBtnStyle}
              aria-label={`Resolver ${incident.title}`}
            >
              <i className="fa-solid fa-circle-check" />
              Resolver
            </button>
          )}
        </div>
      </div>

      <style>{`
        @keyframes pv2-pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.35; }
        }
      `}</style>
    </article>
  )
}

// ── Form ─────────────────────────────────────────────────────────────────────

interface FormProps {
  form: FormState
  setForm: React.Dispatch<React.SetStateAction<FormState>>
  industryOptions: string[]
  previewCount: number
  activeTotal: number
}

function IncidentForm({ form, setForm, industryOptions, previewCount, activeTotal }: FormProps) {
  const parsedIds = parseOrgIds(form.org_ids_text)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div>
        <label style={labelStyle}>Título</label>
        <input
          type="text"
          value={form.title}
          onChange={(e) => setForm((p) => ({ ...p, title: e.target.value }))}
          style={inputStyle}
          placeholder="Ej. Fallo de integración SAT"
          maxLength={200}
        />
      </div>

      <div>
        <label style={labelStyle}>Razón (mínimo 10 chars)</label>
        <textarea
          value={form.reason}
          onChange={(e) => setForm((p) => ({ ...p, reason: e.target.value }))}
          style={{ ...inputStyle, minHeight: 70, resize: 'vertical', fontFamily: 'var(--font-sans)' }}
          placeholder="Describe brevemente qué está ocurriendo…"
        />
      </div>

      <div>
        <label style={labelStyle}>Scope</label>
        <div role="radiogroup" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
          {[
            { value: 'industry' as const, label: 'Por industria', icon: 'fa-layer-group' },
            { value: 'plan' as const,     label: 'Por plan',      icon: 'fa-crown' },
            { value: 'org_ids' as const,  label: 'Específicas',   icon: 'fa-list-ol' },
            { value: 'all' as const,      label: 'Todas',         icon: 'fa-globe' },
          ].map((opt) => {
            const selected = form.scope_type === opt.value
            const isAll = opt.value === 'all'
            return (
              <button
                key={opt.value}
                type="button"
                role="radio"
                aria-checked={selected}
                onClick={() => setForm((p) => ({ ...p, scope_type: opt.value }))}
                style={{
                  ...scopeOptionStyle,
                  borderColor: selected
                    ? (isAll ? 'var(--p-danger)' : 'var(--p-accent)')
                    : 'var(--p-border)',
                  background: selected
                    ? (isAll ? 'rgba(239,68,68,0.08)' : 'var(--p-accent-soft)')
                    : 'var(--p-surface-2)',
                  color: selected
                    ? (isAll ? 'var(--p-danger)' : 'var(--p-accent)')
                    : 'var(--p-text)',
                }}
              >
                <i className={'fa-solid ' + opt.icon} />
                <span>{opt.label}</span>
              </button>
            )
          })}
        </div>
      </div>

      {form.scope_type === 'industry' && (
        <div>
          <label style={labelStyle}>Industria</label>
          <select
            value={form.industry}
            onChange={(e) => setForm((p) => ({ ...p, industry: e.target.value }))}
            style={inputStyle}
          >
            <option value="">— selecciona —</option>
            {industryOptions.map((i) => (
              <option key={i} value={i}>{i}</option>
            ))}
          </select>
        </div>
      )}

      {form.scope_type === 'plan' && (
        <div>
          <label style={labelStyle}>Plan</label>
          <select
            value={form.plan}
            onChange={(e) => setForm((p) => ({ ...p, plan: e.target.value as Plan }))}
            style={inputStyle}
          >
            {PLANS.map((p) => (
              <option key={p} value={p}>{nombrePlan(p)}</option>
            ))}
          </select>
        </div>
      )}

      {form.scope_type === 'org_ids' && (
        <div>
          <label style={labelStyle}>IDs de organización (separadas por coma)</label>
          <input
            type="text"
            value={form.org_ids_text}
            onChange={(e) => setForm((p) => ({ ...p, org_ids_text: e.target.value }))}
            style={inputStyle}
            placeholder="42, 55, 88"
          />
          <div style={{ color: 'var(--p-hint)', fontSize: 11, marginTop: 6, fontFamily: 'var(--font-mono)' }}>
            {parsedIds.length} id{parsedIds.length === 1 ? '' : 's'} válidos
          </div>
        </div>
      )}

      {form.scope_type === 'all' && (
        <div style={warningBoxStyle}>
          <i className="fa-solid fa-triangle-exclamation" style={{ color: 'var(--p-danger)' }} />
          <div>
            <div style={{ color: 'var(--p-danger)', fontWeight: 600, fontSize: 13 }}>
              Esto afectará TODAS las orgs activas
            </div>
            <div style={{ color: 'var(--p-muted)', fontSize: 12, marginTop: 2 }}>
              {activeTotal} orgs serán suspendidas. Si son más de 100, requerirá confirmación adicional.
            </div>
          </div>
        </div>
      )}

      <div>
        <label style={labelStyle}>Banner HTML (opcional)</label>
        <textarea
          value={form.banner_html}
          onChange={(e) => setForm((p) => ({ ...p, banner_html: e.target.value }))}
          style={{ ...inputStyle, minHeight: 60, resize: 'vertical', fontFamily: 'var(--font-mono)', fontSize: 12 }}
          placeholder="<b>Servicio temporalmente suspendido</b> — estamos trabajando en una solución."
        />
        <div style={{ color: 'var(--p-hint)', fontSize: 11, marginTop: 6 }}>
          Reservado para uso futuro (banner en la UI del tenant).
        </div>
      </div>

      <div style={previewBoxStyle}>
        <span style={{ color: 'var(--p-muted)', fontSize: 12 }}>Esto suspenderá</span>
        <span style={{ color: 'var(--p-danger)', fontFamily: 'var(--font-display)', fontSize: 28, fontWeight: 700, letterSpacing: '-0.02em' }}>
          {previewCount}
        </span>
        <span style={{ color: 'var(--p-muted)', fontSize: 12 }}>
          org{previewCount === 1 ? '' : 's'} activa{previewCount === 1 ? '' : 's'}
        </span>
      </div>
    </div>
  )
}

// ── Empty + skeleton ─────────────────────────────────────────────────────────

function EmptyState({ onCreate, filter }: { onCreate: () => void; filter: IncidentStatusFilter }) {
  const msg = filter === 'active'
    ? 'Sin incidentes activos. Todo tranquilo.'
    : filter === 'resolved'
      ? 'Aún no hay incidentes resueltos.'
      : 'Sin incidentes. Todo tranquilo.'
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
        <i className="fa-solid fa-shield-halved" />
      </div>
      <div>
        <div style={{ color: 'var(--p-text)', fontSize: 15, fontWeight: 600 }}>
          {msg}
        </div>
        <div style={{ color: 'var(--p-muted)', fontSize: 12, marginTop: 4 }}>
          Un incidente suspende temporalmente un grupo de orgs. Es reversible en un click.
        </div>
      </div>
      {filter !== 'resolved' && (
        <button type="button" onClick={onCreate} style={dangerBtnStyle}>
          <i className="fa-solid fa-fire" />
          Iniciar incidente
        </button>
      )}
    </div>
  )
}

function IncidentsSkeleton() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {Array.from({ length: 3 }).map((_, i) => (
        <div key={i} className="card" style={{ padding: 18 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr auto', gap: 14 }}>
            <span className="sk" style={{ width: 36, height: 36, borderRadius: 10 }} />
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, minWidth: 0 }}>
              <span className="sk" style={{ width: '40%', height: 14, borderRadius: 6 }} />
              <span className="sk" style={{ width: '70%', height: 12, borderRadius: 6 }} />
              <span className="sk" style={{ width: '25%', height: 10, borderRadius: 6 }} />
            </div>
            <span className="sk" style={{ width: 88, height: 30, borderRadius: 8 }} />
          </div>
        </div>
      ))}
    </div>
  )
}

// ── Styles ───────────────────────────────────────────────────────────────────

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

const dangerBtnStyle: React.CSSProperties = {
  background: 'var(--p-danger)',
  color: '#fff',
  border: '1px solid var(--p-danger)',
  padding: '8px 16px',
  borderRadius: 8,
  fontSize: 13,
  fontWeight: 600,
  fontFamily: 'var(--font-sans)',
  display: 'inline-flex',
  alignItems: 'center',
  gap: 8,
  cursor: 'pointer',
  boxShadow: '0 2px 8px rgba(239,68,68,0.25)',
}

const resolveBtnStyle: React.CSSProperties = {
  background: 'var(--p-surface-2)',
  color: 'var(--p-text)',
  border: '1px solid var(--p-border)',
  padding: '6px 12px',
  borderRadius: 8,
  fontSize: 12,
  fontWeight: 600,
  fontFamily: 'var(--font-sans)',
  display: 'inline-flex',
  alignItems: 'center',
  gap: 6,
  cursor: 'pointer',
  height: 30,
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

const metaLineStyle: React.CSSProperties = {
  color: 'var(--p-muted)',
  fontFamily: 'var(--font-mono)',
  fontSize: 11,
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  flexWrap: 'wrap',
  marginTop: 2,
}

const dotSeparatorStyle: React.CSSProperties = {
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

const snapshotBoxStyle: React.CSSProperties = {
  marginTop: 10,
  padding: 12,
  background: 'var(--p-sidebar)',
  border: '1px solid var(--p-border)',
  borderRadius: 10,
  maxHeight: 260,
  overflow: 'auto',
}

const inputStyle: React.CSSProperties = {
  width: '100%',
  background: 'var(--p-surface-2)',
  color: 'var(--p-text)',
  border: '1px solid var(--p-border)',
  borderRadius: 8,
  padding: '8px 10px',
  fontSize: 13,
  fontFamily: 'var(--font-sans)',
  outline: 'none',
  boxSizing: 'border-box',
}

const labelStyle: React.CSSProperties = {
  display: 'block',
  fontSize: 11,
  textTransform: 'uppercase',
  letterSpacing: '0.08em',
  color: 'var(--p-muted)',
  fontWeight: 600,
  marginBottom: 6,
}

const scopeOptionStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  padding: '10px 12px',
  borderRadius: 10,
  border: '1px solid var(--p-border)',
  background: 'var(--p-surface-2)',
  color: 'var(--p-text)',
  fontSize: 13,
  fontFamily: 'var(--font-sans)',
  fontWeight: 500,
  cursor: 'pointer',
  transition: 'background 0.15s ease, border-color 0.15s ease, color 0.15s ease',
}

const warningBoxStyle: React.CSSProperties = {
  display: 'flex',
  gap: 12,
  padding: 14,
  borderRadius: 10,
  background: 'rgba(239,68,68,0.06)',
  border: '1px solid rgba(239,68,68,0.25)',
  alignItems: 'flex-start',
}

const previewBoxStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
  gap: 4,
  padding: 18,
  borderRadius: 12,
  background: 'var(--p-surface-2)',
  border: '1px dashed var(--p-border)',
}
