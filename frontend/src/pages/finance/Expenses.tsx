import { useEffect, useState, useCallback } from 'react'
import { expensesApi, type Expense, type ExpenseStats, type ExpenseCreate } from '../../api/expenses'
import { DaxCard } from '../../components/ui/DaxCard'
import { Spinner } from '../../components/ui/Spinner'
import { Modal } from '../../components/ui/Modal'
import { CabeceraPagina } from '../../components/ui/CabeceraPagina'
import { BarraFiltros, ParFechas } from '../../components/ui/BarraFiltros'
import { ListaTarjetas } from '../../components/ui/ListaTarjetas'
import { TarjetaFila } from '../../components/ui/TarjetaFila'
import { useEsTelefono } from '../../hooks/useIsMobile'
import { toast } from '../../store/toastStore'
import { confirm as confirmDialog } from '../../components/ui/ConfirmDialog'
import { formatCurrency } from '../../utils/currency'
import { todayStr, daysAgoStr } from '../../utils/dates'

const EMPTY_FORM: ExpenseCreate = { amount: 0, category: '', description: '' }
const CATEGORIAS_BASE = ['ALQUILER', 'SERVICIOS', 'SUMINISTROS', 'NÓMINA', 'MANTENIMIENTO', 'MARKETING', 'LOGÍSTICA', 'OTRO']

const fecha = (s: string) => new Date(s).toLocaleDateString('es-MX', { day: '2-digit', month: 'short' })

export function Expenses() {
  const [expenses, setExpenses] = useState<Expense[]>([])
  const [stats, setStats] = useState<ExpenseStats | null>(null)
  const [categories, setCategories] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [startDate, setStartDate] = useState(daysAgoStr(30))
  const [endDate, setEndDate] = useState(todayStr())
  const [filterCat, setFilterCat] = useState('')
  const [modal, setModal] = useState(false)
  const [form, setForm] = useState<ExpenseCreate>(EMPTY_FORM)
  const [saving, setSaving] = useState(false)
  const esTelefono = useEsTelefono()

  const load = useCallback(async (start: string, end: string, cat: string) => {
    setLoading(true)
    try {
      const res = await expensesApi.list({ date_start: start, date_end: end, category: cat || undefined, limit: 100 })
      setExpenses(res.items ?? [])
    } catch { setExpenses([]) } finally { setLoading(false) }
  }, [])

  const loadStats = useCallback(async () => {
    expensesApi.getStats().then(setStats).catch(() => {})
    expensesApi.getCategories().then(setCategories).catch(() => {})
  }, [])

  useEffect(() => {
    loadStats()
    load(startDate, endDate, '')
  }, [])

  const handleCreate = async () => {
    if (!form.amount || !form.category) return
    setSaving(true)
    try {
      await expensesApi.create(form)
      setModal(false); setForm(EMPTY_FORM)
      loadStats(); load(startDate, endDate, filterCat)
    } catch { toast.error('Error al registrar el gasto') } finally { setSaving(false) }
  }

  const handleDelete = async (expense: Expense) => {
    const ok = await confirmDialog({
      title: 'Eliminar gasto',
      message: `¿Eliminar el gasto de ${formatCurrency(expense.amount)} (${expense.category})?`,
      variant: 'danger',
      confirmText: 'Eliminar',
    })
    if (!ok) return
    try {
      await expensesApi.delete(expense.id)
      setExpenses((prev) => prev.filter((e) => e.id !== expense.id))
      loadStats()
    } catch { toast.error('Error al eliminar el gasto') }
  }

  return (
    <div className="space-y-5">
      <CabeceraPagina
        titulo={<div className="flex items-center gap-3">
          <i className="fa-solid fa-money-bill-wave text-indigo-400 text-xl" />
          <h1 className="text-2xl font-black text-white">Gastos</h1>
        </div>}
        accionPrincipal={<button onClick={() => setModal(true)} className="dax-btn-primary text-xs">
          <i className="fa-solid fa-plus" /> Registrar Gasto
        </button>}
      />

      {/* KPIs */}
      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[
            { label: 'Este mes', value: formatCurrency(stats.total_month), icon: 'fa-calendar', color: 'text-red-400' },
            { label: 'Esta semana', value: formatCurrency(stats.total_week), icon: 'fa-calendar-week', color: 'text-amber-400' },
            { label: 'Registros mes', value: String(stats.count_month), icon: 'fa-receipt', color: 'text-white' },
            { label: 'Promedio diario', value: formatCurrency(stats.avg_daily), icon: 'fa-chart-bar', color: 'text-indigo-400' },
          ].map((k) => (
            <DaxCard key={k.label}>
              <div className="flex items-center gap-2 mb-1">
                <i className={`fa-solid ${k.icon} text-slate-500 text-xs`} />
                <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">{k.label}</p>
              </div>
              <p className={`text-xl font-black tabular-nums ${k.color}`}>{k.value}</p>
            </DaxCard>
          ))}
        </div>
      )}

      {/* Categorías breakdown */}
      {stats?.by_category && stats.by_category.length > 0 && (
        <DaxCard>
          <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-3">Por Categoría (Mes)</p>
          <div className="space-y-2">
            {stats.by_category.map((c) => {
              const pct = stats.total_month > 0 ? (c.total / stats.total_month) * 100 : 0
              return (
                <div key={c.category}>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-slate-400">{c.category}</span>
                    <span className="text-white font-semibold">{formatCurrency(c.total)}</span>
                  </div>
                  <div className="h-1.5 bg-slate-700 rounded-full">
                    <div className="h-full bg-red-500/60 rounded-full" style={{ width: `${pct}%` }} />
                  </div>
                </div>
              )
            })}
          </div>
        </DaxCard>
      )}

      {/* Filtros */}
      <BarraFiltros className="sm:items-center">
        <select value={filterCat} onChange={(e) => setFilterCat(e.target.value)} className="dax-input text-xs max-w-[160px]">
          <option value="">Todas las categorías</option>
          {categories.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <ParFechas>
          <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className="dax-input w-36 text-xs" />
          <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} className="dax-input w-36 text-xs" />
        </ParFechas>
        <button onClick={() => load(startDate, endDate, filterCat)} className="dax-btn-primary text-xs max-md:min-h-[44px]">
          <i className="fa-solid fa-search" /> Filtrar
        </button>
      </BarraFiltros>

      {/* Lista */}
      <DaxCard padding={false}>
        {esTelefono ? (
          <ListaTarjetas cargando={loading} vacio={expenses.length === 0} textoVacio="Sin gastos en este período" className="p-3">
            {expenses.map((e) => (
              <TarjetaFila key={e.id}
                titulo={e.description ?? e.category}
                subtitulo={`${fecha(e.created_at)} · ${e.branch_name ?? '—'} · ${e.user_name ?? '—'}`}
                importe={<span className="text-red-400">{formatCurrency(e.amount)}</span>}
                estado={<span className="dax-badge dax-badge-slate">{e.category}</span>}
                acciones={<button onClick={() => handleDelete(e)} aria-label={`Eliminar gasto de ${formatCurrency(e.amount)}`} className="dax-btn-danger text-xs">
                  <i className="fa-solid fa-trash" /> Eliminar
                </button>}
              />
            ))}
          </ListaTarjetas>
        ) : loading ? <Spinner text="Cargando gastos..." /> : expenses.length === 0 ? (
          <div className="p-12 text-center text-slate-600">Sin gastos en este período</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="dax-table w-full">
              <thead>
                <tr>
                  <th>Fecha</th>
                  <th>Categoría</th>
                  <th>Descripción</th>
                  <th>Sucursal</th>
                  <th>Registró</th>
                  <th className="text-right">Monto</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {expenses.map((e) => (
                  <tr key={e.id}>
                    <td className="text-xs text-slate-400">{fecha(e.created_at)}</td>
                    <td>
                      <span className="dax-badge dax-badge-slate">{e.category}</span>
                    </td>
                    <td className="text-slate-300 text-sm max-w-[200px] truncate">{e.description ?? '—'}</td>
                    <td className="text-slate-400 text-xs">{e.branch_name ?? '—'}</td>
                    <td className="text-slate-500 text-xs">{e.user_name ?? '—'}</td>
                    <td className="text-right font-semibold text-red-400 tabular-nums">{formatCurrency(e.amount)}</td>
                    <td>
                      <button onClick={() => handleDelete(e)} aria-label={`Eliminar gasto de ${formatCurrency(e.amount)}`} className="dax-btn-icon text-slate-600 hover:text-red-400 text-xs">
                        <i className="fa-solid fa-trash" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </DaxCard>

      {/* Modal nuevo gasto */}
      <Modal open={modal} onClose={() => setModal(false)} title="Nuevo Gasto" size="sm"
        footer={<>
          <button onClick={() => setModal(false)} className="dax-btn-secondary flex-1">Cancelar</button>
          <button onClick={handleCreate} disabled={saving || !form.amount || !form.category} className="dax-btn-primary flex-1 justify-center disabled:opacity-40">
            {saving ? <i className="fa-solid fa-spinner fa-spin" /> : <><i className="fa-solid fa-check" /> Registrar</>}
          </button>
        </>}>
        <div className="space-y-3">
          <div>
            <label className="dax-label">Monto</label>
            <input type="number" step="0.01" value={form.amount || ''} onChange={(e) => setForm((p) => ({ ...p, amount: parseFloat(e.target.value) || 0 }))}
              className="dax-input w-full text-lg font-bold" placeholder="0.00" autoFocus />
          </div>
          <div>
            <label className="dax-label">Categoría</label>
            <select value={form.category}
              onChange={(e) => setForm((p) => ({ ...p, category: e.target.value }))}
              className="dax-input w-full">
              <option value="">Seleccionar...</option>
              {(categories.length > 0 ? categories : CATEGORIAS_BASE).map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div>
            <label className="dax-label">Descripción (opcional)</label>
            <input value={form.description ?? ''} onChange={(e) => setForm((p) => ({ ...p, description: e.target.value }))}
              className="dax-input w-full" placeholder="Detalle del gasto" />
          </div>
        </div>
      </Modal>
    </div>
  )
}
