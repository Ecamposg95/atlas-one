import { useEffect, useState, useCallback } from 'react'
import { productsApi } from '../../api/products'
import { DaxCard } from '../../components/ui/DaxCard'
import { Spinner } from '../../components/ui/Spinner'
import { toast } from '../../store/toastStore'
import { confirm as confirmDialog } from '../../components/ui/ConfirmDialog'
import type { Brand } from '../../types/products'

interface BrandForm { name: string; logo_url: string }
const EMPTY: BrandForm = { name: '', logo_url: '' }

export function Brands() {
  const [brands, setBrands] = useState<Brand[]>([])
  const [loading, setLoading] = useState(true)
  const [modal, setModal] = useState<'create' | 'edit' | null>(null)
  const [editing, setEditing] = useState<Brand | null>(null)
  const [form, setForm] = useState<BrandForm>(EMPTY)
  const [saving, setSaving] = useState(false)
  const [search, setSearch] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    try { setBrands(await productsApi.getBrands()) }
    catch { setBrands([]) } finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [])

  const openCreate = () => { setForm(EMPTY); setEditing(null); setModal('create') }
  const openEdit = (b: Brand) => {
    setForm({ name: b.name, logo_url: b.logo_url ?? '' })
    setEditing(b); setModal('edit')
  }

  const handleSave = async () => {
    if (!form.name) return
    setSaving(true)
    try {
      const payload = { name: form.name, logo_url: form.logo_url || undefined }
      if (modal === 'create') await productsApi.createBrand(payload)
      else if (editing) await productsApi.updateBrand(editing.id, payload)
      setModal(null); load()
    } catch { toast.error('Error al guardar la marca') } finally { setSaving(false) }
  }

  const handleDelete = async (b: Brand) => {
    const ok = await confirmDialog({
      title: 'Eliminar marca',
      message: `¿Eliminar la marca "${b.name}"?`,
      variant: 'danger',
      confirmText: 'Eliminar',
    })
    if (!ok) return
    try { await productsApi.deleteBrand(b.id); load() }
    catch { toast.error('Error al eliminar la marca') }
  }

  const filtered = brands.filter((b) =>
    !search || b.name.toLowerCase().includes(search.toLowerCase())
  )

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <i className="fa-solid fa-tags text-indigo-400 text-xl" />
          <h1 className="text-2xl font-black text-white">Marcas</h1>
        </div>
        <button onClick={openCreate} className="dax-btn-primary text-xs">
          <i className="fa-solid fa-plus" /> Nueva Marca
        </button>
      </div>

      <div className="flex gap-2">
        <input type="text" placeholder="Buscar marca..."
          value={search} onChange={(e) => setSearch(e.target.value)} className="dax-input flex-1 text-sm" />
      </div>

      <DaxCard padding={false}>
        {loading ? <Spinner text="Cargando marcas..." /> : filtered.length === 0 ? (
          <div className="p-12 text-center text-slate-600">Sin marcas</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="dax-table w-full">
              <thead>
                <tr>
                  <th>Logo</th>
                  <th>Nombre</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((b) => (
                  <tr key={b.id}>
                    <td>
                      {b.logo_url ? (
                        <img src={b.logo_url} alt={b.name} className="h-8 w-8 object-contain rounded" />
                      ) : (
                        <div className="h-8 w-8 bg-slate-700 rounded flex items-center justify-center">
                          <i className="fa-solid fa-image text-slate-500 text-xs" />
                        </div>
                      )}
                    </td>
                    <td className="font-semibold text-white">{b.name}</td>
                    {/* El `flex` iba en el `<td>`: la celda dejaba de ser
                        `table-cell` y se salía del reparto de columnas. */}
                    <td className="whitespace-nowrap">
                      <div className="flex gap-2">
                      <button onClick={() => openEdit(b)} aria-label={`Editar ${b.name}`} className="dax-btn-icon text-slate-500 hover:text-white text-xs"><i className="fa-solid fa-pen" /></button>
                      <button onClick={() => handleDelete(b)} aria-label={`Eliminar ${b.name}`} className="dax-btn-icon text-slate-600 hover:text-red-400 text-xs"><i className="fa-solid fa-trash" /></button>
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
              <h3 className="text-lg font-black text-white">{modal === 'create' ? 'Nueva Marca' : 'Editar Marca'}</h3>
              <button onClick={() => setModal(null)} aria-label="Cerrar" className="dax-btn-icon text-slate-500 hover:text-white"><i className="fa-solid fa-xmark text-lg" /></button>
            </div>
            <div className="space-y-3">
              <div>
                <label className="dax-label">Nombre</label>
                <input value={form.name} onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))}
                  className="dax-input w-full" placeholder="Ej: Samsung" autoFocus />
              </div>
              <div>
                <label className="dax-label">URL del logo (opcional)</label>
                <input type="url" value={form.logo_url} onChange={(e) => setForm((p) => ({ ...p, logo_url: e.target.value }))}
                  className="dax-input w-full" placeholder="https://..." />
                {form.logo_url && (
                  <img src={form.logo_url} alt="preview" className="mt-2 h-12 object-contain rounded border border-slate-700" onError={(e) => (e.currentTarget.style.display = 'none')} />
                )}
              </div>
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
