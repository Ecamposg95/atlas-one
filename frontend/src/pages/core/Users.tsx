import { useEffect, useState, useCallback } from 'react'
import { usersApi, type SystemUser, type CreateUserPayload, type UpdateUserPayload } from '../../api/users'
import { organizationApi, type Branch } from '../../api/organization'
import { DaxCard } from '../../components/ui/DaxCard'
import { TablaDesplazable } from '../../components/ui/TablaDesplazable'
import { Spinner } from '../../components/ui/Spinner'
import { Badge } from '../../components/ui/Badge'
import { toast } from '../../store/toastStore'
import { rolUsuario } from '../../utils/enumsEspanol'

const ROLES = ['ADMINISTRADOR', 'DUEÑO', 'GERENTE', 'CAJERO', 'VENDEDOR', 'SOPORTE_OPERATIVO']
// Solo estos roles pueden autorizar una reimpresión desde el POS (mismo
// conjunto que ROLES_GERENCIALES en app/services/reprint_auth.py): en
// cualquier otro rol el PIN se guardaría sin servir para nada.
const ROLES_CON_PIN = ['ADMINISTRADOR', 'DUEÑO', 'GERENTE']
const PIN_VALIDO = /^\d{4,8}$/
const roleVariant = (r: string) =>
  r === 'ADMINISTRADOR' ? 'red' : r === 'DUEÑO' ? 'yellow' : r === 'GERENTE' ? 'blue' : r === 'CAJERO' ? 'green' : 'slate'

interface UserForm {
  username: string; password: string; full_name: string
  role: string; branch_id: string; is_active: boolean
  reprintPin: string; clearReprintPin: boolean
}

const EMPTY_FORM: UserForm = {
  username: '', password: '', full_name: '', role: 'CAJERO', branch_id: '', is_active: true,
  reprintPin: '', clearReprintPin: false,
}

export function Users() {
  const [users, setUsers] = useState<SystemUser[]>([])
  const [branches, setBranches] = useState<Branch[]>([])
  const [loading, setLoading] = useState(true)
  const [modal, setModal] = useState<'create' | 'edit' | null>(null)
  const [editing, setEditing] = useState<SystemUser | null>(null)
  const [form, setForm] = useState<UserForm>(EMPTY_FORM)
  const [saving, setSaving] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await usersApi.getAll()
      setUsers(data)
    } catch { setUsers([]) } finally { setLoading(false) }
  }, [])

  useEffect(() => {
    organizationApi.getBranches().then(setBranches).catch(() => {})
    load()
  }, [])

  const openCreate = () => { setForm(EMPTY_FORM); setEditing(null); setModal('create') }
  const openEdit = (u: SystemUser) => {
    setForm({
      username: u.username, password: '', full_name: u.full_name ?? '', role: u.role,
      branch_id: u.branch_id ? String(u.branch_id) : '', is_active: u.is_active,
      // El PIN nunca se lee de vuelta (el backend solo expone has_reprint_pin):
      // en blanco significa "no cambiarlo".
      reprintPin: '', clearReprintPin: false,
    })
    setEditing(u); setModal('edit')
  }

  const rolConPin = ROLES_CON_PIN.includes(form.role)
  const errorPin = rolConPin && !form.clearReprintPin && form.reprintPin && !PIN_VALIDO.test(form.reprintPin)
    ? 'El PIN debe ser de 4 a 8 dígitos.'
    : null

  const handleSave = async () => {
    if (errorPin) { toast.error(errorPin); return }
    // El PIN solo viaja si el usuario escribió uno o pidió quitarlo; en un rol
    // que no autoriza reimpresiones no se manda nunca, aunque se hubiera
    // tecleado antes de cambiar el rol.
    let reprintPin: string | undefined
    if (rolConPin) {
      if (form.clearReprintPin) reprintPin = ''
      else if (form.reprintPin) reprintPin = form.reprintPin
    }
    setSaving(true)
    try {
      if (modal === 'create') {
        const payload: CreateUserPayload = {
          username: form.username, password: form.password, full_name: form.full_name || undefined,
          role: form.role, branch_id: form.branch_id ? Number(form.branch_id) : null,
        }
        if (reprintPin !== undefined) payload.reprint_pin = reprintPin
        await usersApi.create(payload)
      } else if (editing) {
        const payload: UpdateUserPayload = {
          full_name: form.full_name || undefined, role: form.role,
          branch_id: form.branch_id ? Number(form.branch_id) : null,
          is_active: form.is_active,
        }
        if (form.password) payload.password = form.password
        if (reprintPin !== undefined) payload.reprint_pin = reprintPin
        await usersApi.update(editing.id, payload)
      }
      setModal(null); load()
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      toast.error(typeof detail === 'string' && detail ? detail : 'Error al guardar el usuario')
    } finally { setSaving(false) }
  }

  const handleToggle = async (u: SystemUser) => {
    try {
      await usersApi.update(u.id, { is_active: !u.is_active })
      load()
    } catch { toast.error('Error al cambiar el estado del usuario') }
  }

  const f = (field: keyof UserForm, val: string | boolean) => setForm((prev) => ({ ...prev, [field]: val }))

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <i className="fa-solid fa-users-cog text-indigo-400 text-xl" />
          <h1 className="text-2xl font-black text-white">Usuarios</h1>
        </div>
        <button onClick={openCreate} className="dax-btn-primary text-xs">
          <i className="fa-solid fa-plus" /> Nuevo usuario
        </button>
      </div>

      <DaxCard padding={false}>
        {loading ? <Spinner text="Cargando usuarios..." /> : users.length === 0 ? (
          <div className="p-12 text-center text-slate-600">Sin usuarios</div>
        ) : (
          <TablaDesplazable sangrado={false}>
            <table className="dax-table w-full">
              <thead>
                <tr>
                  <th>Usuario</th>
                  <th>Nombre</th>
                  <th>Rol</th>
                  <th>Sucursal</th>
                  <th>Estado</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.id}>
                    <td className="font-mono text-indigo-400 text-sm">{u.username}</td>
                    <td className="text-slate-300">{u.full_name ?? '—'}</td>
                    <td><Badge variant={roleVariant(u.role) as 'red' | 'yellow' | 'blue' | 'green' | 'slate'}>{rolUsuario(u.role)}</Badge></td>
                    <td className="text-slate-400 text-sm">{u.branch_name ?? 'HQ'}</td>
                    <td>
                      <button onClick={() => handleToggle(u)}
                        aria-label={u.is_active ? `Desactivar a ${u.username}` : `Activar a ${u.username}`}
                        className={`dax-btn-icon text-xs font-semibold whitespace-nowrap ${u.is_active ? 'text-emerald-400' : 'text-slate-600'}`}>
                        <i className={`fa-solid ${u.is_active ? 'fa-circle-check' : 'fa-circle-xmark'} mr-1`} />
                        {u.is_active ? 'Activo' : 'Inactivo'}
                      </button>
                    </td>
                    <td>
                      <button onClick={() => openEdit(u)} aria-label={`Editar a ${u.username}`}
                        className="dax-btn-icon text-slate-500 hover:text-white text-xs">
                        <i className="fa-solid fa-pen" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TablaDesplazable>
        )}
      </DaxCard>

      {/* Modal crear/editar */}
      {modal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm" onClick={() => setModal(null)}>
          <div className="dax-card dax-modal p-6 w-full max-w-md" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-5">
              <h3 className="text-lg font-black text-white">{modal === 'create' ? 'Nuevo usuario' : 'Editar usuario'}</h3>
              <button onClick={() => setModal(null)} className="dax-btn-icon text-slate-500 hover:text-white"><i className="fa-solid fa-xmark text-lg" /></button>
            </div>

            <div className="space-y-3">
              <div>
                <label className="dax-label">Usuario</label>
                <input value={form.username} onChange={(e) => f('username', e.target.value)}
                  disabled={modal === 'edit'} className="dax-input w-full disabled:opacity-50" placeholder="usuario123" />
              </div>
              <div>
                <label className="dax-label">Nombre completo</label>
                <input value={form.full_name} onChange={(e) => f('full_name', e.target.value)} className="dax-input w-full" placeholder="Juan Pérez" />
              </div>
              <div>
                <label className="dax-label">{modal === 'edit' ? 'Nueva contraseña (opcional)' : 'Contraseña'}</label>
                <input type="password" value={form.password} onChange={(e) => f('password', e.target.value)} className="dax-input w-full" />
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="dax-label">Rol</label>
                  <select value={form.role} onChange={(e) => f('role', e.target.value)} className="dax-input w-full">
                    {ROLES.map((r) => <option key={r} value={r}>{rolUsuario(r)}</option>)}
                  </select>
                </div>
                <div>
                  <label className="dax-label">Sucursal</label>
                  <select value={form.branch_id} onChange={(e) => f('branch_id', e.target.value)} className="dax-input w-full">
                    <option value="">Sin sucursal fija</option>
                    {branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
                  </select>
                </div>
              </div>
              {modal === 'edit' && (
                <div className="flex items-center gap-2">
                  <input type="checkbox" id="active-chk" checked={form.is_active} onChange={(e) => f('is_active', e.target.checked)} className="w-4 h-4" />
                  <label htmlFor="active-chk" className="text-sm text-slate-400">Usuario activo</label>
                </div>
              )}

              {/* PIN de reimpresión: lo teclea el cajero en el POS para que un
                  gerente autorice reimprimir un ticket. Es independiente de la
                  contraseña — así el dueño no tiene que compartir la suya. */}
              <div>
                <div className="flex items-center justify-between mb-1">
                  <label htmlFor="reprint-pin" className="dax-label mb-0">PIN de reimpresión (4–8 dígitos)</label>
                  {modal === 'edit' && rolConPin && (
                    <span className={`text-[10px] font-bold uppercase tracking-wider ${editing?.has_reprint_pin ? 'text-emerald-400' : 'text-slate-500'}`}>
                      {editing?.has_reprint_pin ? 'PIN configurado' : 'Sin PIN'}
                    </span>
                  )}
                </div>
                {!rolConPin ? (
                  <p className="text-xs text-slate-500 italic">
                    Solo aplica a Administrador, Dueño o Gerente — son los únicos roles que pueden autorizar una reimpresión.
                  </p>
                ) : form.clearReprintPin ? (
                  <div className="rounded-lg px-3 py-2 flex items-center justify-between gap-2 bg-red-500/10 border border-red-500/30">
                    <span className="text-xs text-red-400">Se quitará el PIN al guardar.</span>
                    <button type="button" onClick={() => f('clearReprintPin', false)}
                      className="text-[10px] font-bold text-slate-400 hover:text-white uppercase transition flex-shrink-0">
                      Cancelar
                    </button>
                  </div>
                ) : (
                  <>
                    <div className="flex gap-2">
                      <input
                        id="reprint-pin"
                        type="password"
                        inputMode="numeric"
                        autoComplete="new-password"
                        value={form.reprintPin}
                        onChange={(e) => f('reprintPin', e.target.value.replace(/\D/g, '').slice(0, 8))}
                        placeholder={modal === 'edit' ? 'Dejar en blanco para no cambiarlo' : 'Opcional'}
                        aria-invalid={!!errorPin}
                        className={`dax-input w-full ${errorPin ? 'border-red-500' : ''}`}
                      />
                      {modal === 'edit' && editing?.has_reprint_pin && (
                        <button type="button" onClick={() => f('clearReprintPin', true)}
                          className="text-[11px] font-bold text-red-500 hover:text-red-400 uppercase transition whitespace-nowrap px-2 flex-shrink-0">
                          Quitar PIN
                        </button>
                      )}
                    </div>
                    {errorPin && <p className="text-xs text-red-400 mt-1">{errorPin}</p>}
                  </>
                )}
              </div>
            </div>

            <div className="dax-modal-footer -mx-6 px-6 flex gap-2 mt-5">
              <button onClick={() => setModal(null)} className="dax-btn-secondary flex-1">Cancelar</button>
              <button onClick={handleSave} disabled={saving || !form.username || !!errorPin || (modal === 'create' && !form.password)} className="dax-btn-primary flex-1 justify-center disabled:opacity-40">
                {saving ? <i className="fa-solid fa-spinner fa-spin" /> : <><i className="fa-solid fa-check" /> Guardar</>}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
