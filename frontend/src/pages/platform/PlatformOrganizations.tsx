import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { platformApi, PlatformOrg, OrgDependencies, IndustryPreset } from '../../api/platform'
import { toast } from '../../store/toastStore'
import { PlatformPageShell } from '../../components/platform/PlatformPageShell'
import { KPICard } from '../../components/platform/KPICard'
import { DataTable, DataTableColumn } from '../../components/platform/DataTable'
import { StatusBadge } from '../../components/platform/StatusBadge'
import { SideDrawer } from '../../components/platform/SideDrawer'
import { ConfirmModal } from '../../components/platform/ConfirmModal'
import { PlatformOrgWizard } from '../../components/platform/PlatformOrgWizard'

type OrgFormState = {
  name: string; legal_name: string; tax_id: string; tax_regime: string
  email: string; phone: string; address: string; website: string
  logo_url: string; timezone: string
  ticket_header: string; ticket_footer: string; printer_name: string
  industry_type: string
}

const EMPTY_FORM: OrgFormState = {
  name: '', legal_name: '', tax_id: '', tax_regime: '',
  email: '', phone: '', address: '', website: '',
  logo_url: '', timezone: 'America/Mexico_City',
  ticket_header: '', ticket_footer: '', printer_name: '',
  industry_type: 'ATLAS_POS',
}

function orgToForm(o: PlatformOrg): OrgFormState {
  return {
    name: o.name || '',
    legal_name: o.legal_name || '',
    tax_id: o.tax_id || '',
    tax_regime: o.tax_regime || '',
    email: o.email || '',
    phone: o.phone || '',
    address: o.address || '',
    website: o.website || '',
    logo_url: o.logo_url || '',
    timezone: o.timezone || 'America/Mexico_City',
    ticket_header: o.ticket_header || '',
    ticket_footer: o.ticket_footer || '',
    printer_name: o.printer_name || '',
    industry_type: (o.industry_type as string) || 'ATLAS_POS',
  }
}

type StatusFilter = 'all' | 'active' | 'archived'

// ── Inline shared styles (tokens) ────────────────────────────────────────────
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

// ── Row actions menu ────────────────────────────────────────────────────────
function RowMenu({
  org,
  onView,
  onEdit,
  onBootstrap,
  onExport,
  onArchive,
  onUnarchive,
  onDelete,
}: {
  org: PlatformOrg
  onView: () => void
  onEdit: () => void
  onBootstrap: () => void
  onExport: () => void
  onArchive: () => void
  onUnarchive: () => void
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
  }
  const dangerStyle: React.CSSProperties = { ...itemStyle, color: 'var(--p-danger)' }

  return (
    <div ref={ref} style={{ position: 'relative', display: 'inline-block' }}>
      <button
        onClick={() => setOpen(o => !o)}
        aria-label={`Acciones ${org.name}`}
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
        <div style={{
          position: 'absolute',
          right: 0,
          top: 32,
          minWidth: 200,
          background: 'var(--p-surface)',
          border: '1px solid var(--p-border)',
          borderRadius: 4,
          boxShadow: '0 4px 16px rgba(0,0,0,0.4)',
          zIndex: 50,
        }}>
          <button style={itemStyle} onClick={() => { setOpen(false); onView() }}>
            <i className="fa-solid fa-eye" style={{ marginRight: 8, width: 12 }} /> Ver detalle
          </button>
          <button style={itemStyle} onClick={() => { setOpen(false); onEdit() }}>
            <i className="fa-solid fa-pen" style={{ marginRight: 8, width: 12 }} /> Editar
          </button>
          <button style={itemStyle} onClick={() => { setOpen(false); onBootstrap() }}>
            <i className="fa-solid fa-wand-magic-sparkles" style={{ marginRight: 8, width: 12 }} /> Bootstrap
          </button>
          <button style={itemStyle} onClick={() => { setOpen(false); onExport() }}>
            <i className="fa-solid fa-file-export" style={{ marginRight: 8, width: 12 }} /> Exportar JSON
          </button>
          <div style={{ borderTop: '1px solid var(--p-border)' }} />
          {org.is_active ? (
            <button style={itemStyle} onClick={() => { setOpen(false); onArchive() }}>
              <i className="fa-solid fa-box-archive" style={{ marginRight: 8, width: 12 }} /> Archivar
            </button>
          ) : (
            <button style={itemStyle} onClick={() => { setOpen(false); onUnarchive() }}>
              <i className="fa-solid fa-rotate-left" style={{ marginRight: 8, width: 12 }} /> Desarchivar
            </button>
          )}
          <button style={dangerStyle} onClick={() => { setOpen(false); onDelete() }}>
            <i className="fa-solid fa-trash" style={{ marginRight: 8, width: 12 }} /> Eliminar
          </button>
        </div>
      )}
    </div>
  )
}

// ── Page ────────────────────────────────────────────────────────────────────
export function PlatformOrganizations() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()

  // Wizard (B1 · Sprint 0): opened via CommandPalette "?new=1" query param.
  const wizardOpen = searchParams.get('new') === '1'
  const closeWizard = () => {
    const next = new URLSearchParams(searchParams)
    next.delete('new')
    setSearchParams(next, { replace: true })
  }

  // Data
  const [orgs, setOrgs] = useState<PlatformOrg[]>([])
  const [loading, setLoading] = useState(true)

  // Filters
  const [showArchived, setShowArchived] = useState(false)
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const [industryFilter, setIndustryFilter] = useState<string[]>([])
  const [dateStart, setDateStart] = useState('')
  const [dateEnd, setDateEnd] = useState('')

  // Drawer (create/edit)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [editingOrg, setEditingOrg] = useState<PlatformOrg | null>(null)
  const [form, setForm] = useState<OrgFormState>(EMPTY_FORM)
  const [saving, setSaving] = useState(false)
  const [presets, setPresets] = useState<IndustryPreset[]>([])

  // Archive / bootstrap / export busy markers
  const [archivingId, setArchivingId] = useState<number | null>(null)
  const [exportingId, setExportingId] = useState<number | null>(null)
  const [bootstrapTarget, setBootstrapTarget] = useState<PlatformOrg | null>(null)
  const [bootstrapping, setBootstrapping] = useState(false)

  // Delete (typed-name confirm)
  const [delTarget, setDelTarget] = useState<PlatformOrg | null>(null)
  const [delDeps, setDelDeps] = useState<OrgDependencies | null>(null)
  const [deleting, setDeleting] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const data = await platformApi.getOrgs({ include_archived: showArchived })
      setOrgs(data)
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'No se pudieron cargar las organizaciones')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [showArchived])

  // ── KPIs ─────────────────────────────────────────────────────────────────
  const kpis = useMemo(() => {
    const total = orgs.length
    const activas = orgs.filter(o => o.is_active && o.status === 'ACTIVE').length
    const archivadas = orgs.filter(o => !o.is_active).length
    const monthStart = new Date()
    monthStart.setDate(1)
    monthStart.setHours(0, 0, 0, 0)
    const nuevas = orgs.filter(o => {
      const d = new Date(o.created_at)
      return !isNaN(d.getTime()) && d >= monthStart
    }).length
    return { total, activas, archivadas, nuevas }
  }, [orgs])

  // ── Industry options ────────────────────────────────────────────────────
  const industryOptions = useMemo(() => {
    const set = new Set<string>()
    orgs.forEach(o => { if (o.industry_type) set.add(o.industry_type) })
    return Array.from(set).sort()
  }, [orgs])

  // ── Filtered rows ────────────────────────────────────────────────────────
  const filtered = useMemo(() => {
    return orgs.filter(o => {
      // Status filter
      if (statusFilter === 'active' && !(o.is_active && o.status === 'ACTIVE')) return false
      if (statusFilter === 'archived' && o.is_active) return false

      // Industry filter
      if (industryFilter.length > 0 && !industryFilter.includes(o.industry_type || '')) return false

      // Date range
      if (dateStart || dateEnd) {
        const d = new Date(o.created_at)
        if (isNaN(d.getTime())) return false
        if (dateStart) {
          const s = new Date(dateStart)
          s.setHours(0, 0, 0, 0)
          if (d < s) return false
        }
        if (dateEnd) {
          const e = new Date(dateEnd)
          e.setHours(23, 59, 59, 999)
          if (d > e) return false
        }
      }

      return true
    })
  }, [orgs, statusFilter, industryFilter, dateStart, dateEnd])

  // ── Drawer handlers ──────────────────────────────────────────────────────
  const openCreate = () => {
    setEditingOrg(null)
    setForm(EMPTY_FORM)
    setDrawerOpen(true)
    platformApi.getPresets()
      .then(setPresets)
      .catch(() => setPresets([]))
  }

  const openEdit = (org: PlatformOrg) => {
    setEditingOrg(org)
    setForm(orgToForm(org))
    setDrawerOpen(true)
  }

  const closeDrawer = () => {
    setDrawerOpen(false)
    setEditingOrg(null)
  }

  const handleSave = async () => {
    if (!form.name.trim()) {
      toast.error('El nombre es requerido')
      return
    }
    setSaving(true)
    try {
      if (editingOrg) {
        await platformApi.updateOrg(editingOrg.id, form)
        toast.success(`Organización "${form.name}" actualizada`)
      } else {
        await platformApi.createOrg(form)
        toast.success(`Organización "${form.name}" creada`)
      }
      closeDrawer()
      load()
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'No se pudo guardar la organización')
    } finally {
      setSaving(false)
    }
  }

  // ── Archive / unarchive ──────────────────────────────────────────────────
  const handleArchive = async (o: PlatformOrg) => {
    if (!confirm(`¿Archivar "${o.name}"? Quedará oculta por default y se puede restaurar.`)) return
    setArchivingId(o.id)
    try {
      await platformApi.archiveOrg(o.id)
      toast.success(`"${o.name}" archivada`)
      load()
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'No se pudo archivar')
    } finally {
      setArchivingId(null)
    }
  }

  const handleUnarchive = async (o: PlatformOrg) => {
    if (!confirm(`¿Desarchivar "${o.name}"?`)) return
    setArchivingId(o.id)
    try {
      await platformApi.unarchiveOrg(o.id)
      toast.success(`"${o.name}" restaurada`)
      load()
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'No se pudo restaurar')
    } finally {
      setArchivingId(null)
    }
  }

  // ── Export JSON (preserved) ─────────────────────────────────────────────
  const handleExport = async (o: PlatformOrg) => {
    setExportingId(o.id)
    try {
      const payload = await platformApi.exportOrg(o.id)
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `org-${o.id}-${o.name.replace(/\W+/g, '_')}-export.json`
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
      toast.success('Export descargado (incluye clientes únicamente)')
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'No se pudo exportar')
    } finally {
      setExportingId(null)
    }
  }

  // ── Bootstrap (preserved) ───────────────────────────────────────────────
  const handleBootstrap = async () => {
    if (!bootstrapTarget) return
    setBootstrapping(true)
    try {
      const res = await platformApi.bootstrapOrg(bootstrapTarget.id)
      toast.success(res?.message || 'Bootstrap completado')
      setBootstrapTarget(null)
      load()
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Bootstrap falló')
    } finally {
      setBootstrapping(false)
    }
  }

  // ── Delete with deps ─────────────────────────────────────────────────────
  const openDelete = async (org: PlatformOrg) => {
    setDelTarget(org)
    setDelDeps(null)
    try {
      setDelDeps(await platformApi.getOrgDependencies(org.id))
    } catch {
      // backend will still protect on delete
    }
  }

  const closeDelete = () => {
    setDelTarget(null)
    setDelDeps(null)
  }

  const handleDelete = async () => {
    if (!delTarget) return
    setDeleting(true)
    try {
      await platformApi.deleteOrg(delTarget.id)
      toast.success(`Organización "${delTarget.name}" eliminada`)
      closeDelete()
      load()
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Fallo al eliminar')
    } finally {
      setDeleting(false)
    }
  }

  const depsBlock = (delDeps?.branches ?? 0) + (delDeps?.users ?? 0) > 0

  // ── Table columns ────────────────────────────────────────────────────────
  const columns: DataTableColumn<PlatformOrg>[] = [
    {
      key: 'name',
      label: 'Nombre',
      sortable: true,
      sortValue: o => o.name.toLowerCase(),
      accessor: o => (
        <div>
          <div style={{ fontWeight: 600, color: 'var(--p-text)' }}>{o.name}</div>
          <div style={{ fontSize: 11, color: 'var(--p-muted)', fontFamily: 'monospace' }}>#{o.id}</div>
        </div>
      ),
    },
    {
      key: 'industry',
      label: 'Industry',
      sortable: true,
      sortValue: o => o.industry_type || '',
      accessor: o => (
        <span style={{
          background: 'rgba(123,47,190,0.12)',
          color: 'var(--p-purple)',
          padding: '2px 8px',
          borderRadius: 4,
          fontSize: 11,
          fontFamily: 'monospace',
          fontWeight: 600,
        }}>
          {o.industry_type || '—'}
        </span>
      ),
    },
    {
      key: 'modules',
      label: 'Módulos',
      accessor: () => <span style={{ color: 'var(--p-muted)' }}>—</span>,
    },
    {
      key: 'users',
      label: 'Usuarios',
      accessor: () => <span style={{ color: 'var(--p-muted)' }}>—</span>,
    },
    {
      key: 'branches',
      label: 'Sucursales',
      accessor: () => <span style={{ color: 'var(--p-muted)' }}>—</span>,
    },
    {
      key: 'created',
      label: 'Creada',
      sortable: true,
      sortValue: o => o.created_at,
      accessor: o => {
        const d = new Date(o.created_at)
        return (
          <span style={{ color: 'var(--p-muted)', fontSize: 12 }}>
            {isNaN(d.getTime()) ? '—' : d.toLocaleDateString('es-MX', { year: 'numeric', month: 'short', day: '2-digit' })}
          </span>
        )
      },
    },
    {
      key: 'status',
      label: 'Status',
      sortable: true,
      sortValue: o => (!o.is_active ? 'archived' : o.status === 'SUSPENDED' ? 'suspended' : 'active'),
      accessor: o => {
        if (!o.is_active) return <StatusBadge status="archived" />
        if (o.status === 'SUSPENDED') return <StatusBadge status="beta" label="Suspendida" />
        return <StatusBadge status="active" />
      },
    },
    {
      key: 'actions',
      label: '',
      width: '60px',
      accessor: o => (
        <RowMenu
          org={o}
          onView={() => navigate(`/platform/organizations/${o.id}`)}
          onEdit={() => openEdit(o)}
          onBootstrap={() => setBootstrapTarget(o)}
          onExport={() => handleExport(o)}
          onArchive={() => handleArchive(o)}
          onUnarchive={() => handleUnarchive(o)}
          onDelete={() => openDelete(o)}
        />
      ),
    },
  ]

  // ── Toolbar ─────────────────────────────────────────────────────────────
  const toggleIndustry = (key: string) => {
    setIndustryFilter(prev =>
      prev.includes(key) ? prev.filter(k => k !== key) : [...prev, key]
    )
  }

  const toolbar = (
    <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
      {/* Status filter */}
      <div style={{ display: 'flex', gap: 4 }}>
        {(['all', 'active', 'archived'] as StatusFilter[]).map(s => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            style={chipStyle(statusFilter === s)}
          >
            {s === 'all' ? 'Todas' : s === 'active' ? 'Activas' : 'Archivadas'}
          </button>
        ))}
      </div>

      {/* Industry chips */}
      {industryOptions.length > 0 && (
        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', alignItems: 'center' }}>
          <span style={{ fontSize: 11, color: 'var(--p-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            Industry:
          </span>
          {industryOptions.map(ind => (
            <button
              key={ind}
              onClick={() => toggleIndustry(ind)}
              style={chipStyle(industryFilter.includes(ind))}
            >
              {ind}
            </button>
          ))}
        </div>
      )}

      {/* Date range */}
      <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
        <span style={{ fontSize: 11, color: 'var(--p-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
          Creada:
        </span>
        <input
          type="date"
          value={dateStart}
          onChange={e => setDateStart(e.target.value)}
          style={{
            background: 'var(--p-surface-2)',
            border: '1px solid var(--p-border)',
            color: 'var(--p-text)',
            padding: '4px 8px',
            borderRadius: 4,
            fontSize: 12,
          }}
        />
        <span style={{ color: 'var(--p-muted)', fontSize: 11 }}>→</span>
        <input
          type="date"
          value={dateEnd}
          onChange={e => setDateEnd(e.target.value)}
          style={{
            background: 'var(--p-surface-2)',
            border: '1px solid var(--p-border)',
            color: 'var(--p-text)',
            padding: '4px 8px',
            borderRadius: 4,
            fontSize: 12,
          }}
        />
      </div>

      {/* Mostrar archivadas (carga incluye archivadas) */}
      <button
        onClick={() => setShowArchived(s => !s)}
        style={chipStyle(showArchived)}
      >
        <i className="fa-solid fa-box-archive" style={{ marginRight: 4 }} />
        Mostrar archivadas
      </button>
    </div>
  )

  // ── Header actions ──────────────────────────────────────────────────────
  const headerActions = (
    <button onClick={openCreate} style={buttonPrimary}>
      <i className="fa-solid fa-plus" /> Nueva organización
    </button>
  )

  // ── KPI strip ───────────────────────────────────────────────────────────
  const kpiStrip = (
    <>
      <KPICard label="Total" value={kpis.total} accent="cyan" icon="fa-building" />
      <KPICard label="Activas" value={kpis.activas} accent="teal" icon="fa-circle-check" />
      <KPICard label="Archivadas" value={kpis.archivadas} accent="warning" icon="fa-box-archive" />
      <KPICard label="Nuevas este mes" value={kpis.nuevas} accent="purple" icon="fa-arrow-trend-up" />
    </>
  )

  // ── CSV row ─────────────────────────────────────────────────────────────
  const csvRow = (o: PlatformOrg) => ({
    id: o.id,
    nombre: o.name,
    legal_name: o.legal_name || '',
    industry: o.industry_type || '',
    email: o.email || '',
    phone: o.phone || '',
    status: !o.is_active ? 'ARCHIVED' : (o.status || 'ACTIVE'),
    is_active: o.is_active ? 'true' : 'false',
    created_at: o.created_at,
  })

  return (
    <PlatformPageShell
      breadcrumb="Platform / Organizaciones"
      title="Organizaciones"
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
          <p style={{ marginTop: 12, fontSize: 13 }}>Cargando organizaciones...</p>
        </div>
      ) : (
        <DataTable
          data={filtered}
          columns={columns}
          rowKey={o => o.id}
          searchable
          searchKeys={o => `${o.name} ${o.legal_name || ''} ${o.email || ''}`}
          pageSize={20}
          csvFilename="organizations.csv"
          csvRow={csvRow}
          toolbar={toolbar}
          emptyMessage={orgs.length === 0 ? 'Sin organizaciones registradas' : 'Sin resultados con los filtros aplicados'}
        />
      )}

      {/* Create / Edit drawer */}
      <SideDrawer
        open={drawerOpen}
        title={editingOrg ? `Editar ${editingOrg.name}` : 'Nueva organización'}
        onClose={closeDrawer}
        onSave={handleSave}
        saving={saving}
        saveLabel={editingOrg ? 'Guardar' : 'Crear'}
        width={520}
      >
        {!editingOrg && (
          <div style={{
            padding: 12,
            marginBottom: 16,
            borderRadius: 4,
            background: 'rgba(123,47,190,0.08)',
            border: '1px solid rgba(123,47,190,0.3)',
          }}>
            <label style={{ ...labelStyle, color: 'var(--p-purple)' }}>
              Preset de industria
            </label>
            <select
              value={form.industry_type}
              onChange={e => setForm({ ...form, industry_type: e.target.value })}
              style={{ ...inputStyle, background: 'var(--p-surface-2)' }}
            >
              {presets.length === 0 && (
                <option value="ATLAS_POS">AtlasPOS — Punto de venta de alto rendimiento</option>
              )}
              {presets.map(p => (
                <option key={p.industry_type} value={p.industry_type}>
                  {p.display_name}{p.description ? ` — ${p.description.slice(0, 60)}` : ''}
                </option>
              ))}
            </select>
            <p style={{ fontSize: 11, color: 'var(--p-muted)', margin: '6px 0 0' }}>
              Los módulos del preset se habilitarán automáticamente al crear la organización.
            </p>
          </div>
        )}

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <div style={{ gridColumn: '1 / -1' }}>
            <label style={labelStyle}>Nombre comercial *</label>
            <input
              value={form.name}
              onChange={e => setForm({ ...form, name: e.target.value })}
              required
              style={inputStyle}
            />
          </div>

          <div>
            <label style={labelStyle}>Razón social</label>
            <input value={form.legal_name} onChange={e => setForm({ ...form, legal_name: e.target.value })} style={inputStyle} />
          </div>

          <div>
            <label style={labelStyle}>RFC</label>
            <input value={form.tax_id} onChange={e => setForm({ ...form, tax_id: e.target.value })} style={inputStyle} />
          </div>

          <div>
            <label style={labelStyle}>Régimen fiscal</label>
            <input value={form.tax_regime} onChange={e => setForm({ ...form, tax_regime: e.target.value })} style={inputStyle} />
          </div>

          <div>
            <label style={labelStyle}>Email</label>
            <input type="email" value={form.email} onChange={e => setForm({ ...form, email: e.target.value })} style={inputStyle} />
          </div>

          <div>
            <label style={labelStyle}>Teléfono</label>
            <input value={form.phone} onChange={e => setForm({ ...form, phone: e.target.value })} style={inputStyle} />
          </div>

          <div>
            <label style={labelStyle}>Timezone</label>
            <input value={form.timezone} onChange={e => setForm({ ...form, timezone: e.target.value })} style={inputStyle} />
          </div>

          <div style={{ gridColumn: '1 / -1' }}>
            <label style={labelStyle}>Dirección</label>
            <input value={form.address} onChange={e => setForm({ ...form, address: e.target.value })} style={inputStyle} />
          </div>

          <div>
            <label style={labelStyle}>Website</label>
            <input type="url" value={form.website} onChange={e => setForm({ ...form, website: e.target.value })} style={inputStyle} />
          </div>

          <div>
            <label style={labelStyle}>Logo URL</label>
            <input type="url" value={form.logo_url} onChange={e => setForm({ ...form, logo_url: e.target.value })} style={inputStyle} />
          </div>

          <div style={{ gridColumn: '1 / -1' }}>
            <label style={labelStyle}>Impresora por default</label>
            <input value={form.printer_name} onChange={e => setForm({ ...form, printer_name: e.target.value })} style={inputStyle} />
          </div>

          <div style={{ gridColumn: '1 / -1' }}>
            <label style={labelStyle}>Ticket header</label>
            <input value={form.ticket_header} onChange={e => setForm({ ...form, ticket_header: e.target.value })} style={inputStyle} />
          </div>

          <div style={{ gridColumn: '1 / -1' }}>
            <label style={labelStyle}>Ticket footer</label>
            <input value={form.ticket_footer} onChange={e => setForm({ ...form, ticket_footer: e.target.value })} style={inputStyle} />
          </div>
        </div>
      </SideDrawer>

      {/* Delete confirm */}
      {delTarget && depsBlock ? (
        // Bloqueado por dependencias — modal informativo
        <div
          onClick={closeDelete}
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
              border: '1px solid var(--p-warning)',
              borderRadius: 6,
              padding: 20,
              width: 460,
              maxWidth: '90vw',
            }}
          >
            <h3 style={{ margin: 0, color: 'var(--p-text)', fontSize: '1rem', fontWeight: 700 }}>
              <i className="fa-solid fa-triangle-exclamation" style={{ color: 'var(--p-warning)', marginRight: 8 }} />
              Eliminación bloqueada
            </h3>
            <p style={{ color: 'var(--p-muted)', fontSize: '0.85rem', margin: '8px 0 12px' }}>
              <strong style={{ color: 'var(--p-text)' }}>{delTarget.name}</strong> tiene dependencias activas.
              Para eliminarla, primero debes archivarla o migrar/eliminar:
            </p>
            <ul style={{
              margin: '0 0 16px',
              padding: '12px',
              background: 'rgba(245,158,11,0.05)',
              border: '1px solid rgba(245,158,11,0.2)',
              borderRadius: 4,
              listStyle: 'none',
              color: 'var(--p-warning)',
              fontSize: 12,
            }}>
              {(delDeps?.branches ?? 0) > 0 && (
                <li><i className="fa-solid fa-circle-dot" style={{ fontSize: 6, marginRight: 8 }} /> {delDeps?.branches} sucursal(es)</li>
              )}
              {(delDeps?.users ?? 0) > 0 && (
                <li><i className="fa-solid fa-circle-dot" style={{ fontSize: 6, marginRight: 8 }} /> {delDeps?.users} usuario(s) asociado(s)</li>
              )}
            </ul>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button onClick={closeDelete} style={buttonSecondary}>Cancelar</button>
              {delTarget.is_active && (
                <button
                  onClick={() => {
                    const t = delTarget
                    closeDelete()
                    handleArchive(t)
                  }}
                  style={{
                    background: 'var(--p-warning)',
                    color: '#000',
                    fontWeight: 700,
                    border: 'none',
                    padding: '6px 16px',
                    borderRadius: 4,
                    fontSize: 12,
                    cursor: 'pointer',
                  }}
                >
                  <i className="fa-solid fa-box-archive" style={{ marginRight: 6 }} />
                  Archivar en su lugar
                </button>
              )}
            </div>
          </div>
        </div>
      ) : (
        <ConfirmModal
          open={!!delTarget}
          title={`Eliminar ${delTarget?.name ?? ''}`}
          message="Esta acción es permanente y no reversible. Se eliminará la organización y toda su configuración."
          resourceName={delTarget?.name ?? ''}
          destructive
          busy={deleting}
          onClose={closeDelete}
          onConfirm={handleDelete}
        />
      )}

      {/* Bootstrap confirm modal */}
      {bootstrapTarget && (
        <div
          onClick={() => !bootstrapping && setBootstrapTarget(null)}
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
              border: '1px solid var(--p-purple)',
              borderRadius: 6,
              padding: 20,
              width: 420,
              maxWidth: '90vw',
            }}
          >
            <h3 style={{ margin: 0, color: 'var(--p-text)', fontSize: '1rem', fontWeight: 700 }}>
              <i className="fa-solid fa-wand-magic-sparkles" style={{ color: 'var(--p-purple)', marginRight: 8 }} />
              Bootstrap {bootstrapTarget.name}
            </h3>
            <p style={{ color: 'var(--p-muted)', fontSize: '0.85rem', margin: '8px 0 16px' }}>
              Se crearán las sucursales por defecto (HQ + Store) si no existen. No afecta datos existentes.
            </p>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button
                onClick={() => setBootstrapTarget(null)}
                disabled={bootstrapping}
                style={buttonSecondary}
              >
                Cancelar
              </button>
              <button
                onClick={handleBootstrap}
                disabled={bootstrapping}
                style={{
                  background: 'var(--p-purple)',
                  color: '#fff',
                  fontWeight: 700,
                  border: 'none',
                  padding: '6px 16px',
                  borderRadius: 4,
                  fontSize: 12,
                  cursor: 'pointer',
                  opacity: bootstrapping ? 0.5 : 1,
                }}
              >
                {bootstrapping ? 'Ejecutando...' : 'Bootstrap'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Onboarding wizard (Sprint 0 · B1) — triggered by ?new=1 from CommandPalette */}
      <PlatformOrgWizard
        open={wizardOpen}
        onClose={closeWizard}
        onSuccess={(orgId) => {
          closeWizard()
          load()
          navigate(`/platform/organizations/${orgId}`)
        }}
      />

      {/* Inline busy indicator */}
      {(archivingId !== null || exportingId !== null) && (
        <div style={{
          position: 'fixed', bottom: 16, right: 16,
          background: 'var(--p-surface)', border: '1px solid var(--p-border)',
          padding: '8px 14px', borderRadius: 4, color: 'var(--p-muted)', fontSize: 12,
          zIndex: 200,
        }}>
          <i className="fa-solid fa-spinner fa-spin" style={{ marginRight: 6 }} /> Procesando...
        </div>
      )}
    </PlatformPageShell>
  )
}
