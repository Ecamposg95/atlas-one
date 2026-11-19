import { useEffect, useState, FormEvent } from 'react'
import { barApi, BarBottle } from '../../api/bar'
import { useAuthStore } from '../../store/authStore'
import { toast } from '../../store/toastStore'
import { DaxCard } from '../../components/ui/DaxCard'
import { Spinner } from '../../components/ui/Spinner'

const ACCENT = '#EA580C' // Bar (violeta)
const LOW = 15 // % bajo → resaltar reposición

function volColor(pct: number): string {
  if (pct <= LOW) return '#f87171'   // rojo
  if (pct <= 40) return '#fbbf24'    // ámbar
  return '#FFA14A'                   // violeta claro (legible en oscuro)
}

export function Botellas() {
  const { branch } = useAuthStore()
  const [bottles, setBottles] = useState<BarBottle[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState<number | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ name: '', full_volume_ml: 750, pour_size_ml: 45 })

  const load = () => {
    setLoading(true)
    barApi.list({ branch_id: branch?.id })
      .then(setBottles)
      .catch(() => toast.error('No se pudieron cargar las botellas'))
      .finally(() => setLoading(false))
  }
  useEffect(load, [branch?.id])

  const act = async (id: number, fn: () => Promise<BarBottle>) => {
    setBusy(id)
    try {
      const updated = await fn()
      setBottles((bs) => bs.map((b) => (b.id === id ? updated : b)))
    } catch {
      toast.error('Acción no disponible')
    } finally {
      setBusy(null)
    }
  }

  const openBottle = async (e: FormEvent) => {
    e.preventDefault()
    if (!branch?.id) { toast.error('Selecciona una sucursal'); return }
    if (!form.name.trim()) return
    try {
      await barApi.open({ branch_id: branch.id, name: form.name.trim(), full_volume_ml: form.full_volume_ml, pour_size_ml: form.pour_size_ml })
      setForm({ name: '', full_volume_ml: 750, pour_size_ml: 45 })
      setShowForm(false)
      toast.success('Botella abierta')
      load()
    } catch {
      toast.error('No se pudo abrir la botella')
    }
  }

  const active = bottles.filter((b) => b.status !== 'ARCHIVED')
  const lowCount = active.filter((b) => b.pct_remaining <= LOW).length

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-[11px] uppercase tracking-[0.14em] text-slate-500 font-semibold">Bar · Inventario líquido</p>
          <div className="flex items-center gap-3 mt-1">
            <i className="fa-solid fa-wine-bottle text-violet-300 text-xl" />
            <h1 className="text-2xl font-black text-white">Botellas</h1>
          </div>
          <p className="text-sm text-slate-400 mt-0.5">
            {active.length} abiertas
            {lowCount > 0 && <span className="text-rose-400 font-semibold"> · {lowCount} por reponer</span>}
          </p>
        </div>
        <button
          onClick={() => setShowForm((s) => !s)}
          className="rounded-xl px-4 py-2.5 text-sm font-semibold text-white transition-opacity hover:opacity-90"
          style={{ background: ACCENT }}
        >
          {showForm ? 'Cancelar' : '+ Abrir botella'}
        </button>
      </div>

      {/* Form abrir botella */}
      {showForm && (
        <DaxCard>
          <form onSubmit={openBottle} className="flex flex-wrap items-end gap-3">
            <label className="flex-[2_1_240px] text-xs text-slate-400">
              Nombre
              <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="Tequila Don Julio 70" required className={inputCls} />
            </label>
            <label className="flex-[1_1_120px] text-xs text-slate-400">
              Volumen (ml)
              <input type="number" min={50} value={form.full_volume_ml}
                onChange={(e) => setForm({ ...form, full_volume_ml: Number(e.target.value) })} className={inputCls} />
            </label>
            <label className="flex-[1_1_120px] text-xs text-slate-400">
              Servida (ml)
              <input type="number" min={5} value={form.pour_size_ml}
                onChange={(e) => setForm({ ...form, pour_size_ml: Number(e.target.value) })} className={inputCls} />
            </label>
            <button type="submit" className="rounded-xl px-4 py-2.5 text-sm font-semibold text-white bg-slate-700 hover:bg-slate-600 transition-colors">
              Abrir
            </button>
          </form>
        </DaxCard>
      )}

      {/* Lista */}
      {loading ? (
        <Spinner size="lg" text="Cargando botellas..." />
      ) : active.length === 0 ? (
        <DaxCard>
          <p className="text-sm text-slate-400 text-center py-6">No hay botellas abiertas. Abre una para empezar. 🍾</p>
        </DaxCard>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {active.map((b) => {
            const pct = b.pct_remaining
            const color = volColor(pct)
            const empty = b.status === 'EMPTY'
            return (
              <DaxCard key={b.id} className={empty ? 'opacity-60' : ''}>
                <div className="flex flex-col gap-3">
                  <div className="flex items-start justify-between gap-2">
                    <strong className="text-sm text-white leading-tight">{b.name}</strong>
                    <span className="text-xs font-black tabular-nums" style={{ color }}>{Math.round(pct)}%</span>
                  </div>
                  {/* barra de volumen */}
                  <div className="h-2.5 rounded-full bg-slate-700/60 overflow-hidden">
                    <div className="h-full transition-all" style={{ width: `${pct}%`, background: color }} />
                  </div>
                  <p className="text-[11px] text-slate-500 tabular-nums">
                    {Math.round(Number(b.remaining_ml))} / {Math.round(Number(b.full_volume_ml))} ml · servida {Math.round(Number(b.pour_size_ml))} ml
                  </p>
                  <div className="flex gap-2 mt-auto">
                    <button disabled={busy === b.id || empty} onClick={() => act(b.id, () => barApi.pour(b.id, {}))}
                      className="flex-1 rounded-lg py-2 text-xs font-bold text-white disabled:opacity-40 transition-opacity hover:opacity-90"
                      style={{ background: ACCENT }}>
                      Servir
                    </button>
                    <button disabled={busy === b.id}
                      onClick={() => { const ml = Number(prompt('Merma (ml):', '30')); if (ml > 0) act(b.id, () => barApi.waste(b.id, { ml })) }}
                      className="flex-1 rounded-lg py-2 text-xs font-bold bg-slate-700 text-slate-200 hover:bg-slate-600 disabled:opacity-40 transition-colors">
                      Merma
                    </button>
                    <button disabled={busy === b.id} title="Ajustar por conteo"
                      onClick={() => { const ml = Number(prompt('Restante real (ml):', String(Math.round(Number(b.remaining_ml))))); if (ml >= 0) act(b.id, () => barApi.refill(b.id, ml)) }}
                      className="flex-1 rounded-lg py-2 text-xs font-bold bg-slate-700 text-slate-200 hover:bg-slate-600 disabled:opacity-40 transition-colors">
                      Ajustar
                    </button>
                  </div>
                </div>
              </DaxCard>
            )
          })}
        </div>
      )}
    </div>
  )
}

const inputCls = 'block w-full mt-1.5 rounded-lg bg-slate-800 border border-slate-700 px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-violet-500'
