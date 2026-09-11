import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  platformApi,
  IndustryPreset,
  Module,
  OrgDependencies,
  OrgModule,
  PlatformBranch,
  PlatformOrg,
  PlatformUser,
  UpsellResponse,
} from '../../api/platform'
import { toast } from '../../store/toastStore'
import { useImpersonationStore } from '../../store/impersonationStore'
import { PlatformPageShell } from '../../components/platform/PlatformPageShell'
import { StatusBadge } from '../../components/platform/StatusBadge'
import { SideDrawer } from '../../components/platform/SideDrawer'
import { ConfirmModal } from '../../components/platform/ConfirmModal'
import { TablaDesplazable } from '../../components/ui/TablaDesplazable'

// ── Inline shared styles (tokens) ────────────────────────────────────────────
const card: React.CSSProperties = {
  background: 'var(--p-surface)',
  border: '1px solid var(--p-border)',
  borderRadius: 6,
  padding: '1rem 1.25rem',
}

const sectionTitle: React.CSSProperties = {
  fontSize: '0.7rem',
  color: 'var(--p-muted)',
  textTransform: 'uppercase',
  letterSpacing: '0.08em',
  fontWeight: 600,
  margin: 0,
}

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
  padding: '8px 14px',
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
  padding: '8px 14px',
  borderRadius: 4,
  fontSize: 12,
  fontWeight: 600,
  cursor: 'pointer',
  display: 'inline-flex',
  alignItems: 'center',
  gap: 6,
}

const buttonDanger: React.CSSProperties = {
  background: 'rgba(239,68,68,0.12)',
  color: 'var(--p-danger)',
  border: '1px solid rgba(239,68,68,0.4)',
  padding: '8px 14px',
  borderRadius: 4,
  fontSize: 12,
  fontWeight: 700,
  cursor: 'pointer',
  display: 'inline-flex',
  alignItems: 'center',
  gap: 6,
}

const tableHeadCell: React.CSSProperties = {
  padding: '10px 14px',
  textAlign: 'left',
  color: 'var(--p-muted)',
  fontSize: '0.7rem',
  textTransform: 'uppercase',
  letterSpacing: '0.08em',
  fontWeight: 600,
  borderBottom: '1px solid var(--p-border)',
}

const tableCell: React.CSSProperties = {
  padding: '10px 14px',
  borderBottom: '1px solid var(--p-border)',
  color: 'var(--p-text)',
  fontSize: 13,
  verticalAlign: 'middle',
}

type Tab = 'branches' | 'users'

type EditFormState = {
  name: string
  legal_name: string
  tax_id: string
  email: string
  phone: string
  address: string
  timezone: string
}

const EMPTY_EDIT: EditFormState = {
  name: '',
  legal_name: '',
  tax_id: '',
  email: '',
  phone: '',
  address: '',
  timezone: 'America/Mexico_City',
}

// Simple (non-typed) confirm modal — used for low-risk confirms (apply / reset preset).
function SimpleConfirm({
  open, title, message, confirmLabel = 'Confirmar', destructive, busy, onClose, onConfirm,
}: {
  open: boolean; title: string; message: React.ReactNode; confirmLabel?: string
  destructive?: boolean; busy?: boolean; onClose: () => void; onConfirm: () => void
}) {
  if (!open) return null
  const accent = destructive ? 'var(--p-danger)' : 'var(--p-teal)'
  return (
    <div onClick={onClose} style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)',
      zIndex: 1100, display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <div onClick={e => e.stopPropagation()} style={{
        background: 'var(--p-surface)', border: `1px solid ${accent}`,
        borderRadius: 6, padding: 20, width: 460, maxWidth: '90vw',
      }}>
        <h3 style={{ margin: 0, color: 'var(--p-text)', fontSize: '1rem', fontWeight: 700 }}>{title}</h3>
        <div style={{ color: 'var(--p-muted)', fontSize: '0.85rem', margin: '10px 0 16px' }}>{message}</div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <button onClick={onClose} disabled={busy} style={buttonSecondary}>Cancelar</button>
          <button
            onClick={onConfirm}
            disabled={busy}
            style={{
              background: accent, color: destructive ? '#fff' : 'var(--dax-on-accent)',
              fontWeight: 700, border: 'none', padding: '8px 16px',
              borderRadius: 4, fontSize: 12, cursor: 'pointer',
              opacity: busy ? 0.5 : 1,
            }}
          >
            {busy ? '...' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}

// Modal for delete-blocked-by-deps (informational, non-confirmable).
function DepsBlockedModal({
  open, orgName, deps, onClose, onArchive, canArchive,
}: {
  open: boolean; orgName: string; deps: OrgDependencies | null
  onClose: () => void; onArchive?: () => void; canArchive: boolean
}) {
  if (!open) return null
  return (
    <div onClick={onClose} style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)',
      zIndex: 1100, display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <div onClick={e => e.stopPropagation()} style={{
        background: 'var(--p-surface)', border: '1px solid var(--p-warning)',
        borderRadius: 6, padding: 20, width: 460, maxWidth: '90vw',
      }}>
        <h3 style={{ margin: 0, color: 'var(--p-text)', fontSize: '1rem', fontWeight: 700 }}>
          <i className="fa-solid fa-triangle-exclamation" style={{ color: 'var(--p-warning)', marginRight: 8 }} />
          Eliminación bloqueada
        </h3>
        <p style={{ color: 'var(--p-muted)', fontSize: '0.85rem', margin: '8px 0 12px' }}>
          <strong style={{ color: 'var(--p-text)' }}>{orgName}</strong> tiene dependencias activas. Para eliminar,
          primero debes archivarla o migrar/eliminar:
        </p>
        <ul style={{
          margin: '0 0 16px', padding: 12,
          background: 'rgba(245,158,11,0.05)',
          border: '1px solid rgba(245,158,11,0.2)',
          borderRadius: 4, listStyle: 'none',
          color: 'var(--p-warning)', fontSize: 12,
        }}>
          {(deps?.branches ?? 0) > 0 && (
            <li><i className="fa-solid fa-circle-dot" style={{ fontSize: 6, marginRight: 8 }} />{deps?.branches} sucursal(es)</li>
          )}
          {(deps?.users ?? 0) > 0 && (
            <li><i className="fa-solid fa-circle-dot" style={{ fontSize: 6, marginRight: 8 }} />{deps?.users} usuario(s) asociado(s)</li>
          )}
        </ul>
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <button onClick={onClose} style={buttonSecondary}>Cerrar</button>
          {canArchive && onArchive && (
            <button onClick={onArchive} style={{
              background: 'var(--p-warning)', color: '#000', fontWeight: 700,
              border: 'none', padding: '8px 16px', borderRadius: 4, fontSize: 12, cursor: 'pointer',
            }}>
              <i className="fa-solid fa-box-archive" style={{ marginRight: 6 }} />
              Archivar en su lugar
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

export function PlatformOrgDetail() {
  const { orgId } = useParams<{ orgId: string }>()
  const id = Number(orgId)
  const navigate = useNavigate()

  const [org, setOrg] = useState<PlatformOrg | null>(null)
  const [modules, setModules] = useState<OrgModule[]>([])
  const [catalog, setCatalog] = useState<Module[]>([])
  const [users, setUsers] = useState<PlatformUser[]>([])
  const [branches, setBranches] = useState<PlatformBranch[]>([])
  const [presets, setPresets] = useState<IndustryPreset[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(false)

  // Upsell recommendations
  const [upsell, setUpsell] = useState<UpsellResponse | null>(null)
  const [upsellLoading, setUpsellLoading] = useState(false)
  const [activatingModule, setActivatingModule] = useState<string | null>(null)

  const [tab, setTab] = useState<Tab>('branches')

  // Module toggle busy
  const [togglingModule, setTogglingModule] = useState<string | null>(null)

  // Edit drawer
  const [editOpen, setEditOpen] = useState(false)
  const [editForm, setEditForm] = useState<EditFormState>(EMPTY_EDIT)
  const [savingEdit, setSavingEdit] = useState(false)

  // Preset section
  const [selectedPresetId, setSelectedPresetId] = useState<number | null>(null)
  const [applyingPreset, setApplyingPreset] = useState(false)
  const [applyTypedConfirm, setApplyTypedConfirm] = useState(false)
  const [applySimpleConfirm, setApplySimpleConfirm] = useState(false)
  const [resettingPreset, setResettingPreset] = useState(false)
  const [resetConfirmOpen, setResetConfirmOpen] = useState(false)

  // Danger zone — archive
  const [archiveOpen, setArchiveOpen] = useState(false)
  const [archiving, setArchiving] = useState(false)

  // Danger zone — delete
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [deleteDeps, setDeleteDeps] = useState<OrgDependencies | null>(null)
  const [depsBlockedOpen, setDepsBlockedOpen] = useState(false)
  const [deleting, setDeleting] = useState(false)

  // Impersonation (preserved from prior version, moved to header secondary action).
  const [impersonateOpen, setImpersonateOpen] = useState(false)
  const [impersonateReason, setImpersonateReason] = useState('')
  const [impersonating, setImpersonating] = useState(false)
  const startImpersonation = useImpersonationStore((s) => s.start)

  const loadUpsell = async () => {
    setUpsellLoading(true)
    try {
      const data = await platformApi.getUpsellRecommendations(id)
      setUpsell(data)
    } catch {
      setUpsell(null)
    } finally {
      setUpsellLoading(false)
    }
  }

  const load = async () => {
    setLoading(true)
    setLoadError(false)
    try {
      const [o, m, u, b, p, cat] = await Promise.all([
        platformApi.getOrg(id),
        platformApi.getOrgModules(id),
        platformApi.getUsers({ organization_id: id }),
        platformApi.getBranches(id),
        platformApi.getPresets(),
        platformApi.getModulesCatalog().catch(() => [] as Module[]),
      ])
      loadUpsell()
      setOrg(o)
      setModules(m)
      setUsers(u)
      setBranches(b)
      setPresets(p)
      setCatalog(cat)
      setEditForm({
        name: o.name || '',
        legal_name: o.legal_name || '',
        tax_id: o.tax_id || '',
        email: o.email || '',
        phone: o.phone || '',
        address: o.address || '',
        timezone: o.timezone || 'America/Mexico_City',
      })
      // Preselect current preset
      const current = p.find((pr: IndustryPreset) => pr.industry_type === o.industry_type)
      setSelectedPresetId(current?.id ?? (p[0]?.id ?? null))
    } catch (err: any) {
      const status = err?.response?.status
      if (status !== 404) {
        toast.error(err?.response?.data?.detail || 'Error cargando la organización')
      }
      setLoadError(true)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [id])

  // ── Module catalog map for BETA/STABLE badges ───────────────────────────
  const catalogByKey = useMemo(() => {
    const m = new Map<string, Module>()
    catalog.forEach(c => m.set(c.key, c))
    return m
  }, [catalog])

  const enabledModules = useMemo(() => modules.filter(m => m.is_enabled).map(m => m.key), [modules])

  const selectedPreset = useMemo(
    () => presets.find(p => p.id === selectedPresetId) || null,
    [presets, selectedPresetId]
  )

  // Modules currently enabled but NOT in selected preset (will be deactivated)
  const willDeactivate = useMemo(() => {
    if (!selectedPreset) return []
    const presetSet = new Set(selectedPreset.modules)
    return enabledModules.filter(k => !presetSet.has(k))
  }, [enabledModules, selectedPreset])

  // ── Module toggle ──────────────────────────────────────────────────────
  const toggleModule = async (key: string, current: boolean) => {
    if (togglingModule) return
    setTogglingModule(key)
    setModules(prev => prev.map(m => m.key === key ? { ...m, is_enabled: !current } : m))
    try {
      await platformApi.toggleModule(id, key, !current)
      toast.success(`Módulo ${key} ${!current ? 'activado' : 'desactivado'}`)
    } catch (err: any) {
      setModules(prev => prev.map(m => m.key === key ? { ...m, is_enabled: current } : m))
      toast.error(err?.response?.data?.detail || `No se pudo cambiar el módulo ${key}`)
    } finally {
      setTogglingModule(null)
    }
  }

  // ── Edit drawer save ───────────────────────────────────────────────────
  const handleSaveEdit = async () => {
    if (!editForm.name.trim()) {
      toast.error('El nombre es requerido')
      return
    }
    setSavingEdit(true)
    try {
      await platformApi.updateOrg(id, editForm)
      toast.success('Organización actualizada')
      setEditOpen(false)
      load()
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'No se pudo actualizar')
    } finally {
      setSavingEdit(false)
    }
  }

  // ── Preset apply ───────────────────────────────────────────────────────
  const triggerApplyPreset = () => {
    if (!selectedPreset) {
      toast.warning('Selecciona un preset primero')
      return
    }
    if (willDeactivate.length > 0) setApplyTypedConfirm(true)
    else setApplySimpleConfirm(true)
  }

  const doApplyPreset = async () => {
    if (!selectedPreset || !org) return
    setApplyingPreset(true)
    try {
      // setIndustry first if it changed; backend apply-preset uses org.industry_type
      if (org.industry_type !== selectedPreset.industry_type) {
        await platformApi.setIndustry(id, selectedPreset.industry_type)
      }
      const res = await platformApi.applyPreset(id)
      toast.success(res?.message || `Preset "${selectedPreset.display_name}" aplicado`)
      setApplyTypedConfirm(false)
      setApplySimpleConfirm(false)
      load()
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'No se pudo aplicar el preset')
    } finally {
      setApplyingPreset(false)
    }
  }

  const doResetPreset = async () => {
    setResettingPreset(true)
    try {
      const res = await platformApi.resetPreset(id)
      toast.success(res?.message || 'Preset reseteado')
      setResetConfirmOpen(false)
      load()
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'No se pudo resetear el preset')
    } finally {
      setResettingPreset(false)
    }
  }

  // ── Archive / delete ───────────────────────────────────────────────────
  const doArchive = async () => {
    if (!org) return
    setArchiving(true)
    try {
      await platformApi.archiveOrg(id)
      toast.success(`Organización "${org.name}" archivada`)
      setArchiveOpen(false)
      load()
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'No se pudo archivar')
    } finally {
      setArchiving(false)
    }
  }

  const openDelete = async () => {
    setDeleteDeps(null)
    try {
      const deps = await platformApi.getOrgDependencies(id)
      setDeleteDeps(deps)
      const blocking = (deps.branches ?? 0) + (deps.users ?? 0) > 0
      if (blocking) {
        setDepsBlockedOpen(true)
      } else {
        setDeleteOpen(true)
      }
    } catch {
      // If deps fetch fails, allow attempting; backend will validate.
      setDeleteOpen(true)
    }
  }

  const doDelete = async () => {
    if (!org) return
    setDeleting(true)
    try {
      // Sin force: el backend valida dependencias (igual que el borrado
      // desde la lista). El borrado en cascada no debe ser el default.
      await platformApi.deleteOrg(id)
      toast.success(`Organización "${org.name}" eliminada`)
      navigate('/platform/organizations')
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'No se pudo eliminar')
    } finally {
      setDeleting(false)
    }
  }

  // ── Impersonation ──────────────────────────────────────────────────────
  const handleImpersonate = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!org) return
    if (impersonateReason.trim().length < 3) {
      toast.warning('Ingresa una razón (mínimo 3 caracteres)')
      return
    }
    setImpersonating(true)
    try {
      const res = await platformApi.impersonate(id, impersonateReason.trim())
      startImpersonation(id, org.name)
      toast.success(`Modo auditoría activado para ${org.name}`)
      setImpersonateOpen(false)
      setImpersonateReason('')
      navigate(res?.redirect_url && typeof res.redirect_url === 'string'
        ? res.redirect_url.replace('/command-center', '/hq/operations')
        : '/hq/operations')
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'No se pudo iniciar el modo auditoría')
    } finally {
      setImpersonating(false)
    }
  }

  // ── Render guards ──────────────────────────────────────────────────────
  if (loading) {
    return (
      <div style={{
        background: 'var(--p-bg)', minHeight: '100vh',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontFamily: 'Montserrat, sans-serif',
      }}>
        <div style={{ color: 'var(--p-muted)', fontSize: 13 }}>
          <i className="fa-solid fa-spinner fa-spin" style={{ marginRight: 8 }} />
          Cargando organización…
        </div>
      </div>
    )
  }

  if (loadError || !org) {
    return (
      <PlatformPageShell
        breadcrumb="Platform / Organizaciones"
        title="Organización"
        actions={
          <Link to="/platform/organizations" style={buttonSecondary}>
            <i className="fa-solid fa-arrow-left" /> Volver
          </Link>
        }
      >
        <div style={{ ...card, textAlign: 'center', padding: '3rem' }}>
          <p style={{ color: 'var(--p-muted)', marginBottom: 12 }}>
            {loadError ? 'Error cargando la organización' : 'Organización no encontrada'}
          </p>
          <button onClick={load} style={buttonPrimary}>
            <i className="fa-solid fa-rotate" /> Reintentar
          </button>
        </div>
      </PlatformPageShell>
    )
  }

  // ── Header counts ──────────────────────────────────────────────────────
  const counts = {
    branches: branches.length,
    users: users.length,
    activeModules: enabledModules.length,
  }

  const headerActions = (
    <>
      <Link to="/platform/organizations" style={buttonSecondary}>
        <i className="fa-solid fa-arrow-left" /> Volver
      </Link>
      <button onClick={() => setImpersonateOpen(true)} style={buttonSecondary} title="Modo auditoría — registra el acceso y navega al dashboard HQ">
        <i className="fa-solid fa-eye" /> Audit
      </button>
      <button onClick={() => setEditOpen(true)} style={buttonPrimary}>
        <i className="fa-solid fa-pen" /> Editar
      </button>
    </>
  )

  // ── Render ─────────────────────────────────────────────────────────────
  return (
    <PlatformPageShell
      breadcrumb={
        <>
          <Link to="/platform" style={{ color: 'inherit', textDecoration: 'none' }}>Platform</Link>
          {' / '}
          <Link to="/platform/organizations" style={{ color: 'inherit', textDecoration: 'none' }}>Organizaciones</Link>
          {' / '}
          <span style={{ color: 'var(--p-text)' }}>{org.name}</span>
        </>
      }
      title={org.name}
      actions={headerActions}
    >
      {/* ── Header card ───────────────────────────────────────────────── */}
      <div style={{ ...card, display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <span style={{
            background: 'rgba(123,47,190,0.12)',
            color: 'var(--p-purple)',
            padding: '4px 10px',
            borderRadius: 4,
            fontSize: 11,
            fontFamily: 'monospace',
            fontWeight: 600,
          }}>
            {org.industry_type || 'SIN INDUSTRIA'}
          </span>
          {!org.is_active ? (
            <StatusBadge status="archived" />
          ) : org.status === 'SUSPENDED' ? (
            <StatusBadge status="beta" label="Suspendida" />
          ) : (
            <StatusBadge status="active" />
          )}
          <span style={{ fontSize: 12, color: 'var(--p-muted)' }}>
            <i className="fa-solid fa-calendar" style={{ marginRight: 6 }} />
            Creada {new Date(org.created_at).toLocaleDateString('es-MX', { year: 'numeric', month: 'short', day: '2-digit' })}
          </span>
          <span style={{ fontSize: 11, color: 'var(--p-hint)', fontFamily: 'monospace' }}>#{org.id}</span>
        </div>
        <div style={{ display: 'flex', gap: 18, fontSize: 12, color: 'var(--p-muted)' }}>
          <div><strong style={{ color: 'var(--p-text)' }}>{counts.branches}</strong> sucursales</div>
          <div><strong style={{ color: 'var(--p-text)' }}>{counts.users}</strong> usuarios</div>
          <div><strong style={{ color: 'var(--p-text)' }}>{counts.activeModules}</strong> módulos activos</div>
        </div>
      </div>

      {/* ── Sección Módulos ───────────────────────────────────────────── */}
      <section style={card}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12, flexWrap: 'wrap', gap: 8 }}>
          <p style={sectionTitle}>Módulos activos</p>
          <span style={{ fontSize: 11, color: 'var(--p-muted)' }}>
            {counts.activeModules} de {modules.length} habilitados
          </span>
        </div>
        {modules.length === 0 ? (
          <div style={{ textAlign: 'center', color: 'var(--p-muted)', padding: '2rem 0', fontSize: 13 }}>
            Sin módulos configurados
          </div>
        ) : (
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
            gap: 12,
          }}>
            {modules.map(m => {
              const cat = catalogByKey.get(m.key)
              const moduleStatus = (cat?.status || m.status || '').toUpperCase()
              const isBeta = moduleStatus === 'BETA'
              const isStable = moduleStatus === 'STABLE'
              const busy = togglingModule === m.key
              return (
                <div
                  key={m.key}
                  style={{
                    background: 'var(--p-surface-2)',
                    border: '1px solid var(--p-border)',
                    borderRadius: 4,
                    padding: '12px 14px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: 10,
                  }}
                  title={isBeta ? 'Módulo en beta: úsalo bajo tu responsabilidad' : undefined}
                >
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                      <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--p-text)' }}>
                        {cat?.name || m.name || m.key}
                      </span>
                      {isBeta && <StatusBadge status="beta" />}
                      {isStable && <StatusBadge status="stable" />}
                    </div>
                    <div style={{ fontSize: 11, color: 'var(--p-muted)', fontFamily: 'monospace' }}>
                      {m.key} · {m.scope}
                    </div>
                  </div>
                  <button
                    onClick={() => toggleModule(m.key, m.is_enabled)}
                    disabled={busy}
                    aria-label={`Toggle ${m.key}`}
                    style={{
                      position: 'relative',
                      width: 38,
                      height: 20,
                      borderRadius: 999,
                      border: 'none',
                      background: m.is_enabled ? 'var(--p-teal)' : 'var(--p-border)',
                      cursor: busy ? 'wait' : 'pointer',
                      transition: 'background 0.2s',
                      opacity: busy ? 0.6 : 1,
                      flexShrink: 0,
                    }}
                  >
                    <span style={{
                      position: 'absolute',
                      top: 2,
                      left: m.is_enabled ? 20 : 2,
                      width: 16,
                      height: 16,
                      borderRadius: '50%',
                      background: '#fff',
                      transition: 'left 0.2s',
                    }} />
                  </button>
                </div>
              )
            })}
          </div>
        )}
      </section>

      {/* ── Sección Módulos disponibles (upsell) ─────────────────────── */}
      <section style={card}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12, flexWrap: 'wrap', gap: 8 }}>
          <p style={sectionTitle}>
            <i className="fa-solid fa-arrow-up-right-dots" style={{ marginRight: 6, color: 'var(--p-teal)' }} />
            Módulos disponibles
          </p>
          <span style={{ fontSize: 11, color: 'var(--p-muted)' }}>
            {upsell ? `${upsell.recommendations.length} disponibles` : '—'}
          </span>
        </div>

        {upsellLoading && (
          <p style={{ fontSize: 12, color: 'var(--p-muted)' }}>Cargando recomendaciones...</p>
        )}

        {!upsellLoading && upsell && upsell.recommendations.length === 0 && (
          <p style={{ fontSize: 12, color: 'var(--p-muted)', fontStyle: 'italic' }}>
            Tu organización tiene todos los módulos recomendados activos.
          </p>
        )}

        {!upsellLoading && upsell && upsell.recommendations.length > 0 && (
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
            gap: 12,
          }}>
            {upsell.recommendations.map(rec => {
              const busy = activatingModule === rec.module_key
              return (
                <div
                  key={rec.module_key}
                  style={{
                    background: 'var(--p-bg)',
                    border: `1px solid ${rec.in_recommended_preset ? 'var(--p-teal)' : 'var(--p-border)'}`,
                    borderRadius: 6,
                    padding: 14,
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 10,
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                    {rec.icon && <i className={`fa-solid ${rec.icon}`} style={{ color: 'var(--p-cyan)' }} />}
                    <span style={{ fontWeight: 700, fontSize: 13 }}>{rec.module_name}</span>
                    <span style={{
                      fontSize: 9,
                      padding: '1px 6px',
                      borderRadius: 3,
                      fontWeight: 700,
                      letterSpacing: '0.04em',
                      background: rec.status === 'BETA' ? 'rgba(245,158,11,0.18)' : 'rgba(34,197,94,0.15)',
                      color: rec.status === 'BETA' ? 'var(--p-warning)' : 'var(--p-success)',
                    }}>
                      {rec.status}
                    </span>
                  </div>

                  {rec.in_recommended_preset && (
                    <span style={{
                      fontSize: 10,
                      color: 'var(--p-teal)',
                      fontWeight: 600,
                      letterSpacing: '0.04em',
                      textTransform: 'uppercase',
                    }}>
                      <i className="fa-solid fa-star" style={{ marginRight: 4 }} />
                      Recomendado para tu plan
                    </span>
                  )}

                  {rec.upgrade_prompt && (
                    <p style={{ margin: 0, fontSize: 12, color: 'var(--p-muted)', lineHeight: 1.4 }}>
                      {rec.upgrade_prompt}
                    </p>
                  )}

                  {rec.value_props.length > 0 && (
                    <ul style={{ margin: 0, paddingLeft: 18, fontSize: 11, color: 'var(--p-text)' }}>
                      {rec.value_props.map((vp, i) => <li key={i}>{vp}</li>)}
                    </ul>
                  )}

                  <button
                    onClick={async () => {
                      setActivatingModule(rec.module_key)
                      try {
                        await platformApi.toggleModule(id, rec.module_key, true)
                        toast.success(`${rec.module_name} activado`)
                        await Promise.all([loadUpsell(), load()])
                      } catch (err: any) {
                        toast.error(err?.response?.data?.detail || 'No se pudo activar')
                      } finally {
                        setActivatingModule(null)
                      }
                    }}
                    disabled={busy}
                    style={{
                      background: 'var(--p-teal)',
                      color: 'var(--dax-on-accent)',
                      fontWeight: 700,
                      border: 'none',
                      padding: '6px 12px',
                      borderRadius: 4,
                      fontSize: 11,
                      cursor: busy ? 'wait' : 'pointer',
                      opacity: busy ? 0.6 : 1,
                      marginTop: 'auto',
                    }}
                  >
                    <i className="fa-solid fa-plus" style={{ marginRight: 6 }} />
                    {busy ? 'Activando...' : 'Activar'}
                  </button>
                </div>
              )
            })}
          </div>
        )}
      </section>

      {/* ── Sección Preset ────────────────────────────────────────────── */}
      <section style={card}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12, flexWrap: 'wrap', gap: 8 }}>
          <p style={sectionTitle}>Preset de industria</p>
          <span style={{ fontSize: 11, color: 'var(--p-muted)' }}>
            Actual: <strong style={{ color: 'var(--p-text)' }}>{org.industry_type || '—'}</strong>
          </span>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(220px, 320px) 1fr', gap: 16, alignItems: 'start' }}>
          <div>
            <label style={labelStyle}>Seleccionar preset</label>
            <select
              value={selectedPresetId ?? ''}
              onChange={(e) => setSelectedPresetId(Number(e.target.value) || null)}
              style={inputStyle}
            >
              {presets.length === 0 && <option value="">Sin presets disponibles</option>}
              {presets.map(p => (
                <option key={p.id} value={p.id}>
                  {p.display_name} ({p.industry_type})
                </option>
              ))}
            </select>
            {selectedPreset?.description && (
              <p style={{ fontSize: 11, color: 'var(--p-muted)', margin: '8px 0 0' }}>
                {selectedPreset.description}
              </p>
            )}
          </div>

          <div>
            <label style={labelStyle}>Módulos que se activarán ({selectedPreset?.modules.length ?? 0})</label>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {(selectedPreset?.modules ?? []).map(k => {
                const cat = catalogByKey.get(k)
                const isBeta = (cat?.status || '').toUpperCase() === 'BETA'
                return (
                  <span
                    key={k}
                    style={{
                      background: 'rgba(0,201,177,0.10)',
                      color: 'var(--p-teal)',
                      border: '1px solid rgba(0,201,177,0.3)',
                      padding: '3px 8px',
                      borderRadius: 999,
                      fontSize: 11,
                      fontFamily: 'monospace',
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: 4,
                    }}
                  >
                    {k}
                    {isBeta && <i className="fa-solid fa-flask" style={{ fontSize: 9, color: 'var(--p-warning)' }} title="BETA" />}
                  </span>
                )
              })}
              {(selectedPreset?.modules.length ?? 0) === 0 && (
                <span style={{ color: 'var(--p-muted)', fontSize: 12 }}>Preset vacío</span>
              )}
            </div>
            {willDeactivate.length > 0 && (
              <div style={{
                marginTop: 12, padding: 10, borderRadius: 4,
                background: 'rgba(245,158,11,0.06)', border: '1px solid rgba(245,158,11,0.3)',
              }}>
                <p style={{ fontSize: 11, color: 'var(--p-warning)', fontWeight: 600, margin: '0 0 6px' }}>
                  <i className="fa-solid fa-triangle-exclamation" style={{ marginRight: 6 }} />
                  Módulos que se desactivarán ({willDeactivate.length}):
                </p>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                  {willDeactivate.map(k => (
                    <span key={k} style={{
                      fontFamily: 'monospace', fontSize: 11,
                      color: 'var(--p-warning)', background: 'rgba(245,158,11,0.10)',
                      border: '1px solid rgba(245,158,11,0.3)',
                      padding: '2px 6px', borderRadius: 4,
                    }}>{k}</span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>

        <div style={{ display: 'flex', gap: 8, marginTop: 16, flexWrap: 'wrap' }}>
          <button
            onClick={triggerApplyPreset}
            disabled={!selectedPreset || applyingPreset}
            style={{ ...buttonPrimary, opacity: !selectedPreset || applyingPreset ? 0.5 : 1 }}
          >
            <i className="fa-solid fa-wand-magic-sparkles" />
            {applyingPreset ? 'Aplicando…' : 'Aplicar preset'}
          </button>
          <button
            onClick={() => setResetConfirmOpen(true)}
            style={buttonSecondary}
          >
            <i className="fa-solid fa-rotate-left" /> Reset preset
          </button>
        </div>
      </section>

      {/* ── Tabs Sucursales / Usuarios ────────────────────────────────── */}
      <section style={{ ...card, padding: 0, overflow: 'hidden' }}>
        <div style={{
          display: 'flex',
          borderBottom: '1px solid var(--p-border)',
          background: 'var(--p-surface)',
        }}>
          {([
            { key: 'branches', label: `Sucursales (${counts.branches})`, icon: 'fa-store' },
            { key: 'users', label: `Usuarios (${counts.users})`, icon: 'fa-users' },
          ] as { key: Tab; label: string; icon: string }[]).map(t => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              style={{
                background: 'transparent',
                color: tab === t.key ? 'var(--p-teal)' : 'var(--p-muted)',
                border: 'none',
                borderBottom: `2px solid ${tab === t.key ? 'var(--p-teal)' : 'transparent'}`,
                padding: '12px 18px',
                fontSize: 12,
                fontWeight: 600,
                cursor: 'pointer',
                textTransform: 'uppercase',
                letterSpacing: '0.06em',
                display: 'inline-flex',
                alignItems: 'center',
                gap: 6,
              }}
            >
              <i className={`fa-solid ${t.icon}`} />
              {t.label}
            </button>
          ))}
          <div style={{ flex: 1 }} />
          <Link
            to={tab === 'branches' ? `/platform/branches?org=${id}` : `/platform/users?org=${id}`}
            style={{
              alignSelf: 'center',
              marginRight: 12,
              fontSize: 11,
              color: 'var(--p-cyan)',
              textDecoration: 'none',
              fontWeight: 600,
              textTransform: 'uppercase',
              letterSpacing: '0.06em',
            }}
          >
            Ver todos <i className="fa-solid fa-arrow-right" style={{ marginLeft: 4 }} />
          </Link>
        </div>

        {tab === 'branches' && (
          <TablaDesplazable>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead style={{ background: 'var(--p-surface-2)' }}>
                <tr>
                  <th style={tableHeadCell}>Sucursal</th>
                  <th style={tableHeadCell}>Tipo</th>
                  <th style={tableHeadCell}>Dirección</th>
                  <th style={tableHeadCell}>Estado</th>
                </tr>
              </thead>
              <tbody>
                {branches.length === 0 ? (
                  <tr><td colSpan={4} style={{ ...tableCell, textAlign: 'center', color: 'var(--p-muted)', padding: '2rem' }}>Sin sucursales</td></tr>
                ) : branches.map(b => (
                  <tr key={b.id}>
                    <td style={tableCell}>
                      <div style={{ fontWeight: 600 }}>{b.name}</div>
                      <div style={{ fontSize: 11, color: 'var(--p-muted)', fontFamily: 'monospace' }}>#{b.id}</div>
                    </td>
                    <td style={tableCell}>
                      <span style={{
                        background: 'var(--p-surface-2)',
                        color: 'var(--p-text)',
                        padding: '2px 8px',
                        borderRadius: 4,
                        fontFamily: 'monospace',
                        fontSize: 11,
                      }}>{b.branch_type}</span>
                    </td>
                    <td style={{ ...tableCell, color: 'var(--p-muted)' }}>{b.address || '—'}</td>
                    <td style={tableCell}>
                      {b.is_active ? <StatusBadge status="active" /> : <StatusBadge status="inactive" />}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TablaDesplazable>
        )}

        {tab === 'users' && (
          <TablaDesplazable>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead style={{ background: 'var(--p-surface-2)' }}>
                <tr>
                  <th style={tableHeadCell}>Usuario</th>
                  <th style={tableHeadCell}>Rol</th>
                  <th style={tableHeadCell}>Email</th>
                  <th style={tableHeadCell}>Estado</th>
                </tr>
              </thead>
              <tbody>
                {users.length === 0 ? (
                  <tr><td colSpan={4} style={{ ...tableCell, textAlign: 'center', color: 'var(--p-muted)', padding: '2rem' }}>Sin usuarios</td></tr>
                ) : users.map(u => (
                  <tr key={u.id}>
                    <td style={tableCell}>
                      <div style={{ fontWeight: 600 }}>{u.full_name || u.username}</div>
                      <div style={{ fontSize: 11, color: 'var(--p-muted)', fontFamily: 'monospace' }}>@{u.username}</div>
                    </td>
                    <td style={tableCell}>
                      <span style={{
                        background: 'var(--p-surface-2)',
                        color: 'var(--p-text)',
                        padding: '2px 8px',
                        borderRadius: 4,
                        fontFamily: 'monospace',
                        fontSize: 11,
                      }}>{u.role}</span>
                    </td>
                    <td style={{ ...tableCell, color: 'var(--p-muted)' }}>{u.email || '—'}</td>
                    <td style={tableCell}>
                      {u.is_active ? <StatusBadge status="active" /> : <StatusBadge status="inactive" />}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TablaDesplazable>
        )}
      </section>

      {/* ── Danger Zone ───────────────────────────────────────────────── */}
      <section style={{
        background: 'rgba(239,68,68,0.05)',
        border: '1px solid var(--p-danger)',
        borderRadius: 6,
        padding: '1rem 1.25rem',
      }}>
        <p style={{
          ...sectionTitle,
          color: 'var(--p-danger)',
          margin: '0 0 12px',
        }}>
          <i className="fa-solid fa-triangle-exclamation" style={{ marginRight: 8 }} />
          Zona peligrosa
        </p>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 12 }}>
          {/* Archive */}
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            gap: 12, padding: '10px 0', borderBottom: '1px solid rgba(239,68,68,0.15)',
          }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--p-text)' }}>Archivar organización</div>
              <div style={{ fontSize: 12, color: 'var(--p-muted)', marginTop: 2 }}>
                Queda oculta por default y se puede restaurar después. No elimina datos.
              </div>
            </div>
            <button onClick={() => setArchiveOpen(true)} style={buttonDanger} disabled={!org.is_active}>
              <i className="fa-solid fa-box-archive" />
              {org.is_active ? 'Archivar' : 'Ya archivada'}
            </button>
          </div>

          {/* Reset config (placeholder) */}
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            gap: 12, padding: '10px 0', borderBottom: '1px solid rgba(239,68,68,0.15)',
          }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--p-text)' }}>Reset de configuración</div>
              <div style={{ fontSize: 12, color: 'var(--p-muted)', marginTop: 2 }}>
                Limpia toda la configuración (presets, módulos, parámetros). <em>TODO backend.</em>
              </div>
            </div>
            <button
              onClick={() => {
                console.warn('[PlatformOrgDetail] Reset configuración solicitado para org', id, '— endpoint dedicado pendiente.')
                toast.warning('TODO backend: endpoint de reset de configuración aún no existe')
              }}
              style={buttonDanger}
            >
              <i className="fa-solid fa-rotate-left" /> Reset config
            </button>
          </div>

          {/* Delete */}
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            gap: 12, padding: '10px 0',
          }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--p-text)' }}>Eliminar permanentemente</div>
              <div style={{ fontSize: 12, color: 'var(--p-muted)', marginTop: 2 }}>
                Borra la organización y todos sus datos asociados. <strong style={{ color: 'var(--p-danger)' }}>No reversible.</strong>
              </div>
            </div>
            <button onClick={openDelete} style={buttonDanger}>
              <i className="fa-solid fa-trash" /> Eliminar
            </button>
          </div>
        </div>
      </section>

      {/* ── Edit drawer ───────────────────────────────────────────────── */}
      <SideDrawer
        open={editOpen}
        title={`Editar ${org.name}`}
        onClose={() => setEditOpen(false)}
        onSave={handleSaveEdit}
        saving={savingEdit}
        saveLabel="Guardar"
      >
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <div style={{ gridColumn: '1 / -1' }}>
            <label style={labelStyle}>Nombre comercial *</label>
            <input value={editForm.name} onChange={e => setEditForm({ ...editForm, name: e.target.value })} required style={inputStyle} />
          </div>
          <div>
            <label style={labelStyle}>Razón social</label>
            <input value={editForm.legal_name} onChange={e => setEditForm({ ...editForm, legal_name: e.target.value })} style={inputStyle} />
          </div>
          <div>
            <label style={labelStyle}>RFC</label>
            <input value={editForm.tax_id} onChange={e => setEditForm({ ...editForm, tax_id: e.target.value })} style={inputStyle} />
          </div>
          <div>
            <label style={labelStyle}>Email</label>
            <input type="email" value={editForm.email} onChange={e => setEditForm({ ...editForm, email: e.target.value })} style={inputStyle} />
          </div>
          <div>
            <label style={labelStyle}>Teléfono</label>
            <input value={editForm.phone} onChange={e => setEditForm({ ...editForm, phone: e.target.value })} style={inputStyle} />
          </div>
          <div style={{ gridColumn: '1 / -1' }}>
            <label style={labelStyle}>Dirección</label>
            <input value={editForm.address} onChange={e => setEditForm({ ...editForm, address: e.target.value })} style={inputStyle} />
          </div>
          <div>
            <label style={labelStyle}>Timezone</label>
            <input value={editForm.timezone} onChange={e => setEditForm({ ...editForm, timezone: e.target.value })} style={inputStyle} />
          </div>
        </div>
      </SideDrawer>

      {/* ── Apply preset confirms ─────────────────────────────────────── */}
      <SimpleConfirm
        open={applySimpleConfirm}
        title={`Aplicar preset "${selectedPreset?.display_name ?? ''}"`}
        message={
          <>
            Se habilitarán {selectedPreset?.modules.length ?? 0} módulos del preset
            <strong style={{ color: 'var(--p-text)' }}> {selectedPreset?.industry_type}</strong>.
            Ningún módulo activo será desactivado.
          </>
        }
        confirmLabel={applyingPreset ? 'Aplicando…' : 'Aplicar'}
        busy={applyingPreset}
        onClose={() => setApplySimpleConfirm(false)}
        onConfirm={doApplyPreset}
      />

      <ConfirmModal
        open={applyTypedConfirm}
        title="Aplicar preset y desactivar módulos"
        message={`Esta acción desactivará ${willDeactivate.length} módulo(s) actualmente habilitados que no están en el preset "${selectedPreset?.display_name ?? ''}": ${willDeactivate.join(', ')}. Para confirmar, escribe DESACTIVAR.`}
        resourceName="DESACTIVAR"
        destructive
        busy={applyingPreset}
        onClose={() => setApplyTypedConfirm(false)}
        onConfirm={doApplyPreset}
      />

      <SimpleConfirm
        open={resetConfirmOpen}
        title="Resetear preset"
        message={
          <>
            Esto limpiará <strong style={{ color: 'var(--p-text)' }}>industry_type</strong> y
            <strong style={{ color: 'var(--p-text)' }}> todos los módulos habilitados</strong> de
            <strong style={{ color: 'var(--p-text)' }}> {org.name}</strong>. El siguiente login del admin entrará al
            flujo de bienvenida.
          </>
        }
        confirmLabel={resettingPreset ? 'Reseteando…' : 'Confirmar reset'}
        destructive
        busy={resettingPreset}
        onClose={() => setResetConfirmOpen(false)}
        onConfirm={doResetPreset}
      />

      {/* ── Archive confirm (typed-name) ──────────────────────────────── */}
      <ConfirmModal
        open={archiveOpen}
        title={`Archivar ${org.name}`}
        message="La organización quedará oculta por default. No se eliminan datos y puede restaurarse después."
        resourceName={org.name}
        destructive
        busy={archiving}
        onClose={() => setArchiveOpen(false)}
        onConfirm={doArchive}
      />

      {/* ── Delete deps blocker ───────────────────────────────────────── */}
      <DepsBlockedModal
        open={depsBlockedOpen}
        orgName={org.name}
        deps={deleteDeps}
        canArchive={org.is_active}
        onArchive={() => { setDepsBlockedOpen(false); setArchiveOpen(true) }}
        onClose={() => setDepsBlockedOpen(false)}
      />

      {/* ── Delete confirm (typed-name) ───────────────────────────────── */}
      <ConfirmModal
        open={deleteOpen}
        title={`Eliminar ${org.name}`}
        message="Esta acción es permanente y no reversible. Se eliminará la organización y toda su configuración."
        resourceName={org.name}
        destructive
        busy={deleting}
        onClose={() => setDeleteOpen(false)}
        onConfirm={doDelete}
      />

      {/* ── Impersonation modal ───────────────────────────────────────── */}
      {impersonateOpen && (
        <div onClick={() => !impersonating && setImpersonateOpen(false)} style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)',
          zIndex: 1100, display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <div onClick={e => e.stopPropagation()} style={{
            background: 'var(--p-surface)', border: '1px solid var(--p-cyan)',
            borderRadius: 6, padding: 20, width: 460, maxWidth: '90vw',
          }}>
            <h3 style={{ margin: 0, color: 'var(--p-text)', fontSize: '1rem', fontWeight: 700 }}>
              <i className="fa-solid fa-eye" style={{ color: 'var(--p-cyan)', marginRight: 8 }} />
              Modo auditoría — {org.name}
            </h3>
            <p style={{ color: 'var(--p-muted)', fontSize: '0.85rem', margin: '8px 0' }}>
              Esta acción queda registrada en <code style={{ background: 'var(--p-surface-2)', padding: '1px 4px', borderRadius: 3 }}>PlatformAuditLog</code>.
              Tu sesión sigue siendo SUPERADMIN; accedes a la org vía <code style={{ background: 'var(--p-surface-2)', padding: '1px 4px', borderRadius: 3 }}>X-Organization-ID</code>.
            </p>
            <form onSubmit={handleImpersonate}>
              <label style={labelStyle}>Razón (mínimo 3 caracteres) *</label>
              <input
                value={impersonateReason}
                onChange={(e) => setImpersonateReason(e.target.value)}
                required
                minLength={3}
                placeholder="Ej. Soporte ticket #1234"
                style={inputStyle}
              />
              <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 16 }}>
                <button
                  type="button"
                  onClick={() => { setImpersonateOpen(false); setImpersonateReason('') }}
                  disabled={impersonating}
                  style={buttonSecondary}
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={impersonating}
                  style={{ ...buttonPrimary, background: 'var(--p-cyan)', opacity: impersonating ? 0.5 : 1 }}
                >
                  {impersonating ? 'Entrando…' : 'Entrar'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </PlatformPageShell>
  )
}
