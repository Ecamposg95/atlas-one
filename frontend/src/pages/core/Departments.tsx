import { useEffect, useState, useCallback } from 'react'
import { productsApi } from '../../api/products'
import { DaxCard } from '../../components/ui/DaxCard'
import { Spinner } from '../../components/ui/Spinner'
import { toast } from '../../store/toastStore'
import { confirm as confirmDialog } from '../../components/ui/ConfirmDialog'
import type { Department } from '../../types/products'

interface DeptForm { name: string }
const EMPTY: DeptForm = { name: '' }

export function Departments() {
  const [departments, setDepartments] = useState<Department[]>([])
  const [loading, setLoading] = useState(true)
  const [modal, setModal] = useState<'create' | 'edit' | null>(null)
  const [editing, setEditing] = useState<Department | null>(null)
  const [form, setForm] = useState<DeptForm>(EMPTY)
  const [saving, setSaving] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try { setDepartments(await productsApi.getDepartments()) }
    catch { setDepartments([]) } finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [])

  const openCreate = () => { setForm(EMPTY); setEditing(null); setModal('create') }
  const openEdit = (d: Department) => {
    setForm({ name: d.name })
    setEditing(d); setModal('edit')
  }

  const handleSave = async () => {
    if (!form.name) return
    setSaving(true)
    try {
      if (modal === 'create') await productsApi.createDepartment({ name: form.name })
      else if (editing) await productsApi.updateDepartment(editing.id, { name: form.name })
      setModal(null); load()
    } catch { toast.error('Error al guardar el departamento') } finally { setSaving(false) }
  }

  const handleDelete = async (d: Department) => {
    const ok = await confirmDialog({
      title: 'Eliminar departamento',
      message: `¿Eliminar el departamento "${d.name}"?`,
      variant: 'danger',
      confirmText: 'Eliminar',
    })
    if (!ok) return
    try { await productsApi.deleteDepartment(d.id); load() }
    catch { toast.error('Error al eliminar el departamento') }
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <i className="fa-solid fa-layer-group text-indigo-400 text-xl" />
          <h1 className="text-2xl font-black text-white">Departamentos</h1>
        </div>
        <button onClick={openCreate} className="dax-btn-primary text-xs">
          <i className="fa-solid fa-plus" /> Nuevo
        </button>
      </div>

      <DaxCard padding={false}>
        {loading ? <Spinner text="Cargando..." /> : departments.length === 0 ? (
          <div className="p-12 text-center text-slate-600">Sin departamentos</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="dax-table w-full">
              <thead>
                <tr>
                  <th>Nombre</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {departments.map((d) => (
                  <tr key={d.id}>
                    <td className="font-semibold text-white">{d.name}</td>
                    {/* El `flex` iba en el `<td>`: la celda dejaba de ser
                        `table-cell` y se salía del reparto de columnas. */}
                    <td className="whitespace-nowrap">
                      <div className="flex gap-2">
                      <button onClick={() => openEdit(d)} aria-label={`Editar ${d.name}`} className="dax-btn-icon text-slate-500 hover:text-white text-xs"><i className="fa-solid fa-pen" /></button>
                      <button onClick={() => handleDelete(d)} aria-label={`Eliminar ${d.name}`} className="dax-btn-icon text-slate-600 hover:text-red-400 text-xs"><i className="fa-solid fa-trash" /></button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </DaxCard>

      {/* Modal */}
      {modal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm" onClick={() => setModal(null)}>
          <div className="dax-card dax-modal p-6 w-full max-w-sm" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-5">
              <h3 className="text-lg font-black text-white">{modal === 'create' ? 'Nuevo Departamento' : 'Editar Departamento'}</h3>
              <button onClick={() => setModal(null)} aria-label="Cerrar" className="dax-btn-icon text-slate-500 hover:text-white"><i className="fa-solid fa-xmark text-lg" /></button>
            </div>
            <div>
              <label className="dax-label">Nombre</label>
              <input value={form.name} onChange={(e) => setForm({ name: e.target.value })}
                className="dax-input w-full" placeholder="Ej: Electrónicos" autoFocus />
            </div>
            <div className="dax-modal-footer -mx-6 px-6 flex gap-2 mt-5">
              <button onClick={() => setModal(null)} className="dax-btn-secondary flex-1">Cancelar</button>
              <button onClick={handleSave} disabled={saving || !form.name} className="dax-btn-primary flex-1 justify-center disabled:opacity-40">
                {saving ? <i className="fa-solid fa-spinner fa-spin" /> : <><i className="fa-solid fa-check" /> Guardar</>}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
