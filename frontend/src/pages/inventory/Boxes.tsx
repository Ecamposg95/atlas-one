import { useEffect, useState, useCallback } from 'react'
import client from '../../api/client'
import { DaxCard } from '../../components/ui/DaxCard'
import { Spinner } from '../../components/ui/Spinner'
import { toast } from '../../store/toastStore'

// ── Types ────────────────────────────────────────────────────────────────────

interface ContainerType {
  id: number
  name: string
  inner_length: number
  inner_width: number
  inner_height: number
}

interface BoxType {
  id: number
  name: string
  outer_length: number
  outer_width: number
  outer_height: number
}

type Tab = 'containers' | 'boxes'

// ── Helpers ──────────────────────────────────────────────────────────────────

function dims(l: number, w: number, h: number) {
  return `${l} × ${w} × ${h} cm`
}

// ── Forms ─────────────────────────────────────────────────────────────────────

interface ContainerForm { name: string; inner_length: string; inner_width: string; inner_height: string }
interface BoxForm { name: string; outer_length: string; outer_width: string; outer_height: string }

const emptyContainerForm = (): ContainerForm => ({ name: '', inner_length: '', inner_width: '', inner_height: '' })
const emptyBoxForm = (): BoxForm => ({ name: '', outer_length: '', outer_width: '', outer_height: '' })

// ── Component ─────────────────────────────────────────────────────────────────

export function Boxes() {
  const [tab, setTab] = useState<Tab>('containers')
  const [containers, setContainers] = useState<ContainerType[]>([])
  const [boxes, setBoxes] = useState<BoxType[]>([])
  const [loading, setLoading] = useState(true)

  // Container modal
  const [showContainerModal, setShowContainerModal] = useState(false)
  const [containerForm, setContainerForm] = useState<ContainerForm>(emptyContainerForm())
  const [savingContainer, setSavingContainer] = useState(false)

  // Box modal
  const [showBoxModal, setShowBoxModal] = useState(false)
  const [boxForm, setBoxForm] = useState<BoxForm>(emptyBoxForm())
  const [savingBox, setSavingBox] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [{ data: c }, { data: b }] = await Promise.all([
        client.get<ContainerType[]>('/logistics/containers'),
        client.get<BoxType[]>('/logistics/boxes'),
      ])
      setContainers(c)
      setBoxes(b)
    } catch { /* silent */ } finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  // ── Container submit ────────────────────────────────────────────────────────

  const handleSaveContainer = async () => {
    const { name, inner_length, inner_width, inner_height } = containerForm
    if (!name || !inner_length || !inner_width || !inner_height) return
    setSavingContainer(true)
    try {
      await client.post('/logistics/containers', {
        name,
        inner_length: Number(inner_length),
        inner_width: Number(inner_width),
        inner_height: Number(inner_height),
      })
      setShowContainerModal(false)
      setContainerForm(emptyContainerForm())
      load()
    } catch { toast.error('Error al guardar el contenedor') } finally { setSavingContainer(false) }
  }

  // ── Box submit ──────────────────────────────────────────────────────────────

  const handleSaveBox = async () => {
    const { name, outer_length, outer_width, outer_height } = boxForm
    if (!name || !outer_length || !outer_width || !outer_height) return
    setSavingBox(true)
    try {
      await client.post('/logistics/boxes', {
        name,
        outer_length: Number(outer_length),
        outer_width: Number(outer_width),
        outer_height: Number(outer_height),
      })
      setShowBoxModal(false)
      setBoxForm(emptyBoxForm())
      load()
    } catch { toast.error('Error al guardar el tipo de caja') } finally { setSavingBox(false) }
  }

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <i className="fa-solid fa-box-open text-indigo-400 text-xl" />
          <h1 className="text-2xl font-black text-white">Cajas y contenedores</h1>
        </div>
        <button
          onClick={() => tab === 'containers' ? (setContainerForm(emptyContainerForm()), setShowContainerModal(true)) : (setBoxForm(emptyBoxForm()), setShowBoxModal(true))}
          className="dax-btn-primary text-xs"
        >
          <i className="fa-solid fa-plus" /> {tab === 'containers' ? 'Nuevo Contenedor' : 'Nuevo Tipo de Caja'}
        </button>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-slate-900/60 p-1 rounded-xl w-fit">
        {([['containers', 'Contenedores', 'fa-truck-ramp-box'], ['boxes', 'Tipos de Caja', 'fa-box']] as [Tab, string, string][]).map(([key, label, icon]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`flex items-center gap-2 px-4 py-1.5 rounded-lg text-sm font-semibold transition-colors ${
              tab === key ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-white'
            }`}
          >
            <i className={`fa-solid ${icon} text-xs`} />
            {label}
          </button>
        ))}
      </div>

      {loading ? (
        <Spinner text="Cargando..." />
      ) : (
        <>
          {/* Containers */}
          {tab === 'containers' && (
            <DaxCard padding={false}>
              {containers.length === 0 ? (
                <div className="p-12 text-center text-slate-600">
                  <i className="fa-solid fa-truck-ramp-box text-4xl mb-3 block" />
                  Sin tipos de contenedor registrados
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="dax-table w-full">
                    <thead>
                      <tr>
                        <th>#</th>
                        <th>Nombre</th>
                        <th>Dimensiones internas (L × W × H)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {containers.map((c) => (
                        <tr key={c.id}>
                          <td className="text-slate-500 font-mono text-xs">{c.id}</td>
                          <td className="font-semibold text-white">{c.name}</td>
                          <td className="text-slate-400 text-sm font-mono">{dims(c.inner_length, c.inner_width, c.inner_height)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </DaxCard>
          )}

          {/* Boxes */}
          {tab === 'boxes' && (
            <DaxCard padding={false}>
              {boxes.length === 0 ? (
                <div className="p-12 text-center text-slate-600">
                  <i className="fa-solid fa-box text-4xl mb-3 block" />
                  Sin tipos de caja registrados
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="dax-table w-full">
                    <thead>
                      <tr>
                        <th>#</th>
                        <th>Nombre</th>
                        <th>Dimensiones externas (L × W × H)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {boxes.map((b) => (
                        <tr key={b.id}>
                          <td className="text-slate-500 font-mono text-xs">{b.id}</td>
                          <td className="font-semibold text-white">{b.name}</td>
                          <td className="text-slate-400 text-sm font-mono">{dims(b.outer_length, b.outer_width, b.outer_height)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </DaxCard>
          )}
        </>
      )}

      {/* Modal — Nuevo Contenedor */}
      {showContainerModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm"
          onClick={() => setShowContainerModal(false)}>
          <div className="dax-card p-6 w-full max-w-md" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-5">
              <h3 className="text-lg font-black text-white">Nuevo Contenedor</h3>
              <button onClick={() => setShowContainerModal(false)} className="text-slate-500 hover:text-white">
                <i className="fa-solid fa-xmark text-lg" />
              </button>
            </div>
            <div className="space-y-3">
              <div>
                <label className="dax-label">Nombre</label>
                <input type="text" value={containerForm.name}
                  onChange={(e) => setContainerForm((f) => ({ ...f, name: e.target.value }))}
                  className="dax-input w-full" placeholder="Ej. Contenedor 40 pies" />
              </div>
              <div className="grid grid-cols-3 gap-3">
                {(['inner_length', 'inner_width', 'inner_height'] as const).map((field, i) => (
                  <div key={field}>
                    <label className="dax-label">{['Largo', 'Ancho', 'Alto'][i]} (cm)</label>
                    <input type="number" min="0" step="0.01"
                      value={containerForm[field]}
                      onChange={(e) => setContainerForm((f) => ({ ...f, [field]: e.target.value }))}
                      className="dax-input w-full" placeholder="0" />
                  </div>
                ))}
              </div>
            </div>
            <div className="flex gap-2 mt-5">
              <button onClick={() => setShowContainerModal(false)} className="dax-btn-secondary flex-1">Cancelar</button>
              <button onClick={handleSaveContainer}
                disabled={savingContainer || !containerForm.name || !containerForm.inner_length}
                className="dax-btn-primary flex-1 justify-center disabled:opacity-40">
                {savingContainer ? <i className="fa-solid fa-spinner fa-spin" /> : <><i className="fa-solid fa-floppy-disk" /> Guardar</>}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal — Nuevo Tipo de Caja */}
      {showBoxModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm"
          onClick={() => setShowBoxModal(false)}>
          <div className="dax-card p-6 w-full max-w-md" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-5">
              <h3 className="text-lg font-black text-white">Nuevo Tipo de Caja</h3>
              <button onClick={() => setShowBoxModal(false)} className="text-slate-500 hover:text-white">
                <i className="fa-solid fa-xmark text-lg" />
              </button>
            </div>
            <div className="space-y-3">
              <div>
                <label className="dax-label">Nombre</label>
                <input type="text" value={boxForm.name}
                  onChange={(e) => setBoxForm((f) => ({ ...f, name: e.target.value }))}
                  className="dax-input w-full" placeholder="Ej. Caja chica 30×20" />
              </div>
              <div className="grid grid-cols-3 gap-3">
                {(['outer_length', 'outer_width', 'outer_height'] as const).map((field, i) => (
                  <div key={field}>
                    <label className="dax-label">{['Largo', 'Ancho', 'Alto'][i]} (cm)</label>
                    <input type="number" min="0" step="0.01"
                      value={boxForm[field]}
                      onChange={(e) => setBoxForm((f) => ({ ...f, [field]: e.target.value }))}
                      className="dax-input w-full" placeholder="0" />
                  </div>
                ))}
              </div>
            </div>
            <div className="flex gap-2 mt-5">
              <button onClick={() => setShowBoxModal(false)} className="dax-btn-secondary flex-1">Cancelar</button>
              <button onClick={handleSaveBox}
                disabled={savingBox || !boxForm.name || !boxForm.outer_length}
                className="dax-btn-primary flex-1 justify-center disabled:opacity-40">
                {savingBox ? <i className="fa-solid fa-spinner fa-spin" /> : <><i className="fa-solid fa-floppy-disk" /> Guardar</>}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
