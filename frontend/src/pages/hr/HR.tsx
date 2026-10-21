import { useEffect, useState, useCallback } from 'react'
import { hrApi, type Employee, type EmployeeCreate, employeeFullName } from '../../api/hr'
import { organizationApi, type Branch } from '../../api/organization'
import { DaxCard } from '../../components/ui/DaxCard'
import { Spinner } from '../../components/ui/Spinner'
import { Badge } from '../../components/ui/Badge'
import { Modal } from '../../components/ui/Modal'
import { CabeceraPagina } from '../../components/ui/CabeceraPagina'
import { BarraFiltros } from '../../components/ui/BarraFiltros'
import { ListaTarjetas } from '../../components/ui/ListaTarjetas'
import { TarjetaFila } from '../../components/ui/TarjetaFila'
import { useEsTelefono } from '../../hooks/useIsMobile'
import { toast } from '../../store/toastStore'

const EMPLOYEE_TYPES: Employee['employee_type'][] = ['FULL_TIME', 'PART_TIME', 'CONTRACTOR', 'INTERN']
const typeLabel = (t: string) =>
  ({ FULL_TIME: 'Tiempo Completo', PART_TIME: 'Medio Tiempo', CONTRACTOR: 'Contratista', INTERN: 'Prácticas' }[t] ?? t)
const typeVariant = (t: string) =>
  (t === 'FULL_TIME' ? 'green' : t === 'CONTRACTOR' ? 'yellow' : t === 'PART_TIME' ? 'blue' : 'slate') as 'green' | 'yellow' | 'blue' | 'slate'
const fechaIngreso = (e: Employee) =>
  e.hire_date ? new Date(e.hire_date).toLocaleDateString('es-MX', { day: '2-digit', month: 'short', year: 'numeric' }) : '—'

interface EmpForm {
  first_name: string; last_name: string
  employee_type: Employee['employee_type']
  hire_date: string; base_branch_id: string
  phone: string; email_personal: string
}

const EMPTY_FORM: EmpForm = {
  first_name: '', last_name: '', employee_type: 'FULL_TIME',
  hire_date: '', base_branch_id: '', phone: '', email_personal: '',
}

export function HR() {
  const [employees, setEmployees] = useState<Employee[]>([])
  const [branches, setBranches] = useState<Branch[]>([])
  const [loading, setLoading] = useState(true)
  const [modal, setModal] = useState<'create' | 'edit' | null>(null)
  const [editing, setEditing] = useState<Employee | null>(null)
  const [form, setForm] = useState<EmpForm>(EMPTY_FORM)
  const [saving, setSaving] = useState(false)
  const [search, setSearch] = useState('')
  const esTelefono = useEsTelefono()

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await hrApi.getAll()
      setEmployees(data)
    } catch { setEmployees([]) } finally { setLoading(false) }
  }, [])

  useEffect(() => {
    organizationApi.getBranches().then(setBranches).catch(() => {})
    load()
  }, [])

  const openCreate = () => { setForm(EMPTY_FORM); setEditing(null); setModal('create') }
  const openEdit = (e: Employee) => {
    setForm({
      first_name: e.first_name ?? '', last_name: e.last_name ?? '',
      employee_type: e.employee_type ?? 'FULL_TIME',
      hire_date: e.hire_date ?? '',
      base_branch_id: e.base_branch_id ? String(e.base_branch_id) : '',
      phone: e.phone ?? '', email_personal: e.email_personal ?? '',
    })
    setEditing(e); setModal('edit')
  }

  const handleSave = async () => {
    if (!form.first_name) return
    setSaving(true)
    try {
      const payload: EmployeeCreate = {
        first_name: form.first_name, last_name: form.last_name,
        employee_type: form.employee_type,
        hire_date: form.hire_date || undefined,
        base_branch_id: form.base_branch_id ? Number(form.base_branch_id) : null,
        phone: form.phone || undefined, email_personal: form.email_personal || undefined,
      }
      if (modal === 'create') await hrApi.create(payload)
      else if (editing) await hrApi.update(editing.id, payload)
      setModal(null); load()
    } catch { toast.error('Error al guardar el empleado') } finally { setSaving(false) }
  }

  const f = (field: keyof EmpForm, val: string) => setForm((prev) => ({ ...prev, [field]: val }))
  const sucursalDe = (e: Employee) => branches.find((b) => b.id === e.base_branch_id)?.name ?? 'HQ'

  const filtered = employees.filter((e) =>
    !search || employeeFullName(e).toLowerCase().includes(search.toLowerCase())
  )

  return (
    <div className="space-y-5">
      <CabeceraPagina
        titulo={<div className="flex items-center gap-3">
          <i className="fa-solid fa-user-tie text-indigo-400 text-xl" />
          <h1 className="text-2xl font-black text-white">Recursos Humanos</h1>
        </div>}
        accionPrincipal={<button onClick={openCreate} className="dax-btn-primary text-xs">
          <i className="fa-solid fa-plus" /> Nuevo Empleado
        </button>}
      />

      <BarraFiltros>
        <input type="text" placeholder="Buscar empleado..." value={search}
          onChange={(e) => setSearch(e.target.value)} className="dax-input flex-1 text-sm" />
      </BarraFiltros>

      <DaxCard padding={false}>
        {esTelefono ? (
          <ListaTarjetas cargando={loading} vacio={filtered.length === 0} textoVacio="Sin empleados" className="p-3">
            {filtered.map((e) => (
              <TarjetaFila key={e.id}
                titulo={employeeFullName(e)}
                subtitulo={sucursalDe(e)}
                estado={<Badge variant={typeVariant(e.employee_type ?? '')}>{typeLabel(e.employee_type ?? '')}</Badge>}
                datos={[{ etiqueta: 'Ingreso', valor: fechaIngreso(e) }, { etiqueta: 'Teléfono', valor: e.phone ?? '—' }]}
                acciones={<button onClick={() => openEdit(e)} aria-label={`Editar a ${employeeFullName(e)}`} className="dax-btn-secondary text-xs">
                  <i className="fa-solid fa-pen" /> Editar
                </button>}
              />
            ))}
          </ListaTarjetas>
        ) : loading ? <Spinner text="Cargando empleados..." /> : filtered.length === 0 ? (
          <div className="p-12 text-center text-slate-600">Sin empleados</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="dax-table w-full">
              <thead>
                <tr>
                  <th>Nombre</th>
                  <th>Tipo</th>
                  <th>Sucursal</th>
                  <th>Ingreso</th>
                  <th>Teléfono</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((e) => (
                  <tr key={e.id}>
                    <td className="font-semibold text-white">{employeeFullName(e)}</td>
                    <td><Badge variant={typeVariant(e.employee_type ?? '')}>{typeLabel(e.employee_type ?? '')}</Badge></td>
                    <td className="text-slate-400 text-sm">{sucursalDe(e)}</td>
                    <td className="text-slate-500 text-xs">{fechaIngreso(e)}</td>
                    <td className="text-slate-400 text-sm">{e.phone ?? '—'}</td>
                    <td>
                      <button onClick={() => openEdit(e)} aria-label={`Editar a ${employeeFullName(e)}`} className="dax-btn-icon text-slate-500 hover:text-white text-xs">
                        <i className="fa-solid fa-pen" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </DaxCard>

      <Modal open={modal !== null} onClose={() => setModal(null)} title={modal === 'create' ? 'Nuevo Empleado' : 'Editar Empleado'} size="md"
        footer={<>
          <button onClick={() => setModal(null)} className="dax-btn-secondary flex-1">Cancelar</button>
          <button onClick={handleSave} disabled={saving || !form.first_name} className="dax-btn-primary flex-1 justify-center disabled:opacity-40">
            {saving ? <i className="fa-solid fa-spinner fa-spin" /> : <><i className="fa-solid fa-check" /> Guardar</>}
          </button>
        </>}>
        <div className="space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="dax-label">Nombre(s)</label>
              <input value={form.first_name} onChange={(e) => f('first_name', e.target.value)} className="dax-input w-full" placeholder="Juan" autoFocus />
            </div>
            <div>
              <label className="dax-label">Apellido(s)</label>
              <input value={form.last_name} onChange={(e) => f('last_name', e.target.value)} className="dax-input w-full" placeholder="Pérez García" />
            </div>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="dax-label">Tipo</label>
              <select value={form.employee_type} onChange={(e) => f('employee_type', e.target.value)} className="dax-input w-full">
                {EMPLOYEE_TYPES.map((t) => <option key={t} value={t}>{typeLabel(t)}</option>)}
              </select>
            </div>
            <div>
              <label className="dax-label">Sucursal</label>
              <select value={form.base_branch_id} onChange={(e) => f('base_branch_id', e.target.value)} className="dax-input w-full">
                <option value="">HQ</option>
                {branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
              </select>
            </div>
          </div>
          <div>
            <label className="dax-label">Fecha de ingreso</label>
            <input type="date" value={form.hire_date} onChange={(e) => f('hire_date', e.target.value)} className="dax-input w-full" />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="dax-label">Teléfono</label>
              <input value={form.phone} onChange={(e) => f('phone', e.target.value)} className="dax-input w-full" />
            </div>
            <div>
              <label className="dax-label">Email personal</label>
              <input type="email" value={form.email_personal} onChange={(e) => f('email_personal', e.target.value)} className="dax-input w-full" />
            </div>
          </div>
        </div>
      </Modal>
    </div>
  )
}
