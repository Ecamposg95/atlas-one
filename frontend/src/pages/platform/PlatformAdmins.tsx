import { useEffect, useMemo, useRef, useState } from 'react'
import {
  platformApi,
  PlatformAdminUser,
  PlatformAdminInviteResponse,
  AuditLog,
} from '../../api/platform'
import { toast } from '../../store/toastStore'
import { useAuthStore } from '../../store/authStore'
import { PlatformPageShell } from '../../components/platform/PlatformPageShell'
import { DataTable, DataTableColumn } from '../../components/platform/DataTable'
import { StatusBadge } from '../../components/platform/StatusBadge'
import { SideDrawer } from '../../components/platform/SideDrawer'
import { ConfirmModal } from '../../components/platform/ConfirmModal'

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

// ── Row actions menu ────────────────────────────────────────────────────────
function RowMenu({
  admin,
  onChangeRole,
  onRevoke,
  disableRevoke,
}: {
  admin: PlatformAdminUser
  onChangeRole: () => void
  onRevoke: () => void
  disableRevoke: boolean
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
  const dangerStyle: React.CSSProperties = {
    ...itemStyle,
    color: disableRevoke ? 'var(--p-hint)' : 'var(--p-danger)',
    cursor: disableRevoke ? 'not-allowed' : 'pointer',
  }

  return (
    <div ref={ref} style={{ position: 'relative', display: 'inline-block' }}>
      <button
        onClick={(e) => { e.stopPropagation(); setOpen((o) => !o) }}
        aria-label={`Acciones ${admin.username}`}
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
          <button style={itemStyle} onClick={() => { setOpen(false); onChangeRole() }}>
            <i className="fa-solid fa-user-shield" style={{ marginRight: 8, width: 12 }} /> Cambiar rol
          </button>
          <div style={{ borderTop: '1px solid var(--p-border)' }} />
          <button
            style={dangerStyle}
            disabled={disableRevoke}
            title={disableRevoke ? 'No puedes revocar tu propio acceso' : ''}
            onClick={() => { if (!disableRevoke) { setOpen(false); onRevoke() } }}
          >
            <i className="fa-solid fa-user-slash" style={{ marginRight: 8, width: 12 }} /> Revocar acceso
          </button>
        </div>
      )}
    </div>
  )
}

// ── Helpers ─────────────────────────────────────────────────────────────────
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

const roleBadge = (role: string) => {
  if (role === 'SUPERADMIN') return <StatusBadge status="superadmin" />
  if (role === 'SUPPORT') return <StatusBadge status="support" />
  return (
    <span style={{
      background: 'rgba(107,107,120,0.2)',
      color: 'var(--p-muted)',
      padding: '2px 8px',
      borderRadius: 4,
      fontSize: '0.65rem',
      fontWeight: 700,
      textTransform: 'uppercase',
      letterSpacing: '0.06em',
    }}>
      {role || 'NONE'}
    </span>
  )
}

// ── Page ────────────────────────────────────────────────────────────────────
export function PlatformAdmins() {
  const currentUser = useAuthStore((s) => s.user)
  const isSuper = currentUser?.platform_role === 'SUPERADMIN'

  // Data
  const [admins, setAdmins] = useState<PlatformAdminUser[]>([])
  const [loading, setLoading] = useState(true)

  // Invite drawer
  const [inviteOpen, setInviteOpen] = useState(false)
  const [inviteForm, setInviteForm] = useState<{ email: string; full_name: string; platform_role: string }>({
    email: '',
    full_name: '',
    platform_role: 'SUPPORT',
  })
  const [inviting, setInviting] = useState(false)

  // Temp password modal
  const [inviteResult, setInviteResult] = useState<PlatformAdminInviteResponse | null>(null)
  const [copyOk, setCopyOk] = useState(false)

  // Change-role drawer
  const [roleTarget, setRoleTarget] = useState<PlatformAdminUser | null>(null)
  const [roleValue, setRoleValue] = useState<string>('SUPPORT')
  const [savingRole, setSavingRole] = useState(false)

  // Revoke modal
  const [revokeTarget, setRevokeTarget] = useState<PlatformAdminUser | null>(null)
  const [revoking, setRevoking] = useState(false)

  // Manual create modal
  const [manualOpen, setManualOpen] = useState(false)
  const [manualForm, setManualForm] = useState<{
    email: string
    full_name: string
    platform_role: 'SUPERADMIN' | 'SUPPORT'
    password: string
    confirm_password: string
  }>({
    email: '',
    full_name: '',
    platform_role: 'SUPPORT',
    password: '',
    confirm_password: '',
  })
  const [manualCreating, setManualCreating] = useState(false)
  const [showManualPwd, setShowManualPwd] = useState(false)
  const [showManualConfirm, setShowManualConfirm] = useState(false)

  // Audit trail panel
  const [auditTarget, setAuditTarget] = useState<PlatformAdminUser | null>(null)
  const [auditLogs, setAuditLogs] = useState<AuditLog[]>([])
  const [auditLoading, setAuditLoading] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const data = await platformApi.listPlatformAdmins()
      setAdmins(data)
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'No se pudieron cargar los admins')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!isSuper) return
    load()
  }, [isSuper])

  // ── Invite ────────────────────────────────────────────────────────────────
  const openInvite = () => {
    setInviteForm({ email: '', full_name: '', platform_role: 'SUPPORT' })
    setInviteOpen(true)
  }

  const handleInvite = async () => {
    if (!inviteForm.email.trim()) {
      toast.error('Email es requerido')
      return
    }
    setInviting(true)
    try {
      const res = await platformApi.invitePlatformAdmin({
        email: inviteForm.email.trim(),
        full_name: inviteForm.full_name.trim() || undefined,
        platform_role: inviteForm.platform_role,
      })
      setInviteResult(res)
      setInviteOpen(false)
      toast.success(`Admin ${res.email} creado`)
      load()
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'No se pudo invitar al admin')
    } finally {
      setInviting(false)
    }
  }

  const copyTempPassword = async () => {
    if (!inviteResult) return
    try {
      await navigator.clipboard.writeText(inviteResult.temp_password)
      setCopyOk(true)
      setTimeout(() => setCopyOk(false), 1800)
    } catch {
      toast.error('No se pudo copiar al portapapeles')
    }
  }

  // ── Change role ───────────────────────────────────────────────────────────
  const openRole = (a: PlatformAdminUser) => {
    setRoleTarget(a)
    setRoleValue(a.platform_role)
  }

  const closeRole = () => {
    setRoleTarget(null)
    setSavingRole(false)
  }

  const handleSaveRole = async () => {
    if (!roleTarget) return
    if (roleValue === roleTarget.platform_role) {
      closeRole()
      return
    }
    setSavingRole(true)
    try {
      await platformApi.changePlatformAdminRole(roleTarget.id, roleValue)
      toast.success(`Rol actualizado a ${roleValue}`)
      closeRole()
      load()
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'No se pudo cambiar el rol')
    } finally {
      setSavingRole(false)
    }
  }

  // ── Revoke ────────────────────────────────────────────────────────────────
  const handleRevoke = async () => {
    if (!revokeTarget) return
    setRevoking(true)
    try {
      await platformApi.revokePlatformAdmin(revokeTarget.id)
      toast.success(`Acceso revocado a ${revokeTarget.username}`)
      setRevokeTarget(null)
      load()
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'No se pudo revocar el acceso')
    } finally {
      setRevoking(false)
    }
  }

  // ── Manual create ─────────────────────────────────────────────────────────
  const manualEmailValid = useMemo(
    () => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(manualForm.email.trim()),
    [manualForm.email],
  )
  const manualPwdValid = useMemo(
    () =>
      manualForm.password.length >= 8 &&
      /[a-zA-Z]/.test(manualForm.password) &&
      /[0-9]/.test(manualForm.password),
    [manualForm.password],
  )
  const manualMatch = useMemo(
    () =>
      manualForm.password.length > 0 &&
      manualForm.password === manualForm.confirm_password,
    [manualForm.password, manualForm.confirm_password],
  )
  const manualCanSubmit =
    manualEmailValid && manualPwdValid && manualMatch && !manualCreating

  const manualStrengthScore = useMemo(() => {
    const pwd = manualForm.password
    let score = 0
    if (pwd.length >= 8) score += 1
    if (/[a-zA-Z]/.test(pwd)) score += 1
    if (/[0-9]/.test(pwd)) score += 1
    if (pwd.length >= 12) score += 1
    return score
  }, [manualForm.password])

  const manualStrengthLabel =
    manualStrengthScore <= 1 ? 'Débil' : manualStrengthScore >= 4 ? 'Fuerte' : 'Buena'
  const manualStrengthColor =
    manualStrengthScore <= 1
      ? 'var(--p-danger)'
      : manualStrengthScore >= 4
        ? 'var(--p-success)'
        : 'var(--p-warning)'

  const resetManualForm = () => {
    setManualForm({
      email: '',
      full_name: '',
      platform_role: 'SUPPORT',
      password: '',
      confirm_password: '',
    })
    setShowManualPwd(false)
    setShowManualConfirm(false)
  }

  const openManual = () => {
    resetManualForm()
    setManualOpen(true)
  }

  const closeManual = () => {
    setManualOpen(false)
    resetManualForm()
  }

  const handleManualCreate = async () => {
    setManualCreating(true)
    try {
      await platformApi.createPlatformAdminManual({
        email: manualForm.email.trim(),
        full_name: manualForm.full_name.trim() || undefined,
        platform_role: manualForm.platform_role,
        password: manualForm.password,
      })
      toast.success(`Admin ${manualForm.email.trim()} creado`)
      setManualOpen(false)
      resetManualForm()
      await load()
    } catch (err: any) {
      const detail = err?.response?.data?.detail
      toast.error(typeof detail === 'string' && detail.trim() ? detail : 'Error al crear admin')
    } finally {
      setManualCreating(false)
    }
  }

  // ── Audit trail ───────────────────────────────────────────────────────────
  const openAudit = async (a: PlatformAdminUser) => {
    setAuditTarget(a)
    setAuditLogs([])
    setAuditLoading(true)
    try {
      const res = await platformApi.getAuditLogs({ actor_user_id: a.id, limit: 50 })
      setAuditLogs(res.items)
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'No se pudo cargar el audit trail')
    } finally {
      setAuditLoading(false)
    }
  }

  // ── 403 panel for non-SUPERADMIN ──────────────────────────────────────────
  if (!isSuper) {
    return (
      <PlatformPageShell breadcrumb="Platform / Admins" title="Acceso restringido">
        <div style={{
          background: 'var(--p-surface)',
          border: '1px solid var(--p-border)',
          borderTop: '2px solid var(--p-danger)',
          borderRadius: 6,
          padding: '2.5rem',
          textAlign: 'center',
        }}>
          <i className="fa-solid fa-lock" style={{ fontSize: 32, color: 'var(--p-danger)', marginBottom: 12 }} />
          <h2 style={{
            fontSize: '1.1rem',
            color: 'var(--p-text)',
            fontWeight: 700,
            margin: '0 0 8px',
          }}>
            Acceso restringido
          </h2>
          <p style={{ color: 'var(--p-muted)', fontSize: 13, margin: 0, maxWidth: 520, marginInline: 'auto' }}>
            Solo SUPERADMIN puede gestionar admins. Usuarios SUPPORT no tienen acceso a este módulo.
          </p>
        </div>
      </PlatformPageShell>
    )
  }

  // ── Table columns ─────────────────────────────────────────────────────────
  const columns: DataTableColumn<PlatformAdminUser>[] = [
    {
      key: 'name',
      label: 'Nombre',
      sortable: true,
      sortValue: (a) => (a.full_name || a.username).toLowerCase(),
      accessor: (a) => (
        <div>
          <div style={{ fontWeight: 600, color: 'var(--p-text)' }}>{a.full_name || a.username}</div>
          <div style={{ fontSize: 11, color: 'var(--p-muted)', fontFamily: 'monospace' }}>@{a.username}</div>
        </div>
      ),
    },
    {
      key: 'email',
      label: 'Email',
      sortable: true,
      sortValue: (a) => (a.email || '').toLowerCase(),
      accessor: (a) => (
        <span style={{ color: 'var(--p-text)', fontSize: 13 }}>{a.email || '—'}</span>
      ),
    },
    {
      key: 'role',
      label: 'Rol',
      sortable: true,
      sortValue: (a) => a.platform_role,
      accessor: (a) => roleBadge(a.platform_role),
    },
    {
      key: 'status',
      label: 'Status',
      sortable: true,
      sortValue: (a) => (a.is_active ? 'active' : 'inactive'),
      accessor: (a) => (a.is_active ? <StatusBadge status="active" /> : <StatusBadge status="inactive" />),
    },
    {
      key: 'last_login',
      label: 'Última sesión',
      sortable: true,
      sortValue: (a) => a.last_login ?? '',
      accessor: (a) => fmtDate(a.last_login),
    },
    {
      key: 'actions',
      label: '',
      width: '60px',
      accessor: (a) => (
        <div onClick={(e) => e.stopPropagation()}>
          <RowMenu
            admin={a}
            onChangeRole={() => openRole(a)}
            onRevoke={() => setRevokeTarget(a)}
            disableRevoke={a.id === currentUser?.id}
          />
        </div>
      ),
    },
  ]

  const csvRow = (a: PlatformAdminUser) => ({
    id: a.id,
    nombre: a.full_name || '',
    username: a.username,
    email: a.email || '',
    platform_role: a.platform_role,
    is_active: a.is_active ? 'true' : 'false',
    last_login: a.last_login || '',
  })

  const headerActions = (
    <div style={{ display: 'inline-flex', gap: 8 }}>
      <button onClick={openManual} style={buttonSecondary}>
        <i className="fa-solid fa-user-pen" style={{ marginRight: 6 }} /> Crear admin manualmente
      </button>
      <button onClick={openInvite} style={buttonPrimary}>
        <i className="fa-solid fa-user-plus" /> Invitar admin
      </button>
    </div>
  )

  return (
    <PlatformPageShell
      breadcrumb="Platform / Admins"
      title="Administradores de la plataforma"
      actions={headerActions}
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
          <p style={{ marginTop: 12, fontSize: 13 }}>Cargando admins...</p>
        </div>
      ) : (
        <DataTable
          data={admins}
          columns={columns}
          rowKey={(a) => a.id}
          searchable
          searchKeys={(a) => `${a.full_name || ''} ${a.username} ${a.email || ''}`}
          pageSize={20}
          csvFilename="platform-admins.csv"
          csvRow={csvRow}
          onRowClick={openAudit}
          emptyMessage="Sin admins registrados"
        />
      )}

      {/* Invite drawer */}
      <SideDrawer
        open={inviteOpen}
        title="Invitar admin de plataforma"
        onClose={() => setInviteOpen(false)}
        onSave={handleInvite}
        saving={inviting}
        saveLabel="Invitar"
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div>
            <label style={labelStyle}>Email *</label>
            <input
              type="email"
              value={inviteForm.email}
              onChange={(e) => setInviteForm({ ...inviteForm, email: e.target.value })}
              placeholder="admin@empresa.com"
              required
              style={inputStyle}
            />
          </div>
          <div>
            <label style={labelStyle}>Nombre completo</label>
            <input
              value={inviteForm.full_name}
              onChange={(e) => setInviteForm({ ...inviteForm, full_name: e.target.value })}
              placeholder="(opcional)"
              style={inputStyle}
            />
          </div>
          <div>
            <label style={labelStyle}>Rol de plataforma</label>
            <select
              value={inviteForm.platform_role}
              onChange={(e) => setInviteForm({ ...inviteForm, platform_role: e.target.value })}
              style={inputStyle}
            >
              <option value="SUPPORT">SUPPORT</option>
              <option value="SUPERADMIN">SUPERADMIN</option>
            </select>
            <p style={{ fontSize: 11, color: 'var(--p-muted)', margin: '6px 0 0' }}>
              SUPPORT: lectura cross-tenant. SUPERADMIN: acceso total a /platform/*.
            </p>
          </div>
          <div style={{
            padding: 10,
            background: 'rgba(0,229,255,0.06)',
            border: '1px solid rgba(0,229,255,0.2)',
            borderRadius: 4,
            fontSize: 11,
            color: 'var(--p-cyan)',
          }}>
            <i className="fa-solid fa-circle-info" style={{ marginRight: 6 }} />
            Se generará un password temporal que deberás entregar manualmente al nuevo admin.
          </div>
        </div>
      </SideDrawer>

      {/* Temp password modal */}
      {inviteResult && (
        <div
          onClick={() => setInviteResult(null)}
          style={{
            position: 'fixed', inset: 0,
            background: 'rgba(0,0,0,0.7)',
            zIndex: 1100,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              background: 'var(--p-surface)',
              border: '1px solid var(--p-teal)',
              borderRadius: 6,
              padding: 20,
              width: 460,
              maxWidth: '90vw',
            }}
          >
            <h3 style={{ margin: 0, color: 'var(--p-text)', fontSize: '1rem', fontWeight: 700 }}>
              <i className="fa-solid fa-key" style={{ color: 'var(--p-teal)', marginRight: 8 }} />
              Password temporal generado
            </h3>
            <p style={{ color: 'var(--p-muted)', fontSize: '0.85rem', margin: '8px 0 12px' }}>
              Entrega este password manualmente a <strong style={{ color: 'var(--p-text)' }}>{inviteResult.email}</strong>.
              Por seguridad no se mostrará de nuevo.
            </p>
            <div style={{
              padding: '12px 14px',
              background: 'var(--p-surface-2)',
              border: '1px solid var(--p-border)',
              borderRadius: 4,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 8,
              marginBottom: 14,
            }}>
              <code style={{
                color: 'var(--p-teal)',
                fontFamily: 'monospace',
                fontSize: 14,
                fontWeight: 700,
                wordBreak: 'break-all',
              }}>
                {inviteResult.temp_password}
              </code>
              <button
                onClick={copyTempPassword}
                style={{
                  background: copyOk ? 'var(--p-success)' : 'var(--p-teal)',
                  color: copyOk ? '#000' : 'var(--dax-on-accent)',
                  fontWeight: 700,
                  border: 'none',
                  padding: '6px 12px',
                  borderRadius: 4,
                  fontSize: 12,
                  cursor: 'pointer',
                  whiteSpace: 'nowrap',
                }}
              >
                <i className={`fa-solid ${copyOk ? 'fa-check' : 'fa-copy'}`} style={{ marginRight: 6 }} />
                {copyOk ? 'Copiado' : 'Copiar'}
              </button>
            </div>
            <div style={{
              padding: 10,
              background: 'rgba(245,158,11,0.06)',
              border: '1px solid rgba(245,158,11,0.2)',
              borderRadius: 4,
              fontSize: 11,
              color: 'var(--p-warning)',
              marginBottom: 14,
            }}>
              <i className="fa-solid fa-triangle-exclamation" style={{ marginRight: 6 }} />
              Este password no se almacena en texto plano. Si lo cierras sin copiarlo, deberás
              generar uno nuevo desde la sección de usuarios.
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <button onClick={() => setInviteResult(null)} style={buttonPrimary}>
                Listo
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Manual create modal */}
      {manualOpen && (
        <div
          onClick={closeManual}
          style={{
            position: 'fixed', inset: 0,
            background: 'rgba(0,0,0,0.7)',
            zIndex: 1100,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              background: 'var(--p-bg-elevated, var(--p-surface))',
              border: '1px solid var(--p-border)',
              borderTop: '2px solid var(--p-success)',
              borderRadius: 6,
              padding: 20,
              width: 480,
              maxWidth: '92vw',
              maxHeight: '90vh',
              overflowY: 'auto',
            }}
          >
            <div style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              marginBottom: 14,
            }}>
              <h3 style={{ margin: 0, color: 'var(--p-text)', fontSize: '1rem', fontWeight: 700 }}>
                <i className="fa-solid fa-user-pen" style={{ color: 'var(--p-success)', marginRight: 8 }} />
                Crear admin manualmente
              </h3>
              <button
                onClick={closeManual}
                aria-label="Cerrar"
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: 'var(--p-muted)',
                  fontSize: 18,
                  cursor: 'pointer',
                  lineHeight: 1,
                }}
              >
                ×
              </button>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div>
                <label style={labelStyle}>Email *</label>
                <input
                  type="email"
                  value={manualForm.email}
                  onChange={(e) => setManualForm({ ...manualForm, email: e.target.value })}
                  placeholder="admin@empresa.com"
                  style={inputStyle}
                  autoFocus
                />
                {manualForm.email.length > 0 && !manualEmailValid && (
                  <p style={{ color: 'var(--p-danger)', fontSize: 11, margin: '4px 0 0' }}>
                    <i className="fa-solid fa-circle-xmark" style={{ marginRight: 4 }} />
                    Formato de email inválido
                  </p>
                )}
              </div>

              <div>
                <label style={labelStyle}>Nombre completo</label>
                <input
                  value={manualForm.full_name}
                  onChange={(e) => setManualForm({ ...manualForm, full_name: e.target.value })}
                  placeholder="(opcional)"
                  style={inputStyle}
                />
              </div>

              <div>
                <label style={labelStyle}>Rol de plataforma</label>
                <select
                  value={manualForm.platform_role}
                  onChange={(e) =>
                    setManualForm({
                      ...manualForm,
                      platform_role: e.target.value as 'SUPERADMIN' | 'SUPPORT',
                    })
                  }
                  style={inputStyle}
                >
                  <option value="SUPPORT">SUPPORT</option>
                  <option value="SUPERADMIN">SUPERADMIN</option>
                </select>
                <p style={{ fontSize: 11, color: 'var(--p-muted)', margin: '6px 0 0' }}>
                  SUPPORT: lectura cross-tenant. SUPERADMIN: acceso total a /platform/*.
                </p>
              </div>

              <div>
                <label style={labelStyle}>Password *</label>
                <div style={{ position: 'relative' }}>
                  <input
                    type={showManualPwd ? 'text' : 'password'}
                    value={manualForm.password}
                    onChange={(e) => setManualForm({ ...manualForm, password: e.target.value })}
                    placeholder="••••••••"
                    style={{ ...inputStyle, paddingRight: 56 }}
                  />
                  <button
                    type="button"
                    onClick={() => setShowManualPwd((s) => !s)}
                    style={{
                      position: 'absolute',
                      right: 6,
                      top: '50%',
                      transform: 'translateY(-50%)',
                      background: 'transparent',
                      border: 'none',
                      color: 'var(--p-muted)',
                      fontSize: 11,
                      cursor: 'pointer',
                      padding: '4px 6px',
                    }}
                  >
                    {showManualPwd ? 'ocultar' : 'ver'}
                  </button>
                </div>
                {/* Strength bar */}
                {manualForm.password.length > 0 && (
                  <div style={{ marginTop: 6 }}>
                    <div style={{
                      height: 4,
                      background: 'var(--p-surface-2)',
                      borderRadius: 2,
                      overflow: 'hidden',
                    }}>
                      <div style={{
                        width: `${(manualStrengthScore / 4) * 100}%`,
                        height: '100%',
                        background: manualStrengthColor,
                        transition: 'width 120ms ease',
                      }} />
                    </div>
                    <div style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      marginTop: 4,
                    }}>
                      <span style={{ fontSize: 11, color: 'var(--p-muted)' }}>
                        Fortaleza:{' '}
                        <span style={{ color: manualStrengthColor, fontWeight: 600 }}>
                          {manualStrengthLabel}
                        </span>
                      </span>
                      <span style={{ fontSize: 11, color: 'var(--p-muted)' }}>
                        Min 8 · 1 letra · 1 número
                      </span>
                    </div>
                  </div>
                )}
              </div>

              <div>
                <label style={labelStyle}>Confirmar password *</label>
                <div style={{ position: 'relative' }}>
                  <input
                    type={showManualConfirm ? 'text' : 'password'}
                    value={manualForm.confirm_password}
                    onChange={(e) =>
                      setManualForm({ ...manualForm, confirm_password: e.target.value })
                    }
                    placeholder="••••••••"
                    style={{ ...inputStyle, paddingRight: 56 }}
                  />
                  <button
                    type="button"
                    onClick={() => setShowManualConfirm((s) => !s)}
                    style={{
                      position: 'absolute',
                      right: 6,
                      top: '50%',
                      transform: 'translateY(-50%)',
                      background: 'transparent',
                      border: 'none',
                      color: 'var(--p-muted)',
                      fontSize: 11,
                      cursor: 'pointer',
                      padding: '4px 6px',
                    }}
                  >
                    {showManualConfirm ? 'ocultar' : 'ver'}
                  </button>
                </div>
                {manualForm.confirm_password.length > 0 && !manualMatch && (
                  <p style={{ color: 'var(--p-danger)', fontSize: 11, margin: '4px 0 0' }}>
                    <i className="fa-solid fa-circle-xmark" style={{ marginRight: 4 }} />
                    Las contraseñas no coinciden
                  </p>
                )}
              </div>

              <div style={{
                display: 'flex',
                justifyContent: 'flex-end',
                gap: 8,
                marginTop: 4,
              }}>
                <button onClick={closeManual} style={buttonSecondary} disabled={manualCreating}>
                  Cancelar
                </button>
                <button
                  onClick={handleManualCreate}
                  disabled={!manualCanSubmit}
                  style={{
                    ...buttonPrimary,
                    background: manualCanSubmit ? 'var(--p-success)' : 'var(--p-surface-2)',
                    color: manualCanSubmit ? '#000' : 'var(--p-muted)',
                    cursor: manualCanSubmit ? 'pointer' : 'not-allowed',
                  }}
                >
                  {manualCreating ? (
                    <>
                      <i className="fa-solid fa-spinner fa-spin" style={{ marginRight: 6 }} />
                      Creando...
                    </>
                  ) : (
                    <>
                      <i className="fa-solid fa-user-plus" style={{ marginRight: 6 }} />
                      Crear admin
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Change-role mini drawer */}
      <SideDrawer
        open={!!roleTarget}
        title={roleTarget ? `Cambiar rol — ${roleTarget.full_name || roleTarget.username}` : 'Cambiar rol'}
        onClose={closeRole}
        onSave={handleSaveRole}
        saving={savingRole}
        saveLabel="Guardar"
        width={380}
      >
        {roleTarget && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div>
              <label style={labelStyle}>Rol actual</label>
              <div>{roleBadge(roleTarget.platform_role)}</div>
            </div>
            <div>
              <label style={labelStyle}>Nuevo rol</label>
              <select
                value={roleValue}
                onChange={(e) => setRoleValue(e.target.value)}
                style={inputStyle}
              >
                <option value="SUPERADMIN">SUPERADMIN</option>
                <option value="SUPPORT">SUPPORT</option>
                <option value="NONE">NONE (revocar acceso de plataforma)</option>
              </select>
            </div>
            {roleValue === 'NONE' && (
              <div style={{
                padding: 10,
                background: 'rgba(239,68,68,0.06)',
                border: '1px solid rgba(239,68,68,0.2)',
                borderRadius: 4,
                fontSize: 11,
                color: 'var(--p-danger)',
              }}>
                <i className="fa-solid fa-triangle-exclamation" style={{ marginRight: 6 }} />
                NONE retira acceso a /platform/*. El usuario seguirá existiendo en su organización.
              </div>
            )}
          </div>
        )}
      </SideDrawer>

      {/* Revoke confirm */}
      <ConfirmModal
        open={!!revokeTarget}
        title={`Revocar acceso de plataforma — ${revokeTarget?.username ?? ''}`}
        message="El usuario perderá acceso a /platform/*. La cuenta seguirá existiendo en su organización pero su platform_role pasará a NONE."
        resourceName={revokeTarget?.username ?? ''}
        destructive
        busy={revoking}
        onClose={() => setRevokeTarget(null)}
        onConfirm={handleRevoke}
      />

      {/* Audit trail panel */}
      <SideDrawer
        open={!!auditTarget}
        title={auditTarget ? `Audit trail de ${auditTarget.full_name || auditTarget.username}` : 'Audit trail'}
        onClose={() => { setAuditTarget(null); setAuditLogs([]) }}
        width={520}
      >
        {auditTarget && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div style={{
              padding: 10,
              background: 'var(--p-surface-2)',
              border: '1px solid var(--p-border)',
              borderRadius: 4,
              fontSize: 12,
              color: 'var(--p-muted)',
            }}>
              <div>
                <strong style={{ color: 'var(--p-text)' }}>{auditTarget.full_name || auditTarget.username}</strong>
                {' '}· {roleBadge(auditTarget.platform_role)}
              </div>
              <div style={{ marginTop: 4, fontSize: 11 }}>
                Últimos 50 eventos registrados como actor.
              </div>
            </div>

            {auditLoading ? (
              <div style={{ textAlign: 'center', padding: 24, color: 'var(--p-muted)' }}>
                <i className="fa-solid fa-spinner fa-spin" />
                <p style={{ marginTop: 8, fontSize: 12 }}>Cargando logs...</p>
              </div>
            ) : auditLogs.length === 0 ? (
              <div style={{
                padding: 24,
                textAlign: 'center',
                color: 'var(--p-muted)',
                background: 'var(--p-surface-2)',
                border: '1px dashed var(--p-border)',
                borderRadius: 4,
                fontSize: 13,
              }}>
                Sin actividad registrada
              </div>
            ) : (
              <div style={{
                display: 'flex',
                flexDirection: 'column',
                gap: 6,
                maxHeight: '70vh',
                overflowY: 'auto',
              }}>
                {auditLogs.map((log) => (
                  <div
                    key={log.id}
                    style={{
                      padding: '10px 12px',
                      background: 'var(--p-surface-2)',
                      border: '1px solid var(--p-border)',
                      borderRadius: 4,
                      display: 'grid',
                      gridTemplateColumns: '1fr auto',
                      gap: 6,
                      alignItems: 'center',
                    }}
                  >
                    <div>
                      <div style={{
                        color: 'var(--p-text)',
                        fontSize: 12,
                        fontWeight: 600,
                        fontFamily: 'monospace',
                      }}>
                        {log.action}
                      </div>
                      <div style={{ color: 'var(--p-muted)', fontSize: 11, marginTop: 2 }}>
                        {log.entity_type}
                        {log.entity_id ? <span style={{ color: 'var(--p-cyan)' }}> #{log.entity_id}</span> : null}
                      </div>
                    </div>
                    <div style={{ color: 'var(--p-muted)', fontSize: 11, textAlign: 'right' }}>
                      {new Date(log.created_at).toLocaleString('es-MX', {
                        dateStyle: 'short',
                        timeStyle: 'short',
                      })}
                    </div>
                  </div>
                ))}
              </div>
            )}

            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 4 }}>
              <button
                onClick={() => { setAuditTarget(null); setAuditLogs([]) }}
                style={buttonSecondary}
              >
                Cerrar
              </button>
            </div>
          </div>
        )}
      </SideDrawer>
    </PlatformPageShell>
  )
}
