import { useEffect, useMemo, useRef, useState } from 'react'
import {
  platformApi,
  PlatformModuleDef,
  ModuleDependencies,
} from '../../api/platform'
import { toast } from '../../store/toastStore'
import { PlatformPageShell } from '../../components/platform/PlatformPageShell'
import { KPICard } from '../../components/platform/KPICard'
import { DataTable, DataTableColumn } from '../../components/platform/DataTable'
import { StatusBadge } from '../../components/platform/StatusBadge'
import { SideDrawer } from '../../components/platform/SideDrawer'
import { ConfirmModal } from '../../components/platform/ConfirmModal'

// ── Form state ──────────────────────────────────────────────────────────────
type ModuleFormState = {
  key: string
  name: string
  description: string
  scope: string
  status: string
}

const SCOPES = ['GLOBAL', 'HQ', 'BRANCH', 'WAREHOUSE'] as const
const STATUSES = ['BETA', 'STABLE'] as const

const EMPTY_FORM: ModuleFormState = {
  key: '',
  name: '',
  description: '',
  scope: 'GLOBAL',
  status: 'BETA',
}

function moduleToForm(m: PlatformModuleDef): ModuleFormState {
  return {
    key: m.key,
    name: m.name || '',
    description: m.description || '',
    scope: m.scope || 'GLOBAL',
    status: m.status || 'BETA',
  }
}

// ── Inline shared styles (tokens) ───────────────────────────────────────────
const inputStyle: React.CSSProperties = {
  width: '100%',
  background: 'var(--p-surface-2)',
  color: 'var(--p-text)',
  border: '1px solid var(--p-border)',
  borderRadius: 4,
  padding: '8px 10px',
  fontSize: 13,
  outline: 'none',
  boxSizing: 'border-box',
  fontFamily: 'inherit',
}

const inputDisabledStyle: React.CSSProperties = {
  ...inputStyle,
  background: 'var(--p-surface)',
  color: 'var(--p-muted)',
  cursor: 'not-allowed',
}

const labelStyle: React.CSSProperties = {
  display: 'block',
  fontSize: '0.65rem',
  color: 'var(--p-muted)',
  textTransform: 'uppercase',
  letterSpacing: '0.08em',
  fontWeight: 600,
  marginBottom: 4,
}

const buttonPrimary: React.CSSProperties = {
  background: 'var(--p-teal)',
  color: 'var(--dax-on-accent)',
  fontWeight: 700,
  border: 'none',
  padding: '8px 16px',
  borderRadius: 4,
  fontSize: 12,
  cursor: 'pointer',
  display: 'inline-flex',
  alignItems: 'center',
  gap: 6,
}

const chipStyle = (active: boolean): React.CSSProperties => ({
  background: active ? 'rgba(0,201,177,0.12)' : 'var(--p-surface-2)',
  color: active ? 'var(--p-teal)' : 'var(--p-muted)',
  border: `1px solid ${active ? 'var(--p-teal)' : 'var(--p-border)'}`,
  padding: '4px 10px',
  borderRadius: 999,
  fontSize: 11,
  fontWeight: 600,
  cursor: 'pointer',
  textTransform: 'uppercase',
  letterSpacing: '0.04em',
})

// ── Scope pill (HQ/BRANCH/WAREHOUSE/GLOBAL) ────────────────────────────────
const SCOPE_COLOR: Record<string, { bg: string; color: string }> = {
  GLOBAL:    { bg: 'rgba(0,229,255,0.10)',  color: 'var(--p-cyan)' },
  HQ:        { bg: 'rgba(192,38,211,0.12)', color: 'var(--p-magenta)' },
  BRANCH:    { bg: 'rgba(0,201,177,0.12)',  color: 'var(--p-teal)' },
  WAREHOUSE: { bg: 'rgba(245,158,11,0.12)', color: 'var(--p-warning)' },
}

function ScopePill({ value }: { value: string }) {
  const c = SCOPE_COLOR[value] ?? { bg: 'var(--p-surface-2)', color: 'var(--p-muted)' }
  return (
    <span style={{
      background: c.bg,
      color: c.color,
      padding: '2px 8px',
      borderRadius: 4,
      fontSize: 11,
      fontFamily: 'monospace',
      fontWeight: 600,
    }}>
      {value || '—'}
    </span>
  )
}

// ── Row actions menu ────────────────────────────────────────────────────────
function RowMenu({
  module,
  onEdit,
  onViewDeps,
  onDelete,
}: {
  module: PlatformModuleDef
  onEdit: () => void
  onViewDeps: () => void
  onDelete: () => void
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    window.addEventListener('mousedown', onClick)
    return () => window.removeEventListener('mousedown', onClick)
  }, [open])

  const itemStyle: React.CSSProperties = {
    display: 'block',
    width: '100%',
    background: 'transparent',
    color: 'var(--p-text)',
    border: 'none',
    padding: '8px 12px',
    fontSize: 12,
    textAlign: 'left',
    cursor: 'pointer',
    fontFamily: 'inherit',
  }
  const dangerStyle: React.CSSProperties = { ...itemStyle, color: 'var(--p-danger)' }

  return (
    <div ref={ref} style={{ position: 'relative', display: 'inline-block' }}>
      <button
        onClick={(e) => { e.stopPropagation(); setOpen(o => !o) }}
        aria-label={`Acciones ${module.key}`}
        style={{
          background: 'transparent',
          border: '1px solid var(--p-border)',
          color: 'var(--p-muted)',
          width: 28,
          height: 28,
          borderRadius: 4,
          cursor: 'pointer',
          fontSize: 14,
          lineHeight: 1,
        }}
      >
        ⋮
      </button>
      {open && (
        <div
          onClick={(e) => e.stopPropagation()}
          style={{
            position: 'absolute',
            right: 0,
            top: 32,
            minWidth: 200,
            background: 'var(--p-surface)',
            border: '1px solid var(--p-border)',
            borderRadius: 4,
            boxShadow: '0 4px 16px rgba(0,0,0,0.4)',
            zIndex: 50,
          }}
        >
          <button style={itemStyle} onClick={() => { setOpen(false); onViewDeps() }}>
            <i className="fa-solid fa-diagram-project" style={{ marginRight: 8, width: 12 }} /> Ver dependencias
          </button>
          <button style={itemStyle} onClick={() => { setOpen(false); onEdit() }}>
            <i className="fa-solid fa-pen" style={{ marginRight: 8, width: 12 }} /> Editar
          </button>
          <div style={{ borderTop: '1px solid var(--p-border)' }} />
          <button style={dangerStyle} onClick={() => { setOpen(false); onDelete() }}>
            <i className="fa-solid fa-trash" style={{ marginRight: 8, width: 12 }} /> Eliminar
          </button>
        </div>
      )}
    </div>
  )
}

// ── Page ────────────────────────────────────────────────────────────────────
export function PlatformModules() {
  // Data
  const [modules, setModules] = useState<PlatformModuleDef[]>([])
  const [deps, setDeps] = useState<Record<string, ModuleDependencies>>({})
  const [loading, setLoading] = useState(true)

  // Filters
  type ScopeFilter = 'all' | 'GLOBAL' | 'HQ' | 'BRANCH' | 'WAREHOUSE'
  type StatusFilter = 'all' | 'BETA' | 'STABLE'
  const [scopeFilter, setScopeFilter] = useState<ScopeFilter>('all')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')

  // Drawer (create/edit)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [editing, setEditing] = useState<PlatformModuleDef | null>(null)
  const [form, setForm] = useState<ModuleFormState>(EMPTY_FORM)
  const [saving, setSaving] = useState(false)
  const [keyError, setKeyError] = useState<string | null>(null)

  // Dependencies side panel
  const [depsTarget, setDepsTarget] = useState<PlatformModuleDef | null>(null)

  // Delete (typed-name)
  const [delTarget, setDelTarget] = useState<PlatformModuleDef | null>(null)
  const [deleting, setDeleting] = useState(false)

  // ── Load data ─────────────────────────────────────────────────────────────
  // Una sola query agregada para counts (en vez de N paralelas que agotaban
  // el pool de conexiones del backend). Cuando el usuario abre el panel de
  // dependencias por módulo se hace la fetch full (con presets/orgs lista).
  const load = async () => {
    setLoading(true)
    try {
      const [list, counts] = await Promise.all([
        platformApi.getModulesCatalog(),
        platformApi.getModulesCounts().catch(() => ({} as Record<string, { presets: number; orgs: number }>)),
      ])
      setModules(list)

      // Convertir counts en el shape de ModuleDependencies (sin las listas
      // detalladas, que se llenan al abrir el panel de un módulo).
      const depsMap: Record<string, ModuleDependencies> = {}
      for (const m of list) {
        const c = counts[m.key]
        depsMap[m.key] = {
          module_key: m.key,
          presets: Array(c?.presets ?? 0).fill(null) as any,
          orgs: Array(c?.orgs ?? 0).fill(null) as any,
        }
      }
      setDeps(depsMap)
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'No se pudo cargar el catálogo')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  // Refresh deps for a single module after a write (cheap).
  const refreshDeps = async (key: string) => {
    try {
      const d = await platformApi.getModuleDependencies(key)
      setDeps(prev => ({ ...prev, [key]: d }))
    } catch {
      // silent
    }
  }

  // ── KPIs ──────────────────────────────────────────────────────────────────
  const kpis = useMemo(() => {
    const total = modules.length
    const beta = modules.filter(m => m.status === 'BETA').length
    const stable = modules.filter(m => m.status === 'STABLE').length
    const orgsActivasTotal = Object.values(deps).reduce((acc, d) => acc + (d.orgs?.length ?? 0), 0)
    return { total, beta, stable, orgsActivasTotal }
  }, [modules, deps])

  // ── Filtered rows ─────────────────────────────────────────────────────────
  const filtered = useMemo(() => {
    return modules.filter(m => {
      if (scopeFilter !== 'all' && m.scope !== scopeFilter) return false
      if (statusFilter !== 'all' && m.status !== statusFilter) return false
      return true
    })
  }, [modules, scopeFilter, statusFilter])

  // ── Drawer handlers ───────────────────────────────────────────────────────
  const openCreate = () => {
    setEditing(null)
    setForm(EMPTY_FORM)
    setKeyError(null)
    setDrawerOpen(true)
  }

  const openEdit = (m: PlatformModuleDef) => {
    setEditing(m)
    setForm(moduleToForm(m))
    setKeyError(null)
    setDrawerOpen(true)
  }

  const closeDrawer = () => {
    setDrawerOpen(false)
    setEditing(null)
    setKeyError(null)
  }

  // kebab-case lowercase (letters, digits, hyphens, underscores)
  const KEY_RE = /^[a-z][a-z0-9_-]*$/

  const validateKey = (k: string): string | null => {
    if (!k.trim()) return 'La key es requerida'
    if (!KEY_RE.test(k)) return 'Sólo minúsculas, dígitos, "-" y "_" (debe iniciar con letra)'
    if (modules.some(m => m.key === k)) return 'Ya existe un módulo con esta key'
    return null
  }

  const onKeyChange = (raw: string) => {
    const v = raw.toLowerCase().replace(/[^a-z0-9_-]/g, '')
    setForm(f => ({ ...f, key: v }))
    setKeyError(editing ? null : validateKey(v))
  }

  const handleSave = async () => {
    if (!editing) {
      const err = validateKey(form.key)
      if (err) { setKeyError(err); toast.error(err); return }
    }
    if (!form.name.trim()) {
      toast.error('El nombre es requerido')
      return
    }
    setSaving(true)
    try {
      if (editing) {
        await platformApi.updateModule(editing.key, {
          name: form.name,
          description: form.description,
          scope: form.scope,
          status: form.status,
        })
        toast.success(`Módulo "${editing.key}" actualizado`)
      } else {
        await platformApi.createModule({
          key: form.key,
          name: form.name,
          description: form.description || undefined,
          scope: form.scope,
          status: form.status,
        })
        toast.success(`Módulo "${form.key}" creado`)
      }
      closeDrawer()
      load()
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'No se pudo guardar el módulo')
    } finally {
      setSaving(false)
    }
  }

  // ── Dependencies panel ────────────────────────────────────────────────────
  const openDeps = async (m: PlatformModuleDef) => {
    setDepsTarget(m)
    // ensure deps fresh on open
    refreshDeps(m.key)
  }

  const closeDeps = () => setDepsTarget(null)

  // ── Delete handlers ───────────────────────────────────────────────────────
  const requestDelete = async (m: PlatformModuleDef) => {
    // Pre-fetch latest deps; if there are active orgs, block.
    let d: ModuleDependencies | undefined = deps[m.key]
    try {
      d = await platformApi.getModuleDependencies(m.key)
      setDeps(prev => ({ ...prev, [m.key]: d! }))
    } catch {
      // fall through to current state
    }
    const orgsCount = d?.orgs?.length ?? 0
    if (orgsCount > 0) {
      toast.error(`Tiene ${orgsCount} org${orgsCount === 1 ? '' : 's'} activa${orgsCount === 1 ? '' : 's'} — desactivar primero`)
      return
    }
    setDelTarget(m)
  }

  const handleDelete = async () => {
    if (!delTarget) return
    setDeleting(true)
    try {
      await platformApi.deleteModule(delTarget.key)
      toast.success(`Módulo "${delTarget.key}" eliminado`)
      setDelTarget(null)
      load()
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'No se pudo eliminar el módulo')
    } finally {
      setDeleting(false)
    }
  }

  // ── Count cell helper ─────────────────────────────────────────────────────
  const CountCell = ({ value, accent }: { value: number | undefined; accent?: 'teal' | 'warning' }) => {
    if (value === undefined) {
      return (
        <span style={{ color: 'var(--p-muted)' }}>
          <i className="fa-solid fa-spinner fa-spin" style={{ fontSize: 10 }} />
        </span>
      )
    }
    if (value === 0) return <span style={{ color: 'var(--p-muted)' }}>0</span>
    const color = accent === 'warning' ? 'var(--p-warning)' : 'var(--p-teal)'
    const bg = accent === 'warning' ? 'rgba(245,158,11,0.12)' : 'rgba(0,201,177,0.12)'
    return (
      <span style={{
        background: bg,
        color,
        padding: '2px 10px',
        borderRadius: 999,
        fontSize: 11,
        fontWeight: 700,
      }}>
        {value}
      </span>
    )
  }

  // ── Table columns ─────────────────────────────────────────────────────────
  const columns: DataTableColumn<PlatformModuleDef>[] = [
    {
      key: 'key',
      label: 'Key',
      sortable: true,
      sortValue: m => m.key.toLowerCase(),
      accessor: m => (
        <div>
          <div style={{ fontFamily: 'monospace', fontWeight: 700, color: 'var(--p-text)', fontSize: 13 }}>
            {m.key}
          </div>
          {m.description && (
            <div style={{
              fontSize: 11,
              color: 'var(--p-muted)',
              marginTop: 2,
              maxWidth: 360,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}>
              {m.description}
            </div>
          )}
        </div>
      ),
    },
    {
      key: 'name',
      label: 'Nombre',
      sortable: true,
      sortValue: m => (m.name || '').toLowerCase(),
      accessor: m => (
        <span style={{ color: 'var(--p-text)', fontSize: 13 }}>{m.name || '—'}</span>
      ),
    },
    {
      key: 'scope',
      label: 'Scope',
      sortable: true,
      sortValue: m => m.scope || '',
      accessor: m => <ScopePill value={m.scope} />,
    },
    {
      key: 'status',
      label: 'Status',
      sortable: true,
      sortValue: m => m.status || '',
      accessor: m => (
        m.status === 'STABLE'
          ? <StatusBadge status="stable" />
          : m.status === 'BETA'
            ? <StatusBadge status="beta" />
            : <span style={{
                background: 'var(--p-surface-2)',
                color: 'var(--p-muted)',
                padding: '2px 8px',
                borderRadius: 4,
                fontSize: 11,
                fontFamily: 'monospace',
              }}>{m.status}</span>
      ),
    },
    {
      key: 'presets',
      label: 'Presets',
      sortable: true,
      sortValue: m => deps[m.key]?.presets?.length ?? -1,
      accessor: m => <CountCell value={deps[m.key]?.presets?.length} accent="teal" />,
    },
    {
      key: 'orgs',
      label: 'Orgs activas',
      sortable: true,
      sortValue: m => deps[m.key]?.orgs?.length ?? -1,
      accessor: m => <CountCell value={deps[m.key]?.orgs?.length} accent="warning" />,
    },
    {
      key: 'actions',
      label: '',
      width: '60px',
      accessor: m => (
        <div onClick={e => e.stopPropagation()}>
          <RowMenu
            module={m}
            onEdit={() => openEdit(m)}
            onViewDeps={() => openDeps(m)}
            onDelete={() => requestDelete(m)}
          />
        </div>
      ),
    },
  ]

  // ── Toolbar (filters) ─────────────────────────────────────────────────────
  const toolbar = (
    <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
      <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
        <span style={{
          fontSize: 11,
          color: 'var(--p-muted)',
          fontWeight: 600,
          textTransform: 'uppercase',
          letterSpacing: '0.06em',
        }}>
          Scope:
        </span>
        {(['all', 'GLOBAL', 'HQ', 'BRANCH', 'WAREHOUSE'] as const).map(s => (
          <button key={s} onClick={() => setScopeFilter(s)} style={chipStyle(scopeFilter === s)}>
            {s === 'all' ? 'Todos' : s}
          </button>
        ))}
      </div>
      <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
        <span style={{
          fontSize: 11,
          color: 'var(--p-muted)',
          fontWeight: 600,
          textTransform: 'uppercase',
          letterSpacing: '0.06em',
        }}>
          Status:
        </span>
        {(['all', 'BETA', 'STABLE'] as const).map(s => (
          <button key={s} onClick={() => setStatusFilter(s)} style={chipStyle(statusFilter === s)}>
            {s === 'all' ? 'Todos' : s}
          </button>
        ))}
      </div>
    </div>
  )

  // ── Header + KPI strip ────────────────────────────────────────────────────
  const headerActions = (
    <button onClick={openCreate} style={buttonPrimary}>
      <i className="fa-solid fa-plus" /> Nuevo módulo
    </button>
  )

  const kpiStrip = (
    <>
      <KPICard label="Total módulos" value={kpis.total} accent="teal" icon="fa-cubes" />
      <KPICard label="Stable" value={kpis.stable} accent="cyan" icon="fa-circle-check" />
      <KPICard label="Beta" value={kpis.beta} accent="warning" icon="fa-flask" />
      <KPICard label="Orgs/módulo (suma)" value={kpis.orgsActivasTotal} accent="purple" icon="fa-building" />
    </>
  )

  // ── CSV row ───────────────────────────────────────────────────────────────
  const csvRow = (m: PlatformModuleDef) => ({
    key: m.key,
    name: m.name || '',
    description: m.description || '',
    scope: m.scope,
    status: m.status,
    presets_count: deps[m.key]?.presets?.length ?? '',
    orgs_active_count: deps[m.key]?.orgs?.length ?? '',
  })

  return (
    <PlatformPageShell
      breadcrumb="Platform / Modules"
      title="Catálogo de Módulos"
      actions={headerActions}
      kpis={kpiStrip}
    >
      {loading ? (
        <div style={{
          background: 'var(--p-surface)',
          border: '1px solid var(--p-border)',
          borderRadius: 6,
          padding: '3rem',
          textAlign: 'center',
          color: 'var(--p-muted)',
        }}>
          <i className="fa-solid fa-spinner fa-spin" style={{ fontSize: 24 }} />
          <p style={{ marginTop: 12, fontSize: 13 }}>Cargando catálogo...</p>
        </div>
      ) : (
        <DataTable
          data={filtered}
          columns={columns}
          rowKey={m => m.key}
          searchable
          searchKeys={m => `${m.key} ${m.name || ''}`}
          pageSize={20}
          csvFilename="modules-catalog.csv"
          csvRow={csvRow}
          toolbar={toolbar}
          onRowClick={m => openDeps(m)}
          emptyMessage={modules.length === 0 ? 'Sin módulos en el catálogo' : 'Sin resultados con los filtros aplicados'}
        />
      )}

      {/* Create / Edit drawer */}
      <SideDrawer
        open={drawerOpen}
        title={editing ? `Editar ${editing.key}` : 'Nuevo módulo'}
        onClose={closeDrawer}
        onSave={handleSave}
        saving={saving}
        saveLabel={editing ? 'Guardar' : 'Crear'}
        width={520}
      >
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <div style={{ gridColumn: '1 / -1' }}>
            <label style={labelStyle}>Key *</label>
            <input
              value={form.key}
              onChange={e => onKeyChange(e.target.value)}
              disabled={!!editing}
              title={editing ? 'Key inmutable después de creación' : undefined}
              placeholder="ej: my-feature"
              style={editing ? inputDisabledStyle : inputStyle}
              required
            />
            {!editing && (
              <p style={{
                fontSize: 11,
                color: keyError ? 'var(--p-danger)' : 'var(--p-muted)',
                margin: '4px 0 0',
              }}>
                {keyError ?? 'Sólo minúsculas, dígitos, "-" o "_". Inicia con letra.'}
              </p>
            )}
            {editing && (
              <p style={{ fontSize: 11, color: 'var(--p-muted)', margin: '4px 0 0' }}>
                <i className="fa-solid fa-lock" style={{ marginRight: 4 }} />
                Key inmutable después de creación.
              </p>
            )}
          </div>

          <div style={{ gridColumn: '1 / -1' }}>
            <label style={labelStyle}>Nombre *</label>
            <input
              value={form.name}
              onChange={e => setForm({ ...form, name: e.target.value })}
              placeholder="Nombre legible del módulo"
              style={inputStyle}
              required
            />
          </div>

          <div style={{ gridColumn: '1 / -1' }}>
            <label style={labelStyle}>Descripción</label>
            <textarea
              value={form.description}
              onChange={e => setForm({ ...form, description: e.target.value })}
              placeholder="¿Qué hace este módulo? (opcional)"
              rows={3}
              style={{ ...inputStyle, resize: 'vertical', minHeight: 60 }}
            />
          </div>

          <div>
            <label style={labelStyle}>Scope</label>
            <select
              value={form.scope}
              onChange={e => setForm({ ...form, scope: e.target.value })}
              style={inputStyle}
            >
              {SCOPES.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>

          <div>
            <label style={labelStyle}>Status</label>
            <select
              value={form.status}
              onChange={e => setForm({ ...form, status: e.target.value })}
              style={inputStyle}
            >
              {STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
        </div>
      </SideDrawer>

      {/* Dependencies side panel */}
      <SideDrawer
        open={!!depsTarget}
        title={depsTarget ? `Dependencias de ${depsTarget.key}` : ''}
        onClose={closeDeps}
        width={480}
      >
        {depsTarget && (() => {
          const d = deps[depsTarget.key]
          const presetsList = d?.presets ?? []
          const orgsList = d?.orgs ?? []
          const hasOrgs = orgsList.length > 0
          return (
            <div>
              {/* Module summary */}
              <div style={{
                background: 'var(--p-surface-2)',
                border: '1px solid var(--p-border)',
                borderRadius: 4,
                padding: 12,
                marginBottom: 16,
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                  <span style={{ fontFamily: 'monospace', fontWeight: 700, color: 'var(--p-text)', fontSize: 13 }}>
                    {depsTarget.key}
                  </span>
                  <ScopePill value={depsTarget.scope} />
                  {depsTarget.status === 'STABLE'
                    ? <StatusBadge status="stable" />
                    : <StatusBadge status="beta" />}
                </div>
                {depsTarget.name && (
                  <p style={{ fontSize: 12, color: 'var(--p-text)', margin: 0 }}>
                    {depsTarget.name}
                  </p>
                )}
                {depsTarget.description && (
                  <p style={{ fontSize: 11, color: 'var(--p-muted)', margin: '4px 0 0' }}>
                    {depsTarget.description}
                  </p>
                )}
              </div>

              {/* Warning banner if active orgs */}
              {hasOrgs && (
                <div style={{
                  background: 'rgba(239,68,68,0.08)',
                  border: '1px solid rgba(239,68,68,0.3)',
                  color: 'var(--p-danger)',
                  padding: '10px 12px',
                  borderRadius: 4,
                  fontSize: 12,
                  marginBottom: 16,
                  display: 'flex',
                  gap: 8,
                  alignItems: 'flex-start',
                }}>
                  <i className="fa-solid fa-triangle-exclamation" style={{ marginTop: 2 }} />
                  <span>No se puede eliminar mientras haya orgs activas con este módulo.</span>
                </div>
              )}

              {/* Presets section */}
              <div style={{ marginBottom: 20 }}>
                <p style={{
                  fontSize: 11,
                  color: 'var(--p-muted)',
                  textTransform: 'uppercase',
                  letterSpacing: '0.08em',
                  fontWeight: 600,
                  margin: '0 0 8px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                }}>
                  <span>
                    <i className="fa-solid fa-layer-group" style={{ marginRight: 6 }} />
                    Presets que lo incluyen
                  </span>
                  <span style={{
                    background: 'var(--p-surface-2)',
                    color: 'var(--p-text)',
                    padding: '1px 8px',
                    borderRadius: 999,
                    fontSize: 10,
                  }}>
                    {presetsList.length}
                  </span>
                </p>
                {!d ? (
                  <p style={{ fontSize: 12, color: 'var(--p-muted)' }}>
                    <i className="fa-solid fa-spinner fa-spin" /> Cargando…
                  </p>
                ) : presetsList.length === 0 ? (
                  <p style={{ fontSize: 12, color: 'var(--p-muted)', margin: 0 }}>
                    Ningún preset incluye este módulo.
                  </p>
                ) : (
                  <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
                    {presetsList.map(p => (
                      <li key={p.id} style={{
                        background: 'var(--p-surface-2)',
                        border: '1px solid var(--p-border)',
                        borderRadius: 4,
                        padding: '8px 10px',
                        marginBottom: 6,
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        gap: 8,
                      }}>
                        <div>
                          <div style={{ fontSize: 13, color: 'var(--p-text)', fontWeight: 600 }}>
                            {p.display_name}
                          </div>
                          <div style={{
                            fontSize: 11,
                            color: 'var(--p-muted)',
                            fontFamily: 'monospace',
                            marginTop: 2,
                          }}>
                            {p.industry_type}
                          </div>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              {/* Orgs section */}
              <div>
                <p style={{
                  fontSize: 11,
                  color: 'var(--p-muted)',
                  textTransform: 'uppercase',
                  letterSpacing: '0.08em',
                  fontWeight: 600,
                  margin: '0 0 8px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                }}>
                  <span>
                    <i className="fa-solid fa-building" style={{ marginRight: 6 }} />
                    Orgs activas con este módulo
                  </span>
                  <span style={{
                    background: 'var(--p-surface-2)',
                    color: 'var(--p-text)',
                    padding: '1px 8px',
                    borderRadius: 999,
                    fontSize: 10,
                  }}>
                    {orgsList.length}
                  </span>
                </p>
                {!d ? (
                  <p style={{ fontSize: 12, color: 'var(--p-muted)' }}>
                    <i className="fa-solid fa-spinner fa-spin" /> Cargando…
                  </p>
                ) : orgsList.length === 0 ? (
                  <p style={{ fontSize: 12, color: 'var(--p-muted)', margin: 0 }}>
                    Ninguna organización activa tiene este módulo habilitado.
                  </p>
                ) : (
                  <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
                    {orgsList.map(o => (
                      <li key={o.id} style={{
                        background: 'var(--p-surface-2)',
                        border: '1px solid var(--p-border)',
                        borderRadius: 4,
                        padding: '8px 10px',
                        marginBottom: 6,
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                      }}>
                        <span style={{ fontSize: 13, color: 'var(--p-text)' }}>{o.name}</span>
                        <span style={{
                          fontSize: 11,
                          color: 'var(--p-muted)',
                          fontFamily: 'monospace',
                        }}>
                          #{o.id}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              {/* Footer actions inside the deps drawer */}
              <div style={{
                marginTop: 24,
                paddingTop: 16,
                borderTop: '1px solid var(--p-border)',
                display: 'flex',
                gap: 8,
                justifyContent: 'flex-end',
              }}>
                <button
                  onClick={() => { const t = depsTarget; closeDeps(); openEdit(t!) }}
                  style={{
                    background: 'var(--p-surface-2)',
                    color: 'var(--p-text)',
                    border: '1px solid var(--p-border)',
                    padding: '8px 14px',
                    borderRadius: 4,
                    fontSize: 12,
                    cursor: 'pointer',
                    fontWeight: 600,
                  }}
                >
                  <i className="fa-solid fa-pen" style={{ marginRight: 6 }} /> Editar
                </button>
                <button
                  onClick={() => { const t = depsTarget; closeDeps(); requestDelete(t!) }}
                  disabled={hasOrgs}
                  title={hasOrgs ? 'Desactiva el módulo en todas las orgs primero' : 'Eliminar módulo'}
                  style={{
                    background: hasOrgs ? 'var(--p-surface-2)' : 'rgba(239,68,68,0.12)',
                    color: hasOrgs ? 'var(--p-muted)' : 'var(--p-danger)',
                    border: `1px solid ${hasOrgs ? 'var(--p-border)' : 'rgba(239,68,68,0.3)'}`,
                    padding: '8px 14px',
                    borderRadius: 4,
                    fontSize: 12,
                    cursor: hasOrgs ? 'not-allowed' : 'pointer',
                    fontWeight: 600,
                    opacity: hasOrgs ? 0.6 : 1,
                  }}
                >
                  <i className="fa-solid fa-trash" style={{ marginRight: 6 }} /> Eliminar
                </button>
              </div>
            </div>
          )
        })()}
      </SideDrawer>

      {/* Delete confirmation */}
      <ConfirmModal
        open={!!delTarget}
        title={delTarget ? `Eliminar módulo "${delTarget.key}"` : ''}
        message="Esta acción es permanente. El módulo se eliminará del catálogo global. Sólo es posible si ninguna organización lo tiene habilitado."
        resourceName={delTarget?.key ?? ''}
        destructive
        busy={deleting}
        onClose={() => setDelTarget(null)}
        onConfirm={handleDelete}
      />
    </PlatformPageShell>
  )
}
