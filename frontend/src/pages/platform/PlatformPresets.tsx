import { useEffect, useMemo, useState } from 'react'
import { platformApi, IndustryPreset, Module, PlatformOrg } from '../../api/platform'
import { toast } from '../../store/toastStore'
import { PlatformPageShell } from '../../components/platform/PlatformPageShell'
import { KPICard } from '../../components/platform/KPICard'
import { SideDrawer } from '../../components/platform/SideDrawer'
import { ConfirmModal } from '../../components/platform/ConfirmModal'

// ── Form state ──────────────────────────────────────────────────────────────
type PresetFormState = {
  industry_type: string
  display_name: string
  description: string
  modules: string[]
}

const EMPTY_FORM: PresetFormState = {
  industry_type: '',
  display_name: '',
  description: '',
  modules: [],
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

const buttonSecondary: React.CSSProperties = {
  background: 'var(--p-surface-2)',
  color: 'var(--p-text)',
  border: '1px solid var(--p-border)',
  padding: '6px 12px',
  borderRadius: 4,
  fontSize: 12,
  fontWeight: 600,
  cursor: 'pointer',
}

const buttonDanger: React.CSSProperties = {
  background: 'transparent',
  color: 'var(--p-danger)',
  border: '1px solid rgba(239,68,68,0.4)',
  padding: '6px 12px',
  borderRadius: 4,
  fontSize: 12,
  fontWeight: 600,
  cursor: 'pointer',
}

// Module pill — neutral chip with optional inline status badge
function ModulePill({ moduleKey, status }: { moduleKey: string; status?: string }) {
  const statusInfo: Record<string, { bg: string; color: string; label: string }> = {
    BETA: { bg: 'rgba(245,158,11,0.18)', color: 'var(--p-warning)', label: 'BETA' },
    STABLE: { bg: 'rgba(34,197,94,0.15)', color: 'var(--p-success)', label: 'STABLE' },
  }
  const s = status ? statusInfo[status] : undefined

  return (
    <span style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: 6,
      background: 'var(--p-surface-2)',
      border: '1px solid var(--p-border)',
      borderRadius: 999,
      padding: '3px 8px 3px 10px',
      fontSize: 11,
    }}>
      <span style={{ fontFamily: 'monospace', color: 'var(--p-text)' }}>{moduleKey}</span>
      {s && (
        <span style={{
          background: s.bg,
          color: s.color,
          padding: '1px 6px',
          borderRadius: 3,
          fontSize: 9,
          fontWeight: 700,
          letterSpacing: '0.04em',
        }}>
          {s.label}
        </span>
      )}
    </span>
  )
}

function SystemBadge() {
  return (
    <span style={{
      background: 'rgba(192,38,211,0.15)',
      color: 'var(--p-magenta)',
      padding: '2px 8px',
      borderRadius: 4,
      fontSize: '0.65rem',
      fontWeight: 700,
      textTransform: 'uppercase',
      letterSpacing: '0.06em',
      whiteSpace: 'nowrap',
    }}>
      SYSTEM
    </span>
  )
}

// ── Page ────────────────────────────────────────────────────────────────────
export function PlatformPresets() {
  // Data
  const [presets, setPresets] = useState<IndustryPreset[]>([])
  const [catalog, setCatalog] = useState<Module[]>([])
  const [orgs, setOrgs] = useState<PlatformOrg[]>([])
  const [loading, setLoading] = useState(true)

  // Filters
  const [search, setSearch] = useState('')
  const [filterIndustry, setFilterIndustry] = useState<string>('')
  const [onlySystem, setOnlySystem] = useState(false)

  // Drawer (create/edit/duplicate)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [editing, setEditing] = useState<IndustryPreset | null>(null)
  const [form, setForm] = useState<PresetFormState>(EMPTY_FORM)
  const [saving, setSaving] = useState(false)
  const [moduleSearch, setModuleSearch] = useState('')

  // System edit warning (typed-name)
  const [systemEditTarget, setSystemEditTarget] = useState<IndustryPreset | null>(null)

  // Delete (typed-name)
  const [delTarget, setDelTarget] = useState<IndustryPreset | null>(null)
  const [deleting, setDeleting] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const [p, c, o] = await Promise.all([
        platformApi.getPresets(),
        platformApi.getModulesCatalog(),
        platformApi.getOrgs({ include_archived: true }),
      ])
      setPresets(p)
      setCatalog(c)
      setOrgs(o)
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'No se pudieron cargar los presets')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  // ── Derived ───────────────────────────────────────────────────────────────
  const moduleByKey = useMemo(() => {
    const map: Record<string, Module> = {}
    catalog.forEach(m => { map[m.key] = m })
    return map
  }, [catalog])

  const orgsByIndustry = useMemo(() => {
    const map: Record<string, PlatformOrg[]> = {}
    orgs.forEach(o => {
      if (!o.industry_type) return
      if (!map[o.industry_type]) map[o.industry_type] = []
      map[o.industry_type].push(o)
    })
    return map
  }, [orgs])

  const industries = useMemo(
    () => Array.from(new Set(presets.map(p => p.industry_type))).sort(),
    [presets]
  )

  // ── KPIs ──────────────────────────────────────────────────────────────────
  const kpis = useMemo(() => {
    const total = presets.length
    const systemCount = presets.filter(p => p.is_system).length
    const orgsAssigned = orgs.filter(o => !!o.industry_type).length
    const moduleKeys = new Set(presets.flatMap(p => p.modules))
    return {
      total,
      systemCount,
      orgsAssigned,
      modulesUsed: moduleKeys.size,
    }
  }, [presets, orgs])

  // ── Filtered presets ──────────────────────────────────────────────────────
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    return presets.filter(p => {
      if (onlySystem && !p.is_system) return false
      if (filterIndustry && p.industry_type !== filterIndustry) return false
      if (q) {
        const hay = `${p.display_name} ${p.industry_type} ${p.description || ''}`.toLowerCase()
        if (!hay.includes(q)) return false
      }
      return true
    })
  }, [presets, search, filterIndustry, onlySystem])

  // ── Drawer handlers ───────────────────────────────────────────────────────
  const openCreate = () => {
    setEditing(null)
    setForm(EMPTY_FORM)
    setModuleSearch('')
    setDrawerOpen(true)
  }

  const openEdit = (p: IndustryPreset) => {
    if (p.is_system) {
      // Show typed-name warning before allowing edit
      setSystemEditTarget(p)
      return
    }
    setEditing(p)
    setForm({
      industry_type: p.industry_type,
      display_name: p.display_name,
      description: p.description || '',
      modules: [...p.modules],
    })
    setModuleSearch('')
    setDrawerOpen(true)
  }

  const openDuplicate = (p: IndustryPreset) => {
    setEditing(null) // create mode
    setForm({
      industry_type: '', // forzar elección
      display_name: `${p.display_name} (copia)`,
      description: p.description || '',
      modules: [...p.modules],
    })
    setModuleSearch('')
    setDrawerOpen(true)
  }

  const confirmSystemEdit = () => {
    if (!systemEditTarget) return
    const p = systemEditTarget
    setSystemEditTarget(null)
    setEditing(p)
    setForm({
      industry_type: p.industry_type,
      display_name: p.display_name,
      description: p.description || '',
      modules: [...p.modules],
    })
    setModuleSearch('')
    setDrawerOpen(true)
  }

  const closeDrawer = () => {
    setDrawerOpen(false)
    setEditing(null)
  }

  const toggleModule = (key: string) => {
    setForm(f => ({
      ...f,
      modules: f.modules.includes(key) ? f.modules.filter(x => x !== key) : [...f.modules, key],
    }))
  }

  const handleSave = async () => {
    if (!form.display_name.trim()) {
      toast.error('El nombre es requerido')
      return
    }
    if (!form.industry_type.trim()) {
      toast.error('El industry_type es requerido')
      return
    }
    setSaving(true)
    try {
      if (editing) {
        await platformApi.updatePreset(editing.id, form)
        toast.success(`Preset "${form.display_name}" actualizado`)
      } else {
        await platformApi.createPreset(form)
        toast.success(`Preset "${form.display_name}" creado`)
      }
      closeDrawer()
      load()
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'No se pudo guardar el preset')
    } finally {
      setSaving(false)
    }
  }

  // ── Delete ────────────────────────────────────────────────────────────────
  const askDelete = (p: IndustryPreset) => {
    if (p.is_system) {
      toast.error('Los system presets no se pueden eliminar')
      return
    }
    setDelTarget(p)
  }

  const handleDelete = async () => {
    if (!delTarget) return
    setDeleting(true)
    try {
      await platformApi.deletePreset(delTarget.id)
      toast.success(`Preset "${delTarget.display_name}" eliminado`)
      setDelTarget(null)
      load()
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'No se pudo eliminar el preset')
    } finally {
      setDeleting(false)
    }
  }

  // ── Module catalog filter (drawer) ────────────────────────────────────────
  const filteredCatalog = useMemo(() => {
    const q = moduleSearch.trim().toLowerCase()
    if (!q) return catalog
    return catalog.filter(m =>
      m.key.toLowerCase().includes(q) ||
      (m.name || '').toLowerCase().includes(q)
    )
  }, [catalog, moduleSearch])

  // ── Header + KPI strip ────────────────────────────────────────────────────
  const headerActions = (
    <button onClick={openCreate} style={buttonPrimary}>
      <i className="fa-solid fa-plus" /> Nuevo preset
    </button>
  )

  const kpiStrip = (
    <>
      <KPICard label="Total presets" value={kpis.total} accent="teal" icon="fa-layer-group" />
      <KPICard label="System presets" value={kpis.systemCount} accent="magenta" icon="fa-shield-halved" />
      <KPICard label="Orgs con industria" value={kpis.orgsAssigned} accent="cyan" icon="fa-building" />
      <KPICard label="Módulos referenciados" value={kpis.modulesUsed} accent="purple" icon="fa-cubes" />
    </>
  )

  // ── Affected orgs for system edit warning ─────────────────────────────────
  const affectedOrgs = systemEditTarget
    ? (orgsByIndustry[systemEditTarget.industry_type] || [])
    : []

  return (
    <PlatformPageShell
      breadcrumb="Platform / Presets"
      title="Industry Presets"
      actions={headerActions}
      kpis={kpiStrip}
    >
      {/* Toolbar */}
      <div style={{
        display: 'flex',
        gap: 12,
        alignItems: 'center',
        flexWrap: 'wrap',
        background: 'var(--p-surface)',
        border: '1px solid var(--p-border)',
        borderRadius: 6,
        padding: 12,
      }}>
        <div style={{ flex: '1 1 240px', minWidth: 200 }}>
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Buscar por nombre o industria..."
            style={{ ...inputStyle, padding: '6px 10px' }}
          />
        </div>

        <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
          <span style={{ fontSize: 11, color: 'var(--p-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            Industria:
          </span>
          <select
            value={filterIndustry}
            onChange={e => setFilterIndustry(e.target.value)}
            style={{
              background: 'var(--p-surface-2)',
              border: '1px solid var(--p-border)',
              color: 'var(--p-text)',
              padding: '6px 8px',
              borderRadius: 4,
              fontSize: 12,
            }}
          >
            <option value="">Todas</option>
            {industries.map(i => <option key={i} value={i}>{i}</option>)}
          </select>
        </div>

        <label style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          fontSize: 12,
          color: 'var(--p-text)',
          cursor: 'pointer',
          background: onlySystem ? 'rgba(192,38,211,0.12)' : 'var(--p-surface-2)',
          border: `1px solid ${onlySystem ? 'var(--p-magenta)' : 'var(--p-border)'}`,
          padding: '5px 10px',
          borderRadius: 4,
          fontWeight: 600,
        }}>
          <input
            type="checkbox"
            checked={onlySystem}
            onChange={e => setOnlySystem(e.target.checked)}
            style={{ margin: 0 }}
          />
          Solo system
        </label>

        <span style={{ fontSize: 11, color: 'var(--p-muted)', marginLeft: 'auto' }}>
          {filtered.length} / {presets.length}
        </span>
      </div>

      {/* Cards */}
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
          <p style={{ marginTop: 12, fontSize: 13 }}>Cargando presets...</p>
        </div>
      ) : (
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))',
          gap: 12,
        }}>
          {filtered.map(p => {
            const orgsUsing = orgsByIndustry[p.industry_type] || []
            return (
              <div
                key={p.id}
                style={{
                  background: 'var(--p-surface)',
                  border: '1px solid var(--p-border)',
                  borderRadius: 6,
                  padding: 16,
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 12,
                }}
              >
                {/* Header */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                      <h3 style={{
                        margin: 0,
                        fontSize: '0.95rem',
                        fontWeight: 700,
                        color: 'var(--p-text)',
                      }}>
                        {p.display_name}
                      </h3>
                      {p.is_system && <SystemBadge />}
                    </div>
                    {p.description && (
                      <p style={{
                        margin: '6px 0 0',
                        fontSize: 12,
                        color: 'var(--p-muted)',
                        lineHeight: 1.4,
                      }}>
                        {p.description}
                      </p>
                    )}
                  </div>
                </div>

                {/* Industry chip + orgs-using */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                  <span style={{
                    background: 'rgba(0,229,255,0.10)',
                    color: 'var(--p-cyan)',
                    border: '1px solid rgba(0,229,255,0.25)',
                    padding: '3px 10px',
                    borderRadius: 4,
                    fontSize: 11,
                    fontFamily: 'monospace',
                    fontWeight: 600,
                  }}>
                    {p.industry_type}
                  </span>
                  <span
                    title={orgsUsing.map(o => o.name).join(', ') || 'Sin orgs asignadas'}
                    style={{
                      background: orgsUsing.length > 0 ? 'rgba(0,201,177,0.10)' : 'var(--p-surface-2)',
                      color: orgsUsing.length > 0 ? 'var(--p-teal)' : 'var(--p-muted)',
                      border: `1px solid ${orgsUsing.length > 0 ? 'rgba(0,201,177,0.25)' : 'var(--p-border)'}`,
                      padding: '3px 10px',
                      borderRadius: 4,
                      fontSize: 11,
                      fontWeight: 600,
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: 6,
                    }}
                  >
                    <i className="fa-solid fa-building" style={{ fontSize: 10 }} />
                    {orgsUsing.length} org{orgsUsing.length === 1 ? '' : 's'}
                  </span>
                </div>

                {/* Modules pills */}
                <div>
                  <p style={{
                    margin: '0 0 6px',
                    fontSize: 10,
                    color: 'var(--p-muted)',
                    textTransform: 'uppercase',
                    letterSpacing: '0.08em',
                    fontWeight: 600,
                  }}>
                    Módulos ({p.modules.length})
                  </p>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                    {p.modules.length === 0 && (
                      <span style={{ fontSize: 11, color: 'var(--p-muted)', fontStyle: 'italic' }}>
                        Sin módulos
                      </span>
                    )}
                    {p.modules.map(k => (
                      <ModulePill key={k} moduleKey={k} status={moduleByKey[k]?.status} />
                    ))}
                  </div>
                </div>

                {/* Footer actions */}
                <div style={{
                  display: 'flex',
                  gap: 8,
                  justifyContent: 'flex-end',
                  borderTop: '1px solid var(--p-border)',
                  paddingTop: 10,
                  marginTop: 'auto',
                }}>
                  <button onClick={() => openEdit(p)} style={buttonSecondary}>
                    <i className="fa-solid fa-pen" style={{ marginRight: 6 }} />
                    Editar
                  </button>
                  <button onClick={() => openDuplicate(p)} style={buttonSecondary}>
                    <i className="fa-solid fa-clone" style={{ marginRight: 6 }} />
                    Duplicar
                  </button>
                  <button
                    onClick={() => askDelete(p)}
                    style={p.is_system ? { ...buttonDanger, opacity: 0.5, cursor: 'not-allowed' } : buttonDanger}
                    title={p.is_system ? 'Los system presets no se pueden eliminar' : 'Eliminar preset'}
                  >
                    <i className="fa-solid fa-trash" />
                  </button>
                </div>
              </div>
            )
          })}

          {filtered.length === 0 && (
            <div style={{
              gridColumn: '1 / -1',
              background: 'var(--p-surface)',
              border: '1px solid var(--p-border)',
              borderRadius: 6,
              padding: '3rem',
              textAlign: 'center',
              color: 'var(--p-muted)',
              fontSize: 13,
            }}>
              {presets.length === 0 ? 'Sin presets registrados' : 'Sin resultados con los filtros aplicados'}
            </div>
          )}
        </div>
      )}

      {/* Create / Edit / Duplicate drawer */}
      <SideDrawer
        open={drawerOpen}
        title={editing ? `Editar ${editing.display_name}` : 'Nuevo preset'}
        onClose={closeDrawer}
        onSave={handleSave}
        saving={saving}
        saveLabel={editing ? 'Guardar' : 'Crear'}
        width={520}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div>
            <label style={labelStyle}>Display name *</label>
            <input
              value={form.display_name}
              onChange={e => setForm({ ...form, display_name: e.target.value })}
              required
              style={inputStyle}
            />
          </div>

          <div>
            <label style={labelStyle}>Industry type *</label>
            <input
              value={form.industry_type}
              onChange={e => setForm({ ...form, industry_type: e.target.value.toUpperCase() })}
              placeholder="Ej. ATLASPOS, RESTAURANT, CLINIC..."
              required
              style={{ ...inputStyle, fontFamily: 'monospace' }}
            />
            <p style={{ fontSize: 10, color: 'var(--p-muted)', margin: '4px 0 0' }}>
              Identificador único en MAYÚSCULAS. Las orgs lo referencian por este valor.
            </p>
          </div>

          <div>
            <label style={labelStyle}>Descripción</label>
            <textarea
              value={form.description}
              onChange={e => setForm({ ...form, description: e.target.value })}
              rows={2}
              style={{ ...inputStyle, resize: 'vertical', fontFamily: 'inherit' }}
            />
          </div>

          {/* Module multi-select */}
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
              <label style={{ ...labelStyle, marginBottom: 0 }}>
                Módulos ({form.modules.length} / {catalog.length})
              </label>
              <div style={{ display: 'flex', gap: 4 }}>
                <button
                  type="button"
                  onClick={() => setForm(f => ({ ...f, modules: catalog.map(m => m.key) }))}
                  style={{
                    background: 'transparent',
                    border: '1px solid var(--p-border)',
                    color: 'var(--p-muted)',
                    fontSize: 10,
                    padding: '3px 8px',
                    borderRadius: 4,
                    cursor: 'pointer',
                    fontWeight: 600,
                  }}
                >
                  Todos
                </button>
                <button
                  type="button"
                  onClick={() => setForm(f => ({ ...f, modules: [] }))}
                  style={{
                    background: 'transparent',
                    border: '1px solid var(--p-border)',
                    color: 'var(--p-muted)',
                    fontSize: 10,
                    padding: '3px 8px',
                    borderRadius: 4,
                    cursor: 'pointer',
                    fontWeight: 600,
                  }}
                >
                  Ninguno
                </button>
              </div>
            </div>

            <input
              value={moduleSearch}
              onChange={e => setModuleSearch(e.target.value)}
              placeholder="Buscar módulo..."
              style={{ ...inputStyle, padding: '6px 10px', marginBottom: 6 }}
            />

            <div style={{
              maxHeight: 280,
              overflowY: 'auto',
              border: '1px solid var(--p-border)',
              borderRadius: 4,
              background: 'var(--p-bg)',
            }}>
              {filteredCatalog.length === 0 && (
                <p style={{ padding: 12, fontSize: 12, color: 'var(--p-muted)', margin: 0, textAlign: 'center' }}>
                  Sin módulos
                </p>
              )}
              {filteredCatalog.map(m => {
                const checked = form.modules.includes(m.key)
                const isBeta = m.status === 'BETA'
                return (
                  <label
                    key={m.key}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 10,
                      padding: '8px 10px',
                      cursor: 'pointer',
                      borderBottom: '1px solid var(--p-border)',
                      background: checked ? 'rgba(0,201,177,0.06)' : 'transparent',
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggleModule(m.key)}
                      style={{ margin: 0, flexShrink: 0 }}
                    />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                        <span style={{ fontFamily: 'monospace', fontSize: 12, color: 'var(--p-text)', fontWeight: 600 }}>
                          {m.key}
                        </span>
                        <span style={{
                          background: isBeta ? 'rgba(245,158,11,0.18)' : 'rgba(34,197,94,0.15)',
                          color: isBeta ? 'var(--p-warning)' : 'var(--p-success)',
                          padding: '1px 6px',
                          borderRadius: 3,
                          fontSize: 9,
                          fontWeight: 700,
                          letterSpacing: '0.04em',
                        }}>
                          {m.status}
                        </span>
                      </div>
                      {(m.name || m.description) && (
                        <p style={{ margin: '2px 0 0', fontSize: 11, color: 'var(--p-muted)', lineHeight: 1.3 }}>
                          {m.name || m.description}
                        </p>
                      )}
                    </div>
                  </label>
                )
              })}
            </div>
          </div>

          {/* Live preview */}
          <div style={{
            background: 'var(--p-bg)',
            border: '1px solid var(--p-border)',
            borderRadius: 4,
            padding: 12,
          }}>
            <p style={{
              margin: '0 0 8px',
              fontSize: 10,
              color: 'var(--p-muted)',
              textTransform: 'uppercase',
              letterSpacing: '0.08em',
              fontWeight: 600,
            }}>
              Preview — {form.modules.length} módulo(s) seleccionado(s)
            </p>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {form.modules.length === 0 && (
                <span style={{ fontSize: 11, color: 'var(--p-hint)', fontStyle: 'italic' }}>
                  Sin módulos seleccionados
                </span>
              )}
              {form.modules.map(k => (
                <ModulePill key={k} moduleKey={k} status={moduleByKey[k]?.status} />
              ))}
            </div>
          </div>
        </div>
      </SideDrawer>

      {/* System edit warning — typed-name + affected orgs list */}
      {systemEditTarget && (
        <div
          onClick={() => setSystemEditTarget(null)}
          style={{
            position: 'fixed', inset: 0,
            background: 'rgba(0,0,0,0.7)',
            zIndex: 1100,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}
        >
          <div
            onClick={e => e.stopPropagation()}
            style={{
              background: 'var(--p-surface)',
              border: '1px solid var(--p-magenta)',
              borderRadius: 6,
              padding: 20,
              width: 480,
              maxWidth: '90vw',
              maxHeight: '85vh',
              display: 'flex',
              flexDirection: 'column',
            }}
          >
            <h3 style={{ margin: 0, color: 'var(--p-text)', fontSize: '1rem', fontWeight: 700 }}>
              <i className="fa-solid fa-shield-halved" style={{ color: 'var(--p-magenta)', marginRight: 8 }} />
              Editar system preset
            </h3>
            <p style={{ color: 'var(--p-muted)', fontSize: '0.85rem', margin: '8px 0 12px' }}>
              <strong style={{ color: 'var(--p-text)' }}>{systemEditTarget.display_name}</strong> es un preset del sistema.
              Cambiarlo afecta a todas las organizaciones que comparten su industry_type.
            </p>

            <div style={{
              padding: 12,
              background: 'var(--p-surface-2)',
              border: '1px solid var(--p-border)',
              borderRadius: 4,
              marginBottom: 14,
              flex: 1,
              minHeight: 60,
              maxHeight: 200,
              overflowY: 'auto',
            }}>
              <p style={{
                margin: '0 0 8px',
                fontSize: 10,
                color: 'var(--p-muted)',
                textTransform: 'uppercase',
                letterSpacing: '0.08em',
                fontWeight: 600,
              }}>
                Orgs afectadas: {affectedOrgs.length}
              </p>
              {affectedOrgs.length === 0 ? (
                <p style={{ margin: 0, fontSize: 12, color: 'var(--p-hint)', fontStyle: 'italic' }}>
                  Ninguna organización usa este industry_type todavía.
                </p>
              ) : (
                <ul style={{ margin: 0, padding: 0, listStyle: 'none' }}>
                  {affectedOrgs.map(o => (
                    <li
                      key={o.id}
                      style={{
                        fontSize: 12,
                        color: 'var(--p-text)',
                        padding: '4px 0',
                        borderBottom: '1px solid var(--p-border)',
                      }}
                    >
                      <i className="fa-solid fa-building" style={{ color: 'var(--p-cyan)', marginRight: 8, fontSize: 10 }} />
                      {o.name}
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <ConfirmInline
              resourceName={systemEditTarget.display_name}
              onCancel={() => setSystemEditTarget(null)}
              onConfirm={confirmSystemEdit}
            />
          </div>
        </div>
      )}

      {/* Delete confirm */}
      <ConfirmModal
        open={!!delTarget}
        title={`Eliminar ${delTarget?.display_name ?? ''}`}
        message="Esta acción es permanente. Las orgs que usen este industry_type quedarán sin preset asociado (no se reasigna automáticamente)."
        resourceName={delTarget?.display_name ?? ''}
        destructive
        busy={deleting}
        onClose={() => setDelTarget(null)}
        onConfirm={handleDelete}
      />
    </PlatformPageShell>
  )
}

// ── Inline typed-name confirm (for system edit warning) ─────────────────────
function ConfirmInline({
  resourceName,
  onCancel,
  onConfirm,
}: {
  resourceName: string
  onCancel: () => void
  onConfirm: () => void
}) {
  const [typed, setTyped] = useState('')
  const ok = typed === resourceName

  return (
    <div>
      <p style={{ color: 'var(--p-text)', fontSize: '0.8rem', marginBottom: 6 }}>
        Para continuar, escribe <code style={{ color: 'var(--p-magenta)', fontWeight: 700 }}>{resourceName}</code>:
      </p>
      <input
        value={typed}
        onChange={e => setTyped(e.target.value)}
        autoFocus
        style={{
          width: '100%',
          background: 'var(--p-surface-2)',
          color: 'var(--p-text)',
          border: '1px solid var(--p-border)',
          padding: '6px 10px',
          borderRadius: 4,
          fontSize: 13,
          marginBottom: 12,
          boxSizing: 'border-box',
        }}
      />
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
        <button
          onClick={onCancel}
          style={{
            background: 'var(--p-surface-2)',
            color: 'var(--p-text)',
            border: '1px solid var(--p-border)',
            padding: '6px 14px',
            borderRadius: 4,
            cursor: 'pointer',
            fontSize: 12,
            fontWeight: 600,
          }}
        >
          Cancelar
        </button>
        <button
          onClick={onConfirm}
          disabled={!ok}
          style={{
            background: 'var(--p-magenta)',
            color: '#fff',
            fontWeight: 700,
            border: 'none',
            padding: '6px 16px',
            borderRadius: 4,
            cursor: ok ? 'pointer' : 'not-allowed',
            opacity: ok ? 1 : 0.4,
            fontSize: 12,
          }}
        >
          Continuar al editor
        </button>
      </div>
    </div>
  )
}
