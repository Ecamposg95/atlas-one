import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { platformApi, PlatformBranch, PlatformOrg, BranchDependencies } from '../../api/platform'
import { toast } from '../../store/toastStore'
import { PlatformPageShell } from '../../components/platform/PlatformPageShell'
import { KPICard } from '../../components/platform/KPICard'
import { DataTable, DataTableColumn } from '../../components/platform/DataTable'
import { StatusBadge } from '../../components/platform/StatusBadge'
import { SideDrawer } from '../../components/platform/SideDrawer'
import { ConfirmModal } from '../../components/platform/ConfirmModal'

// ── Form state ──────────────────────────────────────────────────────────────
type BranchFormState = {
  name: string
  organization_id: string
  branch_type: string
  can_sell: boolean
  is_active: boolean
  email: string
  phone: string
  address: string
  address_line1: string
  address_line2: string
  neighborhood: string
  city: string
  state: string
  postal_code: string
  country: string
  printer_name: string
  ticket_header: string
  ticket_footer: string
  paper_width_mm: number
}

const EMPTY_FORM: BranchFormState = {
  name: '', organization_id: '', branch_type: 'STORE',
  can_sell: true, is_active: true,
  email: '', phone: '', address: '',
  address_line1: '', address_line2: '', neighborhood: '',
  city: '', state: '', postal_code: '', country: 'MX',
  printer_name: '', ticket_header: '', ticket_footer: '',
  paper_width_mm: 80,
}

function branchToForm(b: PlatformBranch, orgIdFallback?: number): BranchFormState {
  return {
    name: b.name || '',
    organization_id: String(b.organization_id ?? orgIdFallback ?? ''),
    branch_type: b.branch_type || 'STORE',
    can_sell: b.can_sell ?? true,
    is_active: b.is_active ?? true,
    email: b.email || '',
    phone: b.phone || '',
    address: b.address || '',
    address_line1: b.address_line1 || '',
    address_line2: b.address_line2 || '',
    neighborhood: b.neighborhood || '',
    city: b.city || '',
    state: b.state || '',
    postal_code: b.postal_code || '',
    country: b.country || 'MX',
    printer_name: b.printer_name || '',
    ticket_header: b.ticket_header || '',
    ticket_footer: b.ticket_footer || '',
    paper_width_mm: b.paper_width_mm ?? 80,
  }
}

type StatusFilter = 'all' | 'active' | 'archived'
type TypeFilter = 'all' | 'HQ' | 'STORE' | 'WAREHOUSE' | 'OFFICE'

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

// ── Type pill (HQ/STORE/...) ────────────────────────────────────────────────
const TYPE_COLOR: Record<string, { bg: string; color: string }> = {
  HQ:        { bg: 'rgba(192,38,211,0.12)', color: 'var(--p-magenta)' },
  STORE:     { bg: 'rgba(0,201,177,0.12)',  color: 'var(--p-teal)' },
  WAREHOUSE: { bg: 'rgba(245,158,11,0.12)', color: 'var(--p-warning)' },
  OFFICE:    { bg: 'rgba(0,229,255,0.12)',  color: 'var(--p-cyan)' },
}

function TypePill({ value }: { value: string }) {
  const c = TYPE_COLOR[value] ?? { bg: 'var(--p-surface-2)', color: 'var(--p-muted)' }
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
  branch,
  onEdit,
  onArchive,
  onUnarchive,
  onDelete,
}: {
  branch: PlatformBranch
  onEdit: () => void
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
        onClick={(e) => { e.stopPropagation(); setOpen(o => !o) }}
        aria-label={`Acciones ${branch.name}`}
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
            minWidth: 180,
            background: 'var(--p-surface)',
            border: '1px solid var(--p-border)',
            borderRadius: 4,
            boxShadow: '0 4px 16px rgba(0,0,0,0.4)',
            zIndex: 50,
          }}
        >
          <button style={itemStyle} onClick={() => { setOpen(false); onEdit() }}>
            <i className="fa-solid fa-pen" style={{ marginRight: 8, width: 12 }} /> Editar
          </button>
          <div style={{ borderTop: '1px solid var(--p-border)' }} />
          {branch.is_active ? (
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
export function PlatformBranches() {
  const navigate = useNavigate()

  // Data
  const [branches, setBranches] = useState<PlatformBranch[]>([])
  const [orgs, setOrgs] = useState<PlatformOrg[]>([])
  const [loading, setLoading] = useState(true)

  // Filters
  const [filterOrg, setFilterOrg] = useState<string>('')
  const [filterType, setFilterType] = useState<TypeFilter>('all')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const [showArchived, setShowArchived] = useState(false)

  // Drawer (create/edit)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [editing, setEditing] = useState<PlatformBranch | null>(null)
  const [form, setForm] = useState<BranchFormState>(EMPTY_FORM)
  const [saving, setSaving] = useState(false)

  // Alerts side panel
  const [alertsTarget, setAlertsTarget] = useState<PlatformBranch | null>(null)

  // Archive busy
  const [archivingId, setArchivingId] = useState<number | null>(null)

  // Delete (typed-name + deps)
  const [delTarget, setDelTarget] = useState<PlatformBranch | null>(null)
  const [delDeps, setDelDeps] = useState<BranchDependencies | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [forceDelete, setForceDelete] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const [b, o] = await Promise.all([
        platformApi.getBranches(filterOrg ? Number(filterOrg) : undefined, { include_archived: showArchived }),
        platformApi.getOrgs({ include_archived: true }),
      ])
      setBranches(b)
      setOrgs(o)
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'No se pudieron cargar las sucursales')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [filterOrg, showArchived])

  const orgName = (id: number) => orgs.find((o) => o.id === id)?.name || '—'
  const activeOrgs = orgs.filter((o) => o.is_active)

  // ── KPIs ──────────────────────────────────────────────────────────────────
  // NOTE: "Activas ahora" usa is_active && branch_type !== 'WAREHOUSE' como proxy.
  // TODO(backend): exponer sesiones live (cash sessions abiertas) por sucursal.
  const kpis = useMemo(() => {
    const total = branches.length
    const activasAhora = branches.filter(b => b.is_active && b.branch_type !== 'WAREHOUSE').length
    const promedio = orgs.length > 0 ? (total / orgs.length).toFixed(1) : '0'
    const conAlertas = branches.filter(b => (b.alerts_count ?? 0) > 0).length
    return { total, activasAhora, promedio, conAlertas }
  }, [branches, orgs])

  // ── Filtered rows ─────────────────────────────────────────────────────────
  const filtered = useMemo(() => {
    return branches.filter(b => {
      if (statusFilter === 'active' && !b.is_active) return false
      if (statusFilter === 'archived' && b.is_active) return false
      if (filterType !== 'all' && b.branch_type !== filterType) return false
      return true
    })
  }, [branches, statusFilter, filterType])

  // ── Drawer handlers ───────────────────────────────────────────────────────
  const openCreate = () => {
    setEditing(null)
    setForm({ ...EMPTY_FORM, organization_id: filterOrg || '' })
    setDrawerOpen(true)
  }

  const openEdit = (b: PlatformBranch) => {
    setEditing(b)
    setForm(branchToForm(b))
    setDrawerOpen(true)
  }

  const closeDrawer = () => {
    setDrawerOpen(false)
    setEditing(null)
  }

  const handleSave = async () => {
    if (!form.name.trim()) {
      toast.error('El nombre es requerido')
      return
    }
    if (!form.organization_id) {
      toast.warning('Selecciona una organización')
      return
    }
    setSaving(true)
    try {
      const payload = { ...form, organization_id: Number(form.organization_id) }
      if (editing) {
        await platformApi.updateBranch(editing.id, payload)
        toast.success(`Sucursal "${form.name}" actualizada`)
      } else {
        await platformApi.createBranch(payload as any)
        toast.success(`Sucursal "${form.name}" creada`)
      }
      closeDrawer()
      load()
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'No se pudo guardar la sucursal')
    } finally {
      setSaving(false)
    }
  }

  // ── Archive / unarchive ───────────────────────────────────────────────────
  const handleArchive = async (b: PlatformBranch) => {
    if (!confirm(`¿Archivar sucursal "${b.name}"? Se puede restaurar.`)) return
    setArchivingId(b.id)
    try {
      await platformApi.archiveBranch(b.id)
      toast.success(`"${b.name}" archivada`)
      load()
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'No se pudo archivar')
    } finally {
      setArchivingId(null)
    }
  }

  const handleUnarchive = async (b: PlatformBranch) => {
    setArchivingId(b.id)
    try {
      await platformApi.unarchiveBranch(b.id)
      toast.success(`"${b.name}" restaurada`)
      load()
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'No se pudo restaurar')
    } finally {
      setArchivingId(null)
    }
  }

  // ── Delete with deps ──────────────────────────────────────────────────────
  const openDelete = async (b: PlatformBranch) => {
    setDelTarget(b)
    setDelDeps(null)
    setForceDelete(false)
    try {
      setDelDeps(await platformApi.getBranchDependencies(b.id))
    } catch {
      // backend will still protect on delete
    }
  }

  const closeDelete = () => {
    setDelTarget(null)
    setDelDeps(null)
    setForceDelete(false)
  }

  const handleDelete = async () => {
    if (!delTarget) return
    setDeleting(true)
    try {
      await platformApi.deleteBranch(delTarget.id, forceDelete)
      toast.success(
        forceDelete
          ? `"${delTarget.name}" eliminada permanentemente`
          : `Sucursal "${delTarget.name}" eliminada`,
      )
      closeDelete()
      load()
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Fallo al eliminar')
    } finally {
      setDeleting(false)
    }
  }

  const depsBlock = (delDeps?.sales ?? 0) + (delDeps?.cash_sessions ?? 0) > 0

  // ── Row click: open alerts panel if any, else navigate to org detail ─────
  const handleRowClick = (b: PlatformBranch) => {
    if ((b.alerts_count ?? 0) > 0) {
      setAlertsTarget(b)
    } else {
      navigate(`/platform/organizations/${b.organization_id}`)
    }
  }

  // ── Table columns ─────────────────────────────────────────────────────────
  const fmtNum = (n: number | null | undefined) =>
    n == null ? <span style={{ color: 'var(--p-muted)' }}>—</span> : <span>{n.toLocaleString('es-MX')}</span>

  const fmtDate = (s: string | null | undefined) => {
    if (!s) return <span style={{ color: 'var(--p-muted)' }}>—</span>
    const d = new Date(s)
    if (isNaN(d.getTime())) return <span style={{ color: 'var(--p-muted)' }}>—</span>
    return (
      <span style={{ color: 'var(--p-muted)', fontSize: 12 }}>
        {d.toLocaleString('es-MX', { dateStyle: 'short', timeStyle: 'short' })}
      </span>
    )
  }

  const columns: DataTableColumn<PlatformBranch>[] = [
    {
      key: 'name',
      label: 'Nombre',
      sortable: true,
      sortValue: b => b.name.toLowerCase(),
      accessor: b => (
        <div>
          <div style={{ fontWeight: 600, color: 'var(--p-text)' }}>{b.name}</div>
          <div style={{ fontSize: 11, color: 'var(--p-muted)', fontFamily: 'monospace' }}>#{b.id}</div>
        </div>
      ),
    },
    {
      key: 'org',
      label: 'Org',
      sortable: true,
      sortValue: b => orgName(b.organization_id).toLowerCase(),
      accessor: b => (
        <span style={{ color: 'var(--p-text)', fontSize: 13 }}>{orgName(b.organization_id)}</span>
      ),
    },
    {
      key: 'type',
      label: 'Tipo',
      sortable: true,
      sortValue: b => b.branch_type || '',
      accessor: b => <TypePill value={b.branch_type} />,
    },
    {
      key: 'status',
      label: 'Status',
      sortable: true,
      sortValue: b => (b.is_active ? 'active' : 'archived'),
      accessor: b => (b.is_active ? <StatusBadge status="active" /> : <StatusBadge status="archived" />),
    },
    {
      key: 'sales_today',
      label: 'Ventas hoy',
      sortable: true,
      sortValue: b => b.sales_today ?? -1,
      accessor: b => fmtNum(b.sales_today),
    },
    {
      key: 'tickets_today',
      label: 'Tickets hoy',
      sortable: true,
      sortValue: b => b.tickets_today ?? -1,
      accessor: b => fmtNum(b.tickets_today),
    },
    {
      key: 'last_sync',
      label: 'Última sync',
      sortable: true,
      sortValue: b => b.last_sync_at ?? '',
      accessor: b => fmtDate(b.last_sync_at),
    },
    {
      key: 'alerts',
      label: 'Alertas',
      sortable: true,
      sortValue: b => b.alerts_count ?? 0,
      accessor: b => {
        const n = b.alerts_count ?? 0
        if (n === 0) return <span style={{ color: 'var(--p-muted)' }}>—</span>
        return (
          <span style={{
            background: 'rgba(239,68,68,0.15)',
            color: 'var(--p-danger)',
            padding: '2px 10px',
            borderRadius: 999,
            fontSize: 11,
            fontWeight: 700,
          }}>
            {n}
          </span>
        )
      },
    },
    {
      key: 'actions',
      label: '',
      width: '60px',
      accessor: b => (
        <div onClick={e => e.stopPropagation()}>
          <RowMenu
            branch={b}
            onEdit={() => openEdit(b)}
            onArchive={() => handleArchive(b)}
            onUnarchive={() => handleUnarchive(b)}
            onDelete={() => openDelete(b)}
          />
        </div>
      ),
    },
  ]

  // ── Toolbar (filters) ─────────────────────────────────────────────────────
  const toolbar = (
    <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
      {/* Org selector */}
      <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
        <span style={{ fontSize: 11, color: 'var(--p-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
          Org:
        </span>
        <select
          value={filterOrg}
          onChange={e => setFilterOrg(e.target.value)}
          style={{
            background: 'var(--p-surface-2)',
            border: '1px solid var(--p-border)',
            color: 'var(--p-text)',
            padding: '4px 8px',
            borderRadius: 4,
            fontSize: 12,
          }}
        >
          <option value="">Todas</option>
          {orgs.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
        </select>
      </div>

      {/* Type filter */}
      <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
        <span style={{ fontSize: 11, color: 'var(--p-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
          Tipo:
        </span>
        {(['all', 'HQ', 'STORE', 'WAREHOUSE', 'OFFICE'] as TypeFilter[]).map(t => (
          <button key={t} onClick={() => setFilterType(t)} style={chipStyle(filterType === t)}>
            {t === 'all' ? 'Todos' : t}
          </button>
        ))}
      </div>

      {/* Status filter */}
      <div style={{ display: 'flex', gap: 4 }}>
        {(['all', 'active', 'archived'] as StatusFilter[]).map(s => (
          <button key={s} onClick={() => setStatusFilter(s)} style={chipStyle(statusFilter === s)}>
            {s === 'all' ? 'Todas' : s === 'active' ? 'Activas' : 'Archivadas'}
          </button>
        ))}
      </div>

      {/* Mostrar archivadas (carga incluye archivadas) */}
      <button onClick={() => setShowArchived(s => !s)} style={chipStyle(showArchived)}>
        <i className="fa-solid fa-box-archive" style={{ marginRight: 4 }} />
        Mostrar archivadas
      </button>
    </div>
  )

  // ── Header + KPI strip ────────────────────────────────────────────────────
  const headerActions = (
    <button onClick={openCreate} style={buttonPrimary}>
      <i className="fa-solid fa-plus" /> Nueva sucursal
    </button>
  )

  const kpiStrip = (
    <>
      <KPICard label="Total sucursales" value={kpis.total} accent="teal" icon="fa-store" />
      <KPICard label="Activas ahora" value={kpis.activasAhora} accent="cyan" icon="fa-bolt" />
      <KPICard label="Promedio por org" value={kpis.promedio} accent="purple" icon="fa-chart-pie" />
      <KPICard label="Con alertas" value={kpis.conAlertas} accent="danger" icon="fa-bell" />
    </>
  )

  // ── CSV row ───────────────────────────────────────────────────────────────
  const csvRow = (b: PlatformBranch) => ({
    id: b.id,
    nombre: b.name,
    org_id: b.organization_id,
    organizacion: orgName(b.organization_id),
    tipo: b.branch_type,
    status: b.is_active ? 'ACTIVE' : 'ARCHIVED',
    can_sell: b.can_sell ? 'true' : 'false',
    ventas_hoy: b.sales_today ?? '',
    tickets_hoy: b.tickets_today ?? '',
    ultima_sync: b.last_sync_at ?? '',
    alertas: b.alerts_count ?? 0,
    email: b.email || '',
    phone: b.phone || '',
    address: b.address || '',
    city: b.city || '',
    state: b.state || '',
    country: b.country || '',
  })

  return (
    <PlatformPageShell
      breadcrumb="Platform / Sucursales"
      title="Sucursales cross-org"
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
          <p style={{ marginTop: 12, fontSize: 13 }}>Cargando sucursales...</p>
        </div>
      ) : (
        <DataTable
          data={filtered}
          columns={columns}
          rowKey={b => b.id}
          searchable
          searchKeys={b => `${b.name} ${orgName(b.organization_id)} ${b.address || ''}`}
          pageSize={20}
          csvFilename="branches.csv"
          csvRow={csvRow}
          toolbar={toolbar}
          onRowClick={handleRowClick}
          emptyMessage={branches.length === 0 ? 'Sin sucursales registradas' : 'Sin resultados con los filtros aplicados'}
        />
      )}

      {/* Create / Edit drawer */}
      <SideDrawer
        open={drawerOpen}
        title={editing ? `Editar ${editing.name}` : 'Nueva sucursal'}
        onClose={closeDrawer}
        onSave={handleSave}
        saving={saving}
        saveLabel={editing ? 'Guardar' : 'Crear'}
        width={520}
      >
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <div style={{ gridColumn: '1 / -1' }}>
            <label style={labelStyle}>Nombre *</label>
            <input
              value={form.name}
              onChange={e => setForm({ ...form, name: e.target.value })}
              required
              style={inputStyle}
            />
          </div>

          <div>
            <label style={labelStyle}>Organización *</label>
            <select
              value={form.organization_id}
              onChange={e => setForm({ ...form, organization_id: e.target.value })}
              required
              style={inputStyle}
            >
              <option value="">— Seleccionar —</option>
              {activeOrgs.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
            </select>
          </div>

          <div>
            <label style={labelStyle}>Tipo</label>
            <select
              value={form.branch_type}
              onChange={e => setForm({ ...form, branch_type: e.target.value })}
              style={inputStyle}
            >
              {['HQ', 'STORE', 'WAREHOUSE', 'OFFICE'].map((t) => <option key={t}>{t}</option>)}
            </select>
          </div>

          <div style={{ gridColumn: '1 / -1', display: 'flex', gap: 16, alignItems: 'center' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--p-text)', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={form.can_sell}
                onChange={e => setForm({ ...form, can_sell: e.target.checked })}
              />
              Puede vender
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--p-text)', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={form.is_active}
                onChange={e => setForm({ ...form, is_active: e.target.checked })}
              />
              Activa
            </label>
          </div>

          <div>
            <label style={labelStyle}>Email</label>
            <input
              type="email"
              value={form.email}
              onChange={e => setForm({ ...form, email: e.target.value })}
              style={inputStyle}
            />
          </div>

          <div>
            <label style={labelStyle}>Teléfono</label>
            <input
              value={form.phone}
              onChange={e => setForm({ ...form, phone: e.target.value })}
              style={inputStyle}
            />
          </div>

          <div style={{ gridColumn: '1 / -1', borderTop: '1px solid var(--p-border)', paddingTop: 8, marginTop: 4 }}>
            <p style={{ fontSize: 11, color: 'var(--p-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', fontWeight: 600, margin: 0 }}>
              Dirección
            </p>
          </div>

          <div style={{ gridColumn: '1 / -1' }}>
            <label style={labelStyle}>Dirección (resumen)</label>
            <input
              value={form.address}
              onChange={e => setForm({ ...form, address: e.target.value })}
              style={inputStyle}
            />
          </div>

          <div>
            <label style={labelStyle}>Calle y número</label>
            <input
              value={form.address_line1}
              onChange={e => setForm({ ...form, address_line1: e.target.value })}
              style={inputStyle}
            />
          </div>

          <div>
            <label style={labelStyle}>Int / Edificio</label>
            <input
              value={form.address_line2}
              onChange={e => setForm({ ...form, address_line2: e.target.value })}
              style={inputStyle}
            />
          </div>

          <div>
            <label style={labelStyle}>Colonia</label>
            <input
              value={form.neighborhood}
              onChange={e => setForm({ ...form, neighborhood: e.target.value })}
              style={inputStyle}
            />
          </div>

          <div>
            <label style={labelStyle}>Ciudad</label>
            <input
              value={form.city}
              onChange={e => setForm({ ...form, city: e.target.value })}
              style={inputStyle}
            />
          </div>

          <div>
            <label style={labelStyle}>Estado</label>
            <input
              value={form.state}
              onChange={e => setForm({ ...form, state: e.target.value })}
              style={inputStyle}
            />
          </div>

          <div>
            <label style={labelStyle}>CP</label>
            <input
              value={form.postal_code}
              onChange={e => setForm({ ...form, postal_code: e.target.value })}
              style={inputStyle}
            />
          </div>

          <div>
            <label style={labelStyle}>País</label>
            <input
              value={form.country}
              onChange={e => setForm({ ...form, country: e.target.value })}
              style={inputStyle}
            />
          </div>

          <div style={{ gridColumn: '1 / -1', borderTop: '1px solid var(--p-border)', paddingTop: 8, marginTop: 4 }}>
            <p style={{ fontSize: 11, color: 'var(--p-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', fontWeight: 600, margin: 0 }}>
              Impresora / Tickets
            </p>
          </div>

          <div>
            <label style={labelStyle}>Nombre impresora</label>
            <input
              value={form.printer_name}
              onChange={e => setForm({ ...form, printer_name: e.target.value })}
              style={inputStyle}
            />
          </div>

          <div>
            <label style={labelStyle}>Ancho papel (mm)</label>
            <select
              value={form.paper_width_mm}
              onChange={e => setForm({ ...form, paper_width_mm: Number(e.target.value) })}
              style={inputStyle}
            >
              <option value={58}>58 mm</option>
              <option value={80}>80 mm</option>
            </select>
          </div>

          <div style={{ gridColumn: '1 / -1' }}>
            <label style={labelStyle}>Ticket header</label>
            <input
              value={form.ticket_header}
              onChange={e => setForm({ ...form, ticket_header: e.target.value })}
              placeholder="(hereda de la org si vacío)"
              style={inputStyle}
            />
          </div>

          <div style={{ gridColumn: '1 / -1' }}>
            <label style={labelStyle}>Ticket footer</label>
            <input
              value={form.ticket_footer}
              onChange={e => setForm({ ...form, ticket_footer: e.target.value })}
              placeholder="(hereda de la org si vacío)"
              style={inputStyle}
            />
          </div>
        </div>
      </SideDrawer>

      {/* Alerts side panel */}
      <SideDrawer
        open={!!alertsTarget}
        title={alertsTarget ? `Alertas de ${alertsTarget.name}` : 'Alertas'}
        onClose={() => setAlertsTarget(null)}
        width={460}
      >
        {alertsTarget && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div style={{
              padding: 12,
              background: 'rgba(239,68,68,0.08)',
              border: '1px solid rgba(239,68,68,0.3)',
              borderRadius: 4,
              display: 'flex',
              alignItems: 'center',
              gap: 10,
            }}>
              <i className="fa-solid fa-bell" style={{ color: 'var(--p-danger)', fontSize: 16 }} />
              <div>
                <p style={{ margin: 0, fontSize: 12, color: 'var(--p-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', fontWeight: 600 }}>
                  Alertas activas
                </p>
                <p style={{ margin: 0, fontSize: '1.5rem', fontWeight: 800, color: 'var(--p-danger)' }}>
                  {alertsTarget.alerts_count ?? 0}
                </p>
              </div>
            </div>

            <div style={{
              padding: 14,
              background: 'var(--p-surface-2)',
              border: '1px solid var(--p-border)',
              borderRadius: 4,
            }}>
              <p style={{ margin: '0 0 6px', fontSize: 12, color: 'var(--p-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', fontWeight: 600 }}>
                Pendiente
              </p>
              <p style={{ margin: 0, fontSize: 13, color: 'var(--p-text)', lineHeight: 1.5 }}>
                Endpoint de alertas pendiente — mostrar últimos N eventos del branch.
              </p>
              <p style={{ margin: '8px 0 0', fontSize: 11, color: 'var(--p-hint)' }}>
                TODO(backend): exponer <code style={{ color: 'var(--p-cyan)' }}>GET /platform/branches/&#123;id&#125;/alerts</code> con
                {' '}eventos recientes (low-stock, errores de sync, sesiones de caja con varianza, etc.).
              </p>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
              <button
                onClick={() => navigate(`/platform/organizations/${alertsTarget.organization_id}`)}
                style={buttonSecondary}
              >
                <i className="fa-solid fa-arrow-up-right-from-square" style={{ marginRight: 6 }} />
                Ver organización
              </button>
            </div>
          </div>
        )}
      </SideDrawer>

      {/* Delete with deps */}
      {delTarget && depsBlock && !forceDelete ? (
        // Bloqueado por dependencias — modal informativo + opción cascade
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
              width: 480,
              maxWidth: '90vw',
            }}
          >
            <h3 style={{ margin: 0, color: 'var(--p-text)', fontSize: '1rem', fontWeight: 700 }}>
              <i className="fa-solid fa-triangle-exclamation" style={{ color: 'var(--p-warning)', marginRight: 8 }} />
              Eliminación bloqueada
            </h3>
            <p style={{ color: 'var(--p-muted)', fontSize: '0.85rem', margin: '8px 0 12px' }}>
              <strong style={{ color: 'var(--p-text)' }}>{delTarget.name}</strong> tiene datos transaccionales.
              El backend bloqueará el DELETE para preservar integridad. Lo más seguro es <strong style={{ color: 'var(--p-warning)' }}>archivar</strong>.
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
              {(delDeps?.sales ?? 0) > 0 && (
                <li><i className="fa-solid fa-circle-dot" style={{ fontSize: 6, marginRight: 8 }} /> {delDeps?.sales} venta(s) registrada(s)</li>
              )}
              {(delDeps?.cash_sessions ?? 0) > 0 && (
                <li><i className="fa-solid fa-circle-dot" style={{ fontSize: 6, marginRight: 8 }} /> {delDeps?.cash_sessions} sesión(es) de caja</li>
              )}
              {(delDeps?.users ?? 0) > 0 && (
                <li><i className="fa-solid fa-circle-dot" style={{ fontSize: 6, marginRight: 8 }} /> {delDeps?.users} usuario(s) asignado(s)</li>
              )}
            </ul>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', flexWrap: 'wrap' }}>
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
              <button
                onClick={() => setForceDelete(true)}
                style={{
                  background: 'var(--p-danger)',
                  color: '#fff',
                  fontWeight: 700,
                  border: 'none',
                  padding: '6px 16px',
                  borderRadius: 4,
                  fontSize: 12,
                  cursor: 'pointer',
                }}
              >
                <i className="fa-solid fa-skull-crossbones" style={{ marginRight: 6 }} />
                Eliminar cascade
              </button>
            </div>
          </div>
        </div>
      ) : (
        <ConfirmModal
          open={!!delTarget}
          title={
            forceDelete
              ? `Cascade: eliminar ${delTarget?.name ?? ''}`
              : `Eliminar ${delTarget?.name ?? ''}`
          }
          message={
            forceDelete
              ? `Acción irreversible. Se eliminarán ${delDeps?.sales ?? 0} venta(s), ${delDeps?.cash_sessions ?? 0} sesión(es) de caja y se desvincularán ${delDeps?.users ?? 0} usuario(s).`
              : 'Esta acción es permanente y no reversible.'
          }
          resourceName={delTarget?.name ?? ''}
          destructive
          busy={deleting}
          onClose={closeDelete}
          onConfirm={handleDelete}
        />
      )}

      {/* Inline busy indicator */}
      {archivingId !== null && (
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
