import { useEffect, useMemo, useRef, useState } from 'react'
import { platformApi, PlatformUser, PlatformOrg, PlatformBranch } from '../../api/platform'
import { useAuthStore } from '../../store/authStore'
import { toast } from '../../store/toastStore'
import { PlatformPageShell } from '../../components/platform/PlatformPageShell'
import { KPICard } from '../../components/platform/KPICard'
import { DataTable, DataTableColumn } from '../../components/platform/DataTable'
import { StatusBadge } from '../../components/platform/StatusBadge'
import { SideDrawer } from '../../components/platform/SideDrawer'
import { ConfirmModal } from '../../components/platform/ConfirmModal'

const ROLES = ['ADMINISTRADOR', 'DUEÑO', 'GERENTE', 'CAJERO', 'VENDEDOR', 'SOPORTE_OPERATIVO', 'CLIENTE']

type FormState = {
  username: string
  full_name: string
  email: string
  password: string
  role: string
  organization_id: string
  branch_id: string
  is_active: boolean
}

const EMPTY_FORM: FormState = {
  username: '',
  full_name: '',
  email: '',
  password: '',
  role: 'CAJERO',
  organization_id: '',
  branch_id: '',
  is_active: true,
}

// ── inline styles reusables (tokens) ────────────────────────────────────────
const inputStyle: React.CSSProperties = {
  width: '100%',
  background: 'var(--p-surface-2)',
  border: '1px solid var(--p-border)',
  color: 'var(--p-text)',
  padding: '8px 10px',
  borderRadius: 4,
  fontSize: 13,
  boxSizing: 'border-box',
  fontFamily: 'inherit',
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

const ghostBtn: React.CSSProperties = {
  background: 'var(--p-surface-2)',
  border: '1px solid var(--p-border)',
  color: 'var(--p-text)',
  padding: '6px 12px',
  borderRadius: 4,
  fontSize: 12,
  fontWeight: 600,
  cursor: 'pointer',
  fontFamily: 'inherit',
}

const primaryBtn: React.CSSProperties = {
  background: 'var(--p-teal)',
  color: 'var(--dax-on-accent)',
  fontWeight: 700,
  padding: '8px 16px',
  border: 'none',
  borderRadius: 4,
  fontSize: 12,
  cursor: 'pointer',
  fontFamily: 'inherit',
}

function maskEmail(email: string | null): string {
  if (!email) return '—'
  const [user, domain] = email.split('@')
  if (!domain) return email
  const visible = user.slice(0, 1)
  return `${visible}${'*'.repeat(Math.max(1, user.length - 1))}@${domain}`
}

export function PlatformUsers() {
  const currentUser = useAuthStore((s) => s.user)
  const isSuperAdmin = currentUser?.platform_role === 'SUPERADMIN'

  // Data
  const [users, setUsers] = useState<PlatformUser[]>([])
  const [orgs, setOrgs] = useState<PlatformOrg[]>([])
  const [branches, setBranches] = useState<PlatformBranch[]>([])
  const [loading, setLoading] = useState(true)

  // Filters
  const [filterOrg, setFilterOrg] = useState<string>('')
  const [filterRole, setFilterRole] = useState<string>('')
  const [filterStatus, setFilterStatus] = useState<'all' | 'active' | 'inactive'>('all')

  // Drawer (create/edit)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [editing, setEditing] = useState<PlatformUser | null>(null)
  const [form, setForm] = useState<FormState>(EMPTY_FORM)
  const [saving, setSaving] = useState(false)

  // Reset password
  const [resetTarget, setResetTarget] = useState<PlatformUser | null>(null)
  const [resettingBusy, setResettingBusy] = useState(false)
  const [resetResult, setResetResult] = useState<{ user: PlatformUser; pwd: string } | null>(null)
  const [resetCopied, setResetCopied] = useState(false)

  // Role drawer
  const [roleTarget, setRoleTarget] = useState<PlatformUser | null>(null)
  const [roleValue, setRoleValue] = useState<string>('CAJERO')
  const [roleSaving, setRoleSaving] = useState(false)

  // Delete
  const [delTarget, setDelTarget] = useState<PlatformUser | null>(null)
  const [deleting, setDeleting] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const [u, o, b] = await Promise.all([
        platformApi.getUsers({ include_inactive: true }),
        platformApi.getOrgs({ include_archived: true }),
        platformApi.getBranches(undefined, { include_archived: true }),
      ])
      setUsers(u)
      setOrgs(o)
      setBranches(b)
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'No se pudieron cargar los usuarios')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const orgName = (id: number | null) => orgs.find((o) => o.id === id)?.name || '—'
  const branchesForOrg = (orgId: number | null) =>
    orgId == null ? [] : branches.filter((b) => b.organization_id === orgId)

  // ── KPIs ────────────────────────────────────────────────────────────────
  const totalUsers = users.length
  const activeUsersCount = users.filter((u) => u.is_active).length
  const newThisMonth = useMemo(() => {
    const now = new Date()
    const firstOfMonth = new Date(now.getFullYear(), now.getMonth(), 1)
    return users.filter((u) => {
      if (!u.created_at) return false
      const d = new Date(u.created_at)
      return d >= firstOfMonth
    }).length
  }, [users])

  const roleCounts = useMemo(() => {
    const map: Record<string, number> = {}
    users.forEach((u) => { map[u.role] = (map[u.role] || 0) + 1 })
    return map
  }, [users])

  const rolesSummary = useMemo(() => {
    const order = ['ADMINISTRADOR', 'DUEÑO', 'GERENTE', 'CAJERO', 'VENDEDOR']
    const parts = order
      .filter((r) => roleCounts[r])
      .map((r) => `${r === 'ADMINISTRADOR' ? 'ADMIN' : r}: ${roleCounts[r]}`)
    return parts.join(' · ') || '—'
  }, [roleCounts])

  // ── Filtros aplicados ───────────────────────────────────────────────────
  const filteredUsers = useMemo(() => {
    return users.filter((u) => {
      if (filterOrg && String(u.organization_id ?? '') !== filterOrg) return false
      if (filterRole && u.role !== filterRole) return false
      if (filterStatus === 'active' && !u.is_active) return false
      if (filterStatus === 'inactive' && u.is_active) return false
      return true
    })
  }, [users, filterOrg, filterRole, filterStatus])

  // ── Formulario CRUD ─────────────────────────────────────────────────────
  const openCreate = () => {
    setEditing(null)
    setForm(EMPTY_FORM)
    setDrawerOpen(true)
  }

  const openEdit = (u: PlatformUser) => {
    setEditing(u)
    setForm({
      username: u.username,
      full_name: u.full_name || '',
      email: u.email || '',
      password: '',
      role: u.role,
      organization_id: u.organization_id != null ? String(u.organization_id) : '',
      branch_id: u.branch_id != null ? String(u.branch_id) : '',
      is_active: u.is_active,
    })
    setDrawerOpen(true)
  }

  const handleSave = async () => {
    if (!form.username.trim()) { toast.error('Username requerido'); return }
    if (!editing && (!form.password || form.password.length < 8)) {
      toast.error('Password requerido (mín. 8 caracteres)')
      return
    }
    setSaving(true)
    try {
      const basePayload = {
        username: form.username.trim(),
        full_name: form.full_name.trim() || null,
        email: form.email.trim() || null,
        role: form.role,
        organization_id: form.organization_id ? Number(form.organization_id) : null,
        branch_id: form.branch_id ? Number(form.branch_id) : null,
        is_active: form.is_active,
      }
      if (editing) {
        const payload: any = { ...basePayload }
        if (form.password) payload.password = form.password
        await platformApi.updateUser(editing.id, payload)
        toast.success(`Usuario "${form.username}" actualizado`)
      } else {
        await platformApi.createUser({ ...basePayload, password: form.password } as any)
        toast.success(`Usuario "${form.username}" creado`)
      }
      setDrawerOpen(false)
      setEditing(null)
      setForm(EMPTY_FORM)
      load()
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'No se pudo guardar el usuario')
    } finally {
      setSaving(false)
    }
  }

  // ── Reset password ──────────────────────────────────────────────────────
  const handleResetPassword = async () => {
    if (!resetTarget) return
    setResettingBusy(true)
    try {
      const r = await platformApi.resetUserPassword(resetTarget.id)
      setResetResult({ user: resetTarget, pwd: r.temp_password })
      setResetTarget(null)
      setResetCopied(false)
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'No se pudo resetear el password')
    } finally {
      setResettingBusy(false)
    }
  }

  const copyTempPassword = async () => {
    if (!resetResult) return
    try {
      await navigator.clipboard.writeText(resetResult.pwd)
      setResetCopied(true)
      setTimeout(() => setResetCopied(false), 2000)
    } catch {
      toast.error('No se pudo copiar al portapapeles')
    }
  }

  // ── Cambiar rol ─────────────────────────────────────────────────────────
  const openChangeRole = (u: PlatformUser) => {
    setRoleTarget(u)
    setRoleValue(u.role)
  }

  const handleChangeRole = async () => {
    if (!roleTarget) return
    if (roleValue === roleTarget.role) { setRoleTarget(null); return }
    setRoleSaving(true)
    try {
      await platformApi.changeUserRole(roleTarget.id, roleValue)
      toast.success(`Rol de "${roleTarget.username}" cambiado a ${roleValue}`)
      setRoleTarget(null)
      load()
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'No se pudo cambiar el rol')
    } finally {
      setRoleSaving(false)
    }
  }

  // ── Delete ──────────────────────────────────────────────────────────────
  const handleDelete = async () => {
    if (!delTarget) return
    setDeleting(true)
    try {
      await platformApi.deleteUser(delTarget.id)
      toast.success(`Usuario "${delTarget.username}" eliminado`)
      setDelTarget(null)
      load()
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'No se pudo eliminar')
    } finally {
      setDeleting(false)
    }
  }

  // ── Columnas DataTable ──────────────────────────────────────────────────
  const columns: DataTableColumn<PlatformUser>[] = [
    {
      key: 'name',
      label: 'Nombre',
      sortable: true,
      sortValue: (u) => (u.full_name || u.username).toLowerCase(),
      accessor: (u) => (
        <div>
          <div style={{ color: 'var(--p-text)', fontWeight: 600 }}>
            {u.full_name || u.username}
          </div>
          <div style={{ color: 'var(--p-muted)', fontSize: 11, fontFamily: 'monospace' }}>
            @{u.username}
          </div>
        </div>
      ),
    },
    {
      key: 'email',
      label: 'Email',
      sortable: true,
      sortValue: (u) => (u.email || '').toLowerCase(),
      accessor: (u) => (
        <span style={{ color: 'var(--p-muted)', fontSize: 12 }}>
          {isSuperAdmin ? (u.email || '—') : maskEmail(u.email)}
        </span>
      ),
    },
    {
      key: 'org',
      label: 'Org',
      sortable: true,
      sortValue: (u) => orgName(u.organization_id).toLowerCase(),
      accessor: (u) => (
        <span style={{ color: 'var(--p-text)', fontSize: 12 }}>
          {orgName(u.organization_id)}
        </span>
      ),
    },
    {
      key: 'role',
      label: 'Rol',
      sortable: true,
      sortValue: (u) => u.role,
      accessor: (u) => (
        <span style={{
          background: 'var(--p-surface-2)',
          color: 'var(--p-text)',
          padding: '2px 8px',
          borderRadius: 4,
          fontSize: 11,
          fontFamily: 'monospace',
          fontWeight: 600,
        }}>
          {u.role}
        </span>
      ),
    },
    {
      key: 'last_login',
      label: 'Última sesión',
      sortable: true,
      sortValue: (u) => u.last_login || '',
      accessor: (u) => (
        <span style={{ color: 'var(--p-muted)', fontSize: 12 }}>
          {u.last_login ? new Date(u.last_login).toLocaleString() : '—'}
        </span>
      ),
    },
    {
      key: 'status',
      label: 'Status',
      sortable: true,
      sortValue: (u) => (u.is_active ? 'a' : 'z'),
      accessor: (u) => <StatusBadge status={u.is_active ? 'active' : 'inactive'} />,
    },
    {
      key: 'actions',
      label: '',
      width: '110px',
      accessor: (u) => (
        <RowActions
          user={u}
          isSuperAdmin={isSuperAdmin}
          onEdit={() => openEdit(u)}
          onResetPassword={() => setResetTarget(u)}
          onChangeRole={() => openChangeRole(u)}
          onDelete={() => setDelTarget(u)}
        />
      ),
    },
  ]

  // ── Toolbar (filtros) ───────────────────────────────────────────────────
  const toolbar = (
    <>
      <select
        value={filterOrg}
        onChange={(e) => setFilterOrg(e.target.value)}
        style={{ ...inputStyle, width: 'auto', padding: '6px 10px', fontSize: 12 }}
      >
        <option value="">Todas las orgs</option>
        {orgs.map((o) => (
          <option key={o.id} value={o.id}>{o.name}</option>
        ))}
      </select>
      <select
        value={filterRole}
        onChange={(e) => setFilterRole(e.target.value)}
        style={{ ...inputStyle, width: 'auto', padding: '6px 10px', fontSize: 12 }}
      >
        <option value="">Todos los roles</option>
        {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
      </select>
      <select
        value={filterStatus}
        onChange={(e) => setFilterStatus(e.target.value as any)}
        style={{ ...inputStyle, width: 'auto', padding: '6px 10px', fontSize: 12 }}
      >
        <option value="all">Todos</option>
        <option value="active">Activos</option>
        <option value="inactive">Inactivos</option>
      </select>
    </>
  )

  // ── Render ──────────────────────────────────────────────────────────────
  return (
    <PlatformPageShell
      breadcrumb="Platform / Usuarios"
      title="Usuarios cross-tenant"
      actions={
        <button onClick={openCreate} style={primaryBtn}>
          <i className="fa-solid fa-plus" style={{ marginRight: 6 }} />
          Nuevo usuario
        </button>
      }
      kpis={
        <>
          <KPICard label="Total usuarios" value={totalUsers} accent="teal" icon="fa-users" />
          <KPICard
            label="Activos (proxy)"
            value={activeUsersCount}
            accent="cyan"
            icon="fa-bolt"
            delta="sin last_login en backend"
            deltaPositive
          />
          <KPICard label="Nuevos este mes" value={newThisMonth} accent="purple" icon="fa-user-plus" />
          <KPICard label="Roles" value={rolesSummary || '—'} accent="magenta" icon="fa-id-badge" />
        </>
      }
    >
      {loading ? (
        <div style={{
          padding: 48,
          textAlign: 'center',
          color: 'var(--p-muted)',
          background: 'var(--p-surface)',
          border: '1px solid var(--p-border)',
          borderRadius: 6,
        }}>
          Cargando usuarios...
        </div>
      ) : (
        <DataTable
          data={filteredUsers}
          columns={columns}
          rowKey={(u) => u.id}
          searchable
          searchKeys={(u) => `${u.full_name || ''} ${u.username} ${u.email || ''}`}
          pageSize={20}
          csvFilename="users.csv"
          csvRow={(u) => ({
            id: u.id,
            username: u.username,
            full_name: u.full_name || '',
            email: isSuperAdmin ? (u.email || '') : maskEmail(u.email),
            role: u.role,
            org: orgName(u.organization_id),
            last_login: u.last_login || '',
            is_active: u.is_active ? 'true' : 'false',
            created_at: u.created_at || '',
          })}
          toolbar={toolbar}
          emptyMessage="Sin usuarios"
        />
      )}

      {/* ── Drawer Create / Edit ─────────────────────────────────────────── */}
      <SideDrawer
        open={drawerOpen}
        title={editing ? `Editar @${editing.username}` : 'Nuevo usuario'}
        onClose={() => { setDrawerOpen(false); setEditing(null); setForm(EMPTY_FORM) }}
        onSave={handleSave}
        saveLabel={editing ? 'Guardar' : 'Crear'}
        saving={saving}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div>
            <label style={labelStyle}>Nombre completo</label>
            <input
              style={inputStyle}
              value={form.full_name}
              onChange={(e) => setForm({ ...form, full_name: e.target.value })}
            />
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div>
              <label style={labelStyle}>Username *</label>
              <input
                style={inputStyle}
                value={form.username}
                onChange={(e) => setForm({ ...form, username: e.target.value })}
                required
              />
            </div>
            <div>
              <label style={labelStyle}>Email</label>
              <input
                type="email"
                style={inputStyle}
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
              />
            </div>
          </div>
          {!editing && (
            <div>
              <label style={labelStyle}>Password * (mín. 8)</label>
              <input
                type="password"
                style={inputStyle}
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
                minLength={8}
                required
              />
            </div>
          )}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div>
              <label style={labelStyle}>Rol *</label>
              <select
                style={inputStyle}
                value={form.role}
                onChange={(e) => setForm({ ...form, role: e.target.value })}
              >
                {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
              </select>
            </div>
            <div>
              <label style={labelStyle}>Organización</label>
              <select
                style={inputStyle}
                value={form.organization_id}
                onChange={(e) => setForm({
                  ...form,
                  organization_id: e.target.value,
                  branch_id: '',
                })}
              >
                <option value="">— Sin org —</option>
                {orgs.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
              </select>
            </div>
          </div>
          <div>
            <label style={labelStyle}>Sucursal (opcional)</label>
            <select
              style={inputStyle}
              value={form.branch_id}
              onChange={(e) => setForm({ ...form, branch_id: e.target.value })}
              disabled={!form.organization_id}
            >
              <option value="">— Sin sucursal —</option>
              {branchesForOrg(form.organization_id ? Number(form.organization_id) : null).map((b) => (
                <option key={b.id} value={b.id}>{b.name}</option>
              ))}
            </select>
          </div>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--p-text)', fontSize: 13, cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={form.is_active}
              onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
            />
            Activo
          </label>
        </div>
      </SideDrawer>

      {/* ── Drawer cambiar rol ──────────────────────────────────────────── */}
      <SideDrawer
        open={!!roleTarget}
        title={roleTarget ? `Cambiar rol — @${roleTarget.username}` : ''}
        onClose={() => setRoleTarget(null)}
        onSave={handleChangeRole}
        saveLabel="Cambiar"
        saving={roleSaving}
        width={380}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div style={{ color: 'var(--p-muted)', fontSize: 12 }}>
            Rol actual:{' '}
            <span style={{
              color: 'var(--p-text)',
              fontFamily: 'monospace',
              background: 'var(--p-surface-2)',
              padding: '2px 8px',
              borderRadius: 4,
            }}>
              {roleTarget?.role}
            </span>
          </div>
          <div>
            <label style={labelStyle}>Nuevo rol</label>
            <select
              style={inputStyle}
              value={roleValue}
              onChange={(e) => setRoleValue(e.target.value)}
            >
              {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
          </div>
        </div>
      </SideDrawer>

      {/* ── Confirm reset password ──────────────────────────────────────── */}
      {resetTarget && (
        <div
          onClick={() => !resettingBusy && setResetTarget(null)}
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
              border: '1px solid var(--p-warning)',
              borderRadius: 6,
              padding: 20,
              width: 420,
              maxWidth: '90vw',
            }}
          >
            <h3 style={{ margin: 0, color: 'var(--p-text)', fontSize: '1rem', fontWeight: 700 }}>
              Reset password — @{resetTarget.username}
            </h3>
            <p style={{ color: 'var(--p-muted)', fontSize: '0.85rem', marginTop: 8, marginBottom: 16 }}>
              Se generará un password temporal. El usuario deberá cambiarlo después de iniciar sesión.
            </p>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
              <button
                onClick={() => setResetTarget(null)}
                disabled={resettingBusy}
                style={ghostBtn}
              >
                Cancelar
              </button>
              <button
                onClick={handleResetPassword}
                disabled={resettingBusy}
                style={{
                  background: 'var(--p-warning)',
                  color: '#000',
                  fontWeight: 700,
                  padding: '6px 16px',
                  border: 'none',
                  borderRadius: 4,
                  cursor: resettingBusy ? 'not-allowed' : 'pointer',
                  fontFamily: 'inherit',
                  fontSize: 12,
                  opacity: resettingBusy ? 0.5 : 1,
                }}
              >
                {resettingBusy ? '...' : 'Resetear'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Modal con temp password ─────────────────────────────────────── */}
      {resetResult && (
        <div
          onClick={() => setResetResult(null)}
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
              Password temporal generado
            </h3>
            <p style={{ color: 'var(--p-muted)', fontSize: '0.85rem', marginTop: 8, marginBottom: 12 }}>
              Para <code style={{ color: 'var(--p-text)' }}>@{resetResult.user.username}</code>.
              Cópialo ahora; no se mostrará otra vez.
            </p>
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              background: 'var(--p-surface-2)',
              border: '1px solid var(--p-border)',
              borderRadius: 4,
              padding: '8px 10px',
              marginBottom: 16,
            }}>
              <code style={{
                flex: 1,
                color: 'var(--p-teal)',
                fontFamily: 'monospace',
                fontSize: 14,
                fontWeight: 700,
                wordBreak: 'break-all',
              }}>
                {resetResult.pwd}
              </code>
              <button
                onClick={copyTempPassword}
                style={{
                  background: 'var(--p-teal)',
                  color: 'var(--dax-on-accent)',
                  border: 'none',
                  padding: '4px 10px',
                  borderRadius: 4,
                  fontSize: 11,
                  fontWeight: 700,
                  cursor: 'pointer',
                  fontFamily: 'inherit',
                  whiteSpace: 'nowrap',
                }}
              >
                {resetCopied ? 'Copiado ✓' : 'Copiar'}
              </button>
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <button onClick={() => setResetResult(null)} style={ghostBtn}>
                Cerrar
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Confirm delete (typed-name) ──────────────────────────────────── */}
      <ConfirmModal
        open={!!delTarget}
        title={delTarget ? `Eliminar @${delTarget.username}` : ''}
        message="Esta acción marcará al usuario como inactivo (soft-delete). Los registros históricos se conservan."
        resourceName={delTarget?.username || ''}
        destructive
        busy={deleting}
        onClose={() => setDelTarget(null)}
        onConfirm={handleDelete}
      />
    </PlatformPageShell>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// RowActions — menú compacto por fila (3 dots → reset / cambiar rol / eliminar)
// ─────────────────────────────────────────────────────────────────────────────

interface RowActionsProps {
  user: PlatformUser
  isSuperAdmin: boolean
  onEdit: () => void
  onResetPassword: () => void
  onChangeRole: () => void
  onDelete: () => void
}

function RowActions({
  user,
  isSuperAdmin,
  onEdit,
  onResetPassword,
  onChangeRole,
  onDelete,
}: RowActionsProps) {
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

  const iconBtn: React.CSSProperties = {
    background: 'none',
    border: 'none',
    color: 'var(--p-muted)',
    cursor: 'pointer',
    padding: '4px 8px',
    borderRadius: 4,
    fontSize: 12,
    fontFamily: 'inherit',
  }

  const menuItem = (
    label: string,
    icon: string,
    handler: () => void,
    opts: { danger?: boolean; disabled?: boolean } = {},
  ) => (
    <button
      onClick={() => { if (!opts.disabled) { setOpen(false); handler() } }}
      disabled={opts.disabled}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        width: '100%',
        padding: '8px 12px',
        background: 'none',
        border: 'none',
        color: opts.disabled
          ? 'var(--p-hint)'
          : opts.danger ? 'var(--p-danger)' : 'var(--p-text)',
        fontSize: 12,
        textAlign: 'left',
        cursor: opts.disabled ? 'not-allowed' : 'pointer',
        fontFamily: 'inherit',
      }}
      onMouseEnter={(e) => {
        if (!opts.disabled) (e.currentTarget.style.background = 'var(--p-surface-2)')
      }}
      onMouseLeave={(e) => { e.currentTarget.style.background = 'none' }}
    >
      <i className={`fa-solid ${icon}`} style={{ width: 14, textAlign: 'center' }} />
      {label}
    </button>
  )

  return (
    <div ref={ref} style={{ position: 'relative', display: 'flex', justifyContent: 'flex-end' }}>
      <button
        onClick={onEdit}
        title="Editar"
        aria-label={`Editar ${user.username}`}
        style={iconBtn}
      >
        <i className="fa-solid fa-pen" />
      </button>
      <button
        onClick={() => setOpen((v) => !v)}
        title="Más acciones"
        aria-label={`Más acciones para ${user.username}`}
        style={iconBtn}
      >
        <i className="fa-solid fa-ellipsis-vertical" />
      </button>
      {open && (
        <div style={{
          position: 'absolute',
          top: '100%',
          right: 0,
          marginTop: 4,
          minWidth: 180,
          background: 'var(--p-surface)',
          border: '1px solid var(--p-border)',
          borderRadius: 6,
          boxShadow: '0 8px 24px rgba(0,0,0,0.5)',
          zIndex: 50,
          overflow: 'hidden',
        }}>
          {menuItem('Reset password', 'fa-key', onResetPassword, { disabled: !isSuperAdmin })}
          {menuItem('Cambiar rol', 'fa-id-badge', onChangeRole, { disabled: !isSuperAdmin })}
          {menuItem('Eliminar', 'fa-trash', onDelete, { danger: true, disabled: !isSuperAdmin })}
        </div>
      )}
    </div>
  )
}
