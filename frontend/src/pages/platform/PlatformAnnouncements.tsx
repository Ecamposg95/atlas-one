import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  announcementsApi,
  platformApi,
  PlatformAnnouncement,
  AnnouncementSeverity,
  AnnouncementStatus,
  AnnouncementCreatePayload,
  IndustryPreset,
  NOMBRE_PLAN,
  nombrePlan,
} from '../../api/platform'
import { toast } from '../../store/toastStore'
import { KPICardV2 } from '../../components/platform/v2/KPICardV2'
import { SideDrawer } from '../../components/platform/SideDrawer'
import { ConfirmModal } from '../../components/platform/ConfirmModal'

import '../../styles/platform-v2.css'

// ── Constants ────────────────────────────────────────────────────────────────

// Claves del catalogo de planes (fuente unica: NOMBRE_PLAN). Se guarda la
// clave; en pantalla se muestra el nombre comercial con `nombrePlan`.
const PLANS: string[] = Object.keys(NOMBRE_PLAN)
type Plan = string

const SEVERITIES: AnnouncementSeverity[] = ['info', 'warning', 'critical', 'success']

const SEVERITY_META: Record<AnnouncementSeverity, { label: string; token: string; bg: string; icon: string }> = {
  info:     { label: 'Info',     token: 'var(--p-accent)',  bg: 'var(--p-accent-soft)',             icon: 'fa-circle-info' },
  warning:  { label: 'Warning',  token: 'var(--p-warning)', bg: 'rgba(245,158,11,0.12)',            icon: 'fa-triangle-exclamation' },
  critical: { label: 'Critical', token: 'var(--p-danger)',  bg: 'rgba(239,68,68,0.14)',             icon: 'fa-circle-exclamation' },
  success:  { label: 'Success',  token: 'var(--p-success)', bg: 'rgba(34,197,94,0.12)',             icon: 'fa-circle-check' },
}

const STATUS_FILTERS: { key: 'all' | AnnouncementStatus; label: string }[] = [
  { key: 'all',       label: 'Todos' },
  { key: 'published', label: 'Publicados' },
  { key: 'draft',     label: 'Drafts' },
  { key: 'expired',   label: 'Expirados' },
]

// ── Markdown renderer (MVP — 20 lines, XSS-safe via pre-escape) ──────────────

function escapeHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

function renderMarkdown(src: string): string {
  const esc = escapeHtml(src)
  // Split into paragraph blocks first.
  const blocks = esc.split(/\n{2,}/)
  const rendered = blocks.map((block) => {
    const lines = block.split('\n')
    // Bullet list block
    if (lines.every((l) => /^\s*-\s+/.test(l))) {
      const items = lines.map((l) => '<li>' + l.replace(/^\s*-\s+/, '') + '</li>').join('')
      return '<ul>' + items + '</ul>'
    }
    // Heading
    const h = block.match(/^(#{1,3})\s+(.*)$/)
    if (h) {
      const level = h[1].length
      return '<h' + level + '>' + h[2] + '</h' + level + '>'
    }
    // Paragraph with inline formatting
    return '<p>' + block.replace(/\n/g, '<br/>') + '</p>'
  }).join('')
  // Inline replacements (applied after block shaping).
  return rendered
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\*([^*]+)\*/g, '<em>$1</em>')
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_m, text, url) => {
      // Solo esquemas seguros: un [x](javascript:...) ejecutaría XSS al
      // inyectarse en href dentro de dangerouslySetInnerHTML.
      const clean = String(url).trim()
      if (!/^(https?:\/\/|mailto:)/i.test(clean)) return text
      return '<a href="' + clean.replace(/"/g, '&quot;') + '" target="_blank" rel="noopener noreferrer">' + text + '</a>'
    })
}

// ── Form state ───────────────────────────────────────────────────────────────

interface FormState {
  title: string
  body_md: string
  severity: AnnouncementSeverity
  industries: string[]
  plans: Plan[]
  org_ids_text: string
  expires_at: string // ISO datetime-local string "YYYY-MM-DDTHH:mm"
}

const EMPTY_FORM: FormState = {
  title: '',
  body_md: '',
  severity: 'info',
  industries: [],
  plans: [],
  org_ids_text: '',
  expires_at: '',
}

function isoToLocalInput(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (!Number.isFinite(d.getTime())) return ''
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function localInputToIso(s: string): string | null {
  if (!s) return null
  const d = new Date(s)
  if (!Number.isFinite(d.getTime())) return null
  return d.toISOString()
}

function formFromAnnouncement(a: PlatformAnnouncement): FormState {
  const ids = a.targets?.org_ids || []
  return {
    title: a.title,
    body_md: a.body_md,
    severity: a.severity,
    industries: a.targets?.industries ?? [],
    plans: (a.targets?.plans ?? []).filter((p) => PLANS.includes(p)),
    org_ids_text: ids.join(', '),
    expires_at: isoToLocalInput(a.expires_at),
  }
}

function parseOrgIds(text: string): number[] {
  return text
    .split(/[,\s]+/)
    .map((s) => s.trim())
    .filter(Boolean)
    .map((s) => Number(s))
    .filter((n) => Number.isFinite(n) && n > 0)
}

// ── Styles ───────────────────────────────────────────────────────────────────

const inputStyle: React.CSSProperties = {
  width: '100%',
  background: 'var(--p-surface-2)',
  color: 'var(--p-text)',
  border: '1px solid var(--p-border)',
  borderRadius: 6,
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

const fieldStyle: React.CSSProperties = { marginBottom: 14 }

// ── Components ───────────────────────────────────────────────────────────────

function SeverityChip({ severity }: { severity: AnnouncementSeverity }) {
  const meta = SEVERITY_META[severity]
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        padding: '2px 8px',
        borderRadius: 999,
        background: meta.bg,
        color: meta.token,
        fontSize: 11,
        fontWeight: 600,
        fontFamily: 'var(--font-mono)',
        textTransform: 'uppercase',
        letterSpacing: '0.04em',
        border: '1px solid ' + meta.token + '33',
      }}
    >
      <i className={'fa-solid ' + meta.icon} style={{ fontSize: 10 }} />
      {meta.label}
    </span>
  )
}

function StatusChip({ status }: { status: AnnouncementStatus }) {
  const map: Record<AnnouncementStatus, { label: string; color: string; bg: string }> = {
    published: { label: 'Publicado', color: 'var(--p-success)', bg: 'rgba(34,197,94,0.10)' },
    draft:     { label: 'Draft',     color: 'var(--p-muted)',   bg: 'var(--p-surface-2)' },
    expired:   { label: 'Expirado',  color: 'var(--p-warning)', bg: 'rgba(245,158,11,0.10)' },
  }
  const m = map[status]
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        padding: '2px 8px',
        borderRadius: 6,
        background: m.bg,
        color: m.color,
        fontSize: 11,
        fontWeight: 600,
        fontFamily: 'var(--font-mono)',
        textTransform: 'uppercase',
        letterSpacing: '0.04em',
        border: '1px solid ' + m.color + '33',
      }}
    >
      {m.label}
    </span>
  )
}

function ChipMulti<T extends string>({
  values,
  options,
  onToggle,
  labelFor,
}: {
  values: T[]
  options: T[]
  onToggle: (v: T) => void
  labelFor?: (v: T) => string
}) {
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
      {options.map((o) => {
        const selected = values.includes(o)
        return (
          <button
            key={o}
            type="button"
            onClick={() => onToggle(o)}
            style={{
              padding: '4px 10px',
              borderRadius: 6,
              border: '1px solid ' + (selected ? 'var(--p-accent)' : 'var(--p-border)'),
              background: selected ? 'var(--p-accent-soft)' : 'var(--p-surface-2)',
              color: selected ? 'var(--p-accent)' : 'var(--p-muted)',
              fontSize: 11,
              fontFamily: 'var(--font-mono)',
              cursor: 'pointer',
              fontWeight: 600,
              letterSpacing: '0.02em',
            }}
          >
            {labelFor ? labelFor(o) : o}
          </button>
        )
      })}
    </div>
  )
}

// ── Page ─────────────────────────────────────────────────────────────────────

type StatusFilter = 'all' | AnnouncementStatus

export function PlatformAnnouncements() {
  const [items, setItems] = useState<PlatformAnnouncement[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<StatusFilter>('all')
  const [presets, setPresets] = useState<IndustryPreset[]>([])

  const [drawerOpen, setDrawerOpen] = useState(false)
  const [editing, setEditing] = useState<PlatformAnnouncement | null>(null)
  const [form, setForm] = useState<FormState>(EMPTY_FORM)
  const [saving, setSaving] = useState(false)

  const [toDelete, setToDelete] = useState<PlatformAnnouncement | null>(null)
  const [deleting, setDeleting] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [rows, ps] = await Promise.all([
        announcementsApi.list(),
        platformApi.getPresets().catch(() => [] as IndustryPreset[]),
      ])
      setItems(Array.isArray(rows) ? rows : [])
      setPresets(Array.isArray(ps) ? ps : [])
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'No se pudieron cargar los comunicados')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const counts = useMemo(() => {
    const c = { published: 0, draft: 0, expired: 0 }
    for (const it of items) c[it.status] += 1
    return c
  }, [items])

  const filtered = useMemo(() => {
    if (filter === 'all') return items
    return items.filter((i) => i.status === filter)
  }, [items, filter])

  const industryOptions = useMemo(
    () => presets.map((p) => p.industry_type).sort(),
    [presets],
  )

  const openCreate = () => {
    setEditing(null)
    setForm(EMPTY_FORM)
    setDrawerOpen(true)
  }

  const openEdit = (a: PlatformAnnouncement) => {
    setEditing(a)
    setForm(formFromAnnouncement(a))
    setDrawerOpen(true)
  }

  const closeDrawer = () => {
    if (saving) return
    setDrawerOpen(false)
    setEditing(null)
  }

  const save = async (publish: boolean) => {
    const title = form.title.trim()
    if (!title) { toast.error('El título es requerido'); return }
    if (!form.body_md.trim()) { toast.error('El cuerpo es requerido'); return }

    const targets: AnnouncementCreatePayload['targets'] = {}
    if (form.industries.length) targets.industries = form.industries
    if (form.plans.length)       targets.plans = form.plans
    const ids = parseOrgIds(form.org_ids_text)
    if (ids.length)              targets.org_ids = ids
    const hasTargets = Object.keys(targets).length > 0

    setSaving(true)
    try {
      if (editing) {
        const updated = await announcementsApi.update(editing.id, {
          title,
          body_md: form.body_md,
          severity: form.severity,
          targets: hasTargets ? targets : {},
          expires_at: localInputToIso(form.expires_at),
        })
        // If user pressed Publish while editing a draft, flip status.
        let final = updated
        if (publish && !updated.published_at) {
          final = await announcementsApi.publish(editing.id)
        }
        setItems((prev) => prev.map((i) => (i.id === final.id ? final : i)))
        toast.success(publish ? 'Comunicado publicado' : 'Cambios guardados')
      } else {
        const created = await announcementsApi.create({
          title,
          body_md: form.body_md,
          severity: form.severity,
          targets: hasTargets ? targets : undefined,
          expires_at: localInputToIso(form.expires_at),
          publish_now: publish,
        })
        setItems((prev) => [created, ...prev])
        toast.success(publish ? 'Comunicado publicado' : 'Draft guardado')
      }
      setDrawerOpen(false)
      setEditing(null)
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'No se pudo guardar')
    } finally {
      setSaving(false)
    }
  }

  const togglePublish = async (a: PlatformAnnouncement) => {
    try {
      const fn = a.published_at ? announcementsApi.unpublish : announcementsApi.publish
      const updated = await fn(a.id)
      setItems((prev) => prev.map((i) => (i.id === updated.id ? updated : i)))
      toast.success(a.published_at ? 'Despublicado' : 'Publicado')
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'No se pudo cambiar estado')
    }
  }

  const confirmDelete = async () => {
    if (!toDelete) return
    setDeleting(true)
    try {
      await announcementsApi.remove(toDelete.id)
      setItems((prev) => prev.filter((i) => i.id !== toDelete.id))
      toast.success('Comunicado eliminado')
      setToDelete(null)
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'No se pudo eliminar')
    } finally {
      setDeleting(false)
    }
  }

  return (
    <>
      <main className="pv2-main">
        {/* Breadcrumb + header */}
        <div className="crumb">
          <span>Platform</span>
          <span className="sep">/</span>
          <span>Admin</span>
          <span className="sep">/</span>
          <span className="now">Announcements</span>
        </div>
        <div className="page-head">
          <div>
            <h1>Announcements</h1>
            <div className="sub">Comunicados a tenants · banners, mantenimientos, anuncios</div>
          </div>
          <div className="right">
            <button className="btn primary" type="button" onClick={openCreate}>
              <i className="fa-solid fa-plus" />
              Nuevo comunicado
            </button>
          </div>
        </div>

        {/* KPIs */}
        <section style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14 }}>
          <KPICardV2 label="Publicados" value={counts.published} icon="fa-bullhorn" />
          <KPICardV2 label="Drafts" value={counts.draft} icon="fa-file-pen" />
          <KPICardV2 label="Expirados" value={counts.expired} icon="fa-hourglass-end" />
        </section>

        {/* Filter pills */}
        <div className="pill-group" role="tablist" aria-label="Filtrar comunicados">
          {STATUS_FILTERS.map((f) => (
            <button
              key={f.key}
              type="button"
              role="tab"
              aria-pressed={f.key === filter}
              className={'pill ' + (f.key === filter ? 'active' : '')}
              onClick={() => setFilter(f.key)}
            >
              {f.label}
            </button>
          ))}
        </div>

        {/* List */}
        {loading ? (
          <div style={{ color: 'var(--p-muted)', fontSize: 13 }}>
            <i className="fa-solid fa-circle-notch fa-spin" /> Cargando…
          </div>
        ) : filtered.length === 0 ? (
          <div
            style={{
              border: '1px dashed var(--p-border)',
              borderRadius: 12,
              padding: '40px 24px',
              textAlign: 'center',
              color: 'var(--p-muted)',
              fontSize: 13,
            }}
          >
            <div style={{ fontSize: 28, marginBottom: 10, color: 'var(--p-hint)' }}>
              <i className="fa-solid fa-bullhorn" />
            </div>
            <div style={{ color: 'var(--p-text)', fontSize: 15, fontWeight: 600, marginBottom: 4 }}>
              Sin comunicados
            </div>
            <div>Crea uno nuevo para difundir un aviso a tus tenants.</div>
          </div>
        ) : (
          <section style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {filtered.map((a) => (
              <AnnouncementCard
                key={a.id}
                ann={a}
                onEdit={() => openEdit(a)}
                onToggle={() => togglePublish(a)}
                onDelete={() => setToDelete(a)}
              />
            ))}
          </section>
        )}
      </main>

      {/* Editor drawer */}
      <SideDrawer
        open={drawerOpen}
        title={editing ? 'Editar comunicado' : 'Nuevo comunicado'}
        subtitle={editing ? `#${editing.id}` : 'Se guarda como draft hasta publicar'}
        onClose={closeDrawer}
        width={760}
      >
        <EditorForm
          form={form}
          setForm={setForm}
          industryOptions={industryOptions}
        />
        <div
          style={{
            marginTop: 16,
            display: 'flex',
            justifyContent: 'flex-end',
            gap: 10,
            paddingTop: 14,
            borderTop: '1px solid var(--p-border)',
          }}
        >
          <button
            onClick={closeDrawer}
            disabled={saving}
            style={{
              background: 'var(--p-surface-2)',
              color: 'var(--p-text)',
              border: '1px solid var(--p-border)',
              padding: '8px 16px',
              borderRadius: 8,
              cursor: saving ? 'not-allowed' : 'pointer',
              fontSize: 13,
              fontWeight: 500,
              opacity: saving ? 0.6 : 1,
            }}
          >
            Cancelar
          </button>
          <button
            onClick={() => save(false)}
            disabled={saving}
            style={{
              background: 'var(--p-surface)',
              color: 'var(--p-text)',
              border: '1px solid var(--p-border)',
              padding: '8px 16px',
              borderRadius: 8,
              cursor: saving ? 'not-allowed' : 'pointer',
              fontSize: 13,
              fontWeight: 600,
              opacity: saving ? 0.6 : 1,
            }}
          >
            {saving ? 'Guardando…' : 'Guardar draft'}
          </button>
          <button
            onClick={() => save(true)}
            disabled={saving}
            style={{
              background: 'var(--p-accent)',
              color: '#fff',
              border: '1px solid var(--p-accent)',
              padding: '8px 18px',
              borderRadius: 8,
              cursor: saving ? 'not-allowed' : 'pointer',
              fontSize: 13,
              fontWeight: 600,
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              opacity: saving ? 0.6 : 1,
            }}
          >
            {saving && <i className="fa-solid fa-circle-notch fa-spin" style={{ fontSize: 11 }} />}
            <i className="fa-solid fa-bullhorn" style={{ fontSize: 11 }} />
            {editing?.published_at ? 'Guardar y re-publicar' : 'Publicar'}
          </button>
        </div>
      </SideDrawer>

      <ConfirmModal
        open={!!toDelete}
        title="Eliminar comunicado"
        message={
          'Vas a borrar permanentemente este comunicado. ' +
          'Los tenants que lo hubieran visto conservarán su registro local, pero no se volverá a emitir. ' +
          'Esta acción no se puede deshacer.'
        }
        resourceName={toDelete?.title ?? ''}
        destructive
        onClose={() => !deleting && setToDelete(null)}
        onConfirm={confirmDelete}
        busy={deleting}
      />
    </>
  )
}

// ── Card ─────────────────────────────────────────────────────────────────────

function AnnouncementCard({
  ann,
  onEdit,
  onToggle,
  onDelete,
}: {
  ann: PlatformAnnouncement
  onEdit: () => void
  onToggle: () => void
  onDelete: () => void
}) {
  const preview = useMemo(() => {
    const stripped = ann.body_md.replace(/[#*`\-\[\]\(\)]/g, '').replace(/\s+/g, ' ').trim()
    return stripped.length > 160 ? stripped.slice(0, 160) + '…' : stripped
  }, [ann.body_md])

  const targets = ann.targets
  const targetsSummary = useMemo(() => {
    if (!targets || (
      !(targets.industries?.length) &&
      !(targets.plans?.length) &&
      !(targets.org_ids?.length)
    )) {
      return 'Universal · todos los tenants'
    }
    const parts: string[] = []
    if (targets.industries?.length) parts.push(`${targets.industries.length} ind.`)
    if (targets.plans?.length)      parts.push(`${targets.plans.length} plan(es)`)
    if (targets.org_ids?.length)    parts.push(`${targets.org_ids.length} org(s)`)
    return parts.join(' · ')
  }, [targets])

  const created = ann.created_at ? new Date(ann.created_at).toLocaleString() : '—'

  return (
    <article
      style={{
        background: 'var(--p-surface)',
        border: '1px solid var(--p-border)',
        borderRadius: 12,
        padding: '16px 18px',
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8, marginBottom: 6 }}>
            <SeverityChip severity={ann.severity} />
            <StatusChip status={ann.status} />
            <span style={{ color: 'var(--p-hint)', fontSize: 11, fontFamily: 'var(--font-mono)' }}>
              #{ann.id}
            </span>
          </div>
          <h3
            style={{
              margin: 0,
              color: 'var(--p-text)',
              fontFamily: 'var(--font-display)',
              fontSize: 17,
              letterSpacing: '-0.015em',
              fontWeight: 600,
              lineHeight: 1.25,
            }}
          >
            {ann.title}
          </h3>
          <p style={{ margin: '6px 0 0', color: 'var(--p-muted)', fontSize: 13, lineHeight: 1.5 }}>
            {preview || <em style={{ color: 'var(--p-hint)' }}>Sin contenido</em>}
          </p>
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 14, color: 'var(--p-muted)', fontSize: 12 }}>
        <span>
          <i className="fa-solid fa-bullseye" style={{ marginRight: 6, color: 'var(--p-hint)' }} />
          {targetsSummary}
        </span>
        <span>
          <i className="fa-solid fa-clock" style={{ marginRight: 6, color: 'var(--p-hint)' }} />
          {created}
        </span>
        {ann.expires_at && (
          <span>
            <i className="fa-solid fa-hourglass-half" style={{ marginRight: 6, color: 'var(--p-hint)' }} />
            Expira {new Date(ann.expires_at).toLocaleString()}
          </span>
        )}
      </div>

      <div style={{ display: 'flex', gap: 8, marginTop: 4, borderTop: '1px solid var(--p-border-2, var(--p-border))', paddingTop: 10 }}>
        <button
          type="button"
          onClick={onEdit}
          style={{
            background: 'var(--p-surface-2)',
            border: '1px solid var(--p-border)',
            color: 'var(--p-text)',
            padding: '6px 12px',
            borderRadius: 6,
            fontSize: 12,
            fontWeight: 500,
            cursor: 'pointer',
          }}
        >
          <i className="fa-solid fa-pen" style={{ fontSize: 10, marginRight: 6 }} />
          Editar
        </button>
        <button
          type="button"
          onClick={onToggle}
          style={{
            background: ann.published_at ? 'var(--p-surface-2)' : 'var(--p-accent)',
            border: '1px solid ' + (ann.published_at ? 'var(--p-border)' : 'var(--p-accent)'),
            color: ann.published_at ? 'var(--p-text)' : '#fff',
            padding: '6px 12px',
            borderRadius: 6,
            fontSize: 12,
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          <i
            className={'fa-solid ' + (ann.published_at ? 'fa-eye-slash' : 'fa-bullhorn')}
            style={{ fontSize: 10, marginRight: 6 }}
          />
          {ann.published_at ? 'Despublicar' : 'Publicar'}
        </button>
        <button
          type="button"
          onClick={onDelete}
          style={{
            marginLeft: 'auto',
            background: 'transparent',
            border: '1px solid var(--p-border)',
            color: 'var(--p-danger)',
            padding: '6px 12px',
            borderRadius: 6,
            fontSize: 12,
            fontWeight: 500,
            cursor: 'pointer',
          }}
        >
          <i className="fa-solid fa-trash" style={{ fontSize: 10, marginRight: 6 }} />
          Eliminar
        </button>
      </div>
    </article>
  )
}

// ── Editor ───────────────────────────────────────────────────────────────────

function EditorForm({
  form,
  setForm,
  industryOptions,
}: {
  form: FormState
  setForm: (updater: FormState | ((prev: FormState) => FormState)) => void
  industryOptions: string[]
}) {
  const update = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }))

  const toggleIndustry = (v: string) =>
    setForm((prev) => ({
      ...prev,
      industries: prev.industries.includes(v)
        ? prev.industries.filter((x) => x !== v)
        : [...prev.industries, v],
    }))

  const togglePlan = (v: Plan) =>
    setForm((prev) => ({
      ...prev,
      plans: prev.plans.includes(v) ? prev.plans.filter((x) => x !== v) : [...prev.plans, v],
    }))

  const previewHtml = useMemo(() => renderMarkdown(form.body_md || ''), [form.body_md])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <div style={fieldStyle}>
        <label style={labelStyle}>Título</label>
        <input
          style={inputStyle}
          value={form.title}
          onChange={(e) => update('title', e.target.value)}
          placeholder="Ej. Mantenimiento programado domingo 02:00"
          maxLength={200}
        />
      </div>

      <div style={fieldStyle}>
        <label style={labelStyle}>Severidad</label>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {SEVERITIES.map((s) => {
            const meta = SEVERITY_META[s]
            const active = form.severity === s
            return (
              <button
                key={s}
                type="button"
                onClick={() => update('severity', s)}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 6,
                  padding: '6px 10px',
                  borderRadius: 6,
                  border: '1px solid ' + (active ? meta.token : 'var(--p-border)'),
                  background: active ? meta.bg : 'var(--p-surface-2)',
                  color: active ? meta.token : 'var(--p-muted)',
                  fontSize: 12,
                  fontWeight: 600,
                  cursor: 'pointer',
                  fontFamily: 'var(--font-mono)',
                  textTransform: 'uppercase',
                  letterSpacing: '0.04em',
                }}
              >
                <i className={'fa-solid ' + meta.icon} style={{ fontSize: 11 }} />
                {meta.label}
              </button>
            )
          })}
        </div>
      </div>

      <div style={fieldStyle}>
        <label style={labelStyle}>Cuerpo (Markdown)</label>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
          <textarea
            value={form.body_md}
            onChange={(e) => update('body_md', e.target.value)}
            placeholder={'# Título\n\nCuerpo con **bold**, *italic*, `code`.\n\n- lista\n- de items\n\n[link](https://ejemplo.com)'}
            style={{
              ...inputStyle,
              minHeight: 220,
              resize: 'vertical',
              fontFamily: 'var(--font-mono)',
              fontSize: 12,
              lineHeight: 1.55,
            }}
          />
          <div
            className="md-preview"
            style={{
              background: 'var(--p-surface-2)',
              border: '1px solid var(--p-border)',
              borderRadius: 6,
              padding: '10px 14px',
              minHeight: 220,
              fontSize: 13,
              color: 'var(--p-text)',
              overflow: 'auto',
              lineHeight: 1.55,
            }}
            dangerouslySetInnerHTML={{ __html: previewHtml }}
          />
        </div>
        <style>{`
          .md-preview h1 { font-family: var(--font-display); font-size: 22px; letter-spacing: -0.02em; margin: 0 0 6px; color: var(--p-text); font-weight: 600; }
          .md-preview h2 { font-family: var(--font-display); font-size: 18px; letter-spacing: -0.015em; margin: 10px 0 4px; color: var(--p-text); font-weight: 600; }
          .md-preview h3 { font-family: var(--font-display); font-size: 14px; margin: 8px 0 4px; color: var(--p-text); font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; }
          .md-preview p  { margin: 0 0 8px; }
          .md-preview ul { margin: 4px 0 10px; padding-left: 18px; }
          .md-preview li { margin: 2px 0; }
          .md-preview code { background: var(--p-surface); padding: 1px 6px; border-radius: 4px; font-family: var(--font-mono); font-size: 11px; color: var(--p-accent); border: 1px solid var(--p-border); }
          .md-preview a  { color: var(--p-accent); text-decoration: underline; }
          .md-preview strong { color: var(--p-text); }
        `}</style>
      </div>

      <div style={fieldStyle}>
        <label style={labelStyle}>Targeting · industrias</label>
        {industryOptions.length === 0 ? (
          <div style={{ fontSize: 12, color: 'var(--p-muted)' }}>(sin presets cargados)</div>
        ) : (
          <ChipMulti
            values={form.industries}
            options={industryOptions}
            onToggle={toggleIndustry}
          />
        )}
      </div>

      <div style={fieldStyle}>
        <label style={labelStyle}>Targeting · planes</label>
        <ChipMulti<Plan>
          values={form.plans}
          options={PLANS}
          onToggle={togglePlan}
          labelFor={nombrePlan}
        />
      </div>

      <div style={fieldStyle}>
        <label style={labelStyle}>Targeting · org IDs (separadas por coma)</label>
        <input
          style={inputStyle}
          value={form.org_ids_text}
          onChange={(e) => update('org_ids_text', e.target.value)}
          placeholder="12, 34, 56"
        />
        <div style={{ fontSize: 11, color: 'var(--p-hint)', marginTop: 4 }}>
          Dejar industrias / planes / IDs vacíos = universal (todos los tenants).
        </div>
      </div>

      <div style={fieldStyle}>
        <label style={labelStyle}>Expira (opcional)</label>
        <input
          style={inputStyle}
          type="datetime-local"
          value={form.expires_at}
          onChange={(e) => update('expires_at', e.target.value)}
        />
      </div>
    </div>
  )
}

export default PlatformAnnouncements
