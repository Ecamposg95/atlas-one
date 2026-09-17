import { useEffect, useState, useCallback, useMemo } from 'react'
import { salesApi } from '../../api/sales'
import { organizationApi, type Branch } from '../../api/organization'
import client from '../../api/client'
import { DaxCard } from '../../components/ui/DaxCard'
import { Spinner } from '../../components/ui/Spinner'
import { Badge } from '../../components/ui/Badge'
import type { SalesDocument } from '../../types/sales'
import { saleLabel } from '../../types/sales'
import { formatCurrency } from '../../utils/currency'
import { todayStr, daysAgoStr } from '../../utils/dates'

const PRESETS = [
  { label: 'Hoy', start: () => todayStr(), end: () => todayStr() },
  { label: 'Ayer', start: () => daysAgoStr(1), end: () => daysAgoStr(1) },
  { label: 'Semana', start: () => daysAgoStr(7), end: () => todayStr() },
  { label: 'Mes', start: () => daysAgoStr(30), end: () => todayStr() },
]

interface SalesStats {
  total_sales: number
  total_transactions: number
  average_ticket: number
  payment_methods: Record<string, number>
}

export function HQSalesLog() {
  const [sales, setSales] = useState<SalesDocument[]>([])
  const [branches, setBranches] = useState<Branch[]>([])
  const [branchId, setBranchId] = useState<number | ''>('')
  const [loading, setLoading] = useState(true)
  const [startDate, setStartDate] = useState(todayStr())
  const [endDate, setEndDate] = useState(todayStr())
  const [page, setPage] = useState(0)
  const [total, setTotal] = useState(0)
  const [selected, setSel] = useState<SalesDocument | null>(null)
  const [search, setSearch] = useState('')
  const [salesStats, setSalesStats] = useState<SalesStats | null>(null)
  const LIMIT = 100

  const load = useCallback(async (start: string, end: string, pg: number, bid: number | '') => {
    setLoading(true)
    try {
      const params: Record<string, unknown> = { start_date: start, end_date: end, limit: LIMIT, skip: pg * LIMIT }
      if (bid) params.branch_id = bid
      const [res, statsRes] = await Promise.allSettled([
        salesApi.list(params),
        client.get<SalesStats>('/sales/stats', { params: { start_date: start, end_date: end, ...(bid ? { branch_id: bid } : {}) } }),
      ])
      if (res.status === 'fulfilled') {
        setSales(res.value.items ?? [])
        setTotal(res.value.total ?? 0)
      } else {
        setSales([])
      }
      setSalesStats(statsRes.status === 'fulfilled' ? statsRes.value.data : null)
    } catch {
      setSales([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    organizationApi.getBranches().then(setBranches).catch(() => {})
    load(startDate, endDate, 0, '')
  }, [])

  const topMethod = useMemo(() => {
    if (!salesStats?.payment_methods) return null
    const entries = Object.entries(salesStats.payment_methods)
    if (!entries.length) return null
    return entries.sort((a, b) => b[1] - a[1])[0]
  }, [salesStats])

  const filteredSales = useMemo(() => {
    if (!search.trim()) return sales
    const q = search.toLowerCase()
    return sales.filter((s) =>
      saleLabel(s).toLowerCase().includes(q) ||
      (s.customer_name ?? '').toLowerCase().includes(q)
    )
  }, [sales, search])

  const applyPreset = (p: typeof PRESETS[0]) => {
    const s = p.start(), e = p.end()
    setStartDate(s); setEndDate(e); setPage(0); load(s, e, 0, branchId)
  }

  const pages = Math.ceil(total / LIMIT)
  const statusVariant = (s: string) =>
    s === 'CLOSED' ? 'green' : s === 'CANCELLED' ? 'red' : s === 'OPEN' ? 'blue' : 'yellow'

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <i className="fa-solid fa-receipt text-indigo-400 text-xl" />
        <h1 className="text-2xl font-black text-white">Ventas HQ</h1>
      </div>

      {/* KPI Strip */}
      {salesStats && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <DaxCard>
            <p className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Total Ventas</p>
            <p className="text-2xl font-black text-emerald-400 tabular-nums">{formatCurrency(salesStats.total_sales)}</p>
          </DaxCard>
          <DaxCard>
            <p className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Transacciones</p>
            <p className="text-2xl font-black text-white tabular-nums">{salesStats.total_transactions}</p>
          </DaxCard>
          <DaxCard>
            <p className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Ticket Promedio</p>
            <p className="text-2xl font-black text-indigo-400 tabular-nums">{formatCurrency(salesStats.average_ticket)}</p>
          </DaxCard>
          <DaxCard>
            <p className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Método Principal</p>
            <p className="text-2xl font-black text-amber-400 tabular-nums">{topMethod?.[0] ?? '—'}</p>
            {topMethod && <p className="text-[10px] text-slate-600 mt-0.5">{formatCurrency(topMethod[1])} recaudado</p>}
          </DaxCard>
        </div>
      )}

      {/* Filtros */}
      <div className="flex flex-wrap gap-2 items-center">
        {PRESETS.map((p) => (
          <button key={p.label} onClick={() => applyPreset(p)}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
              startDate === p.start() && endDate === p.end()
                ? 'bg-indigo-600 text-white'
                : 'bg-slate-700/50 text-slate-400 hover:text-white'
            }`}>
            {p.label}
          </button>
        ))}
        <select
          value={branchId}
          onChange={(e) => setBranchId(e.target.value ? Number(e.target.value) : '')}
          className="dax-input text-xs max-w-[160px]">
          <option value="">Todas las sucursales</option>
          {branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
        </select>
        <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className="dax-input w-36 text-xs" />
        <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} className="dax-input w-36 text-xs" />
        <input
          type="text"
          placeholder="Buscar folio o cliente..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="dax-input text-xs w-44"
        />
        <button onClick={() => { setPage(0); load(startDate, endDate, 0, branchId) }} className="dax-btn-primary text-xs">
          <i className="fa-solid fa-search" /> Filtrar
        </button>
      </div>

      {/* Tabla */}
      <DaxCard padding={false}>
        {loading ? <Spinner text="Cargando ventas..." /> : filteredSales.length === 0 ? (
          <div className="p-12 text-center text-slate-600">Sin ventas en este período</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="dax-table w-full">
              <thead>
                <tr>
                  <th>Folio</th>
                  <th>Sucursal</th>
                  <th>Fecha</th>
                  <th>Cliente</th>
                  <th className="text-right">Total</th>
                  <th>Pago</th>
                  <th>Estado</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {filteredSales.map((s) => (
                  <tr key={s.id}>
                    <td className="font-mono text-indigo-400 text-xs">{saleLabel(s)}</td>
                    <td className="text-xs text-slate-400">{s.branch_name ?? '—'}</td>
                    <td className="text-xs text-slate-400">
                      {new Date(s.created_at).toLocaleString('es-MX', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}
                    </td>
                    <td className="text-sm">{s.customer_name ?? <span className="text-slate-600 italic">Público general</span>}</td>
                    <td className="text-right font-semibold text-emerald-400">{formatCurrency(s.total_amount)}</td>
                    <td>
                      {s.payments?.map((p, i) => (
                        <span key={i} className="dax-badge dax-badge-blue mr-1">{p.method}</span>
                      ))}
                    </td>
                    <td><Badge variant={statusVariant(s.status) as 'green' | 'red' | 'blue' | 'yellow'}>{s.status}</Badge></td>
                    <td>
                      <button onClick={() => setSel(s)} className="dax-btn-icon text-slate-500 hover:text-white transition-colors text-xs">
                        <i className="fa-solid fa-eye" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {pages > 1 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-slate-700/50">
            <button onClick={() => { const np = page - 1; setPage(np); load(startDate, endDate, np, branchId) }} disabled={page === 0} className="dax-btn-secondary text-xs disabled:opacity-40">← Anterior</button>
            <span className="text-slate-500 text-xs">Pág. {page + 1} / {pages} · {total} registros</span>
            <button onClick={() => { const np = page + 1; setPage(np); load(startDate, endDate, np, branchId) }} disabled={page >= pages - 1} className="dax-btn-secondary text-xs disabled:opacity-40">Siguiente →</button>
          </div>
        )}
      </DaxCard>

      {/* Modal detalle */}
      {selected && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm" onClick={() => setSel(null)}>
          <div className="dax-card p-6 w-full max-w-lg max-h-[80vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <div>
                <p className="text-[10px] text-slate-500 uppercase tracking-widest">Folio</p>
                <p className="text-xl font-black text-indigo-400 font-mono">{saleLabel(selected)}</p>
              </div>
              <button onClick={() => setSel(null)} className="dax-btn-icon text-slate-500 hover:text-white"><i className="fa-solid fa-xmark text-lg" /></button>
            </div>

            <div className="space-y-3 text-sm">
              <div className="flex justify-between"><span className="text-slate-500">Sucursal</span><span>{selected.branch_name ?? '—'}</span></div>
              <div className="flex justify-between"><span className="text-slate-500">Cliente</span><span>{selected.customer_name ?? 'Público general'}</span></div>
              <div className="flex justify-between"><span className="text-slate-500">Fecha</span><span>{new Date(selected.created_at).toLocaleString('es-MX')}</span></div>
              <div className="flex justify-between"><span className="text-slate-500">Estado</span><Badge variant={statusVariant(selected.status) as 'green' | 'red' | 'blue' | 'yellow'}>{selected.status}</Badge></div>
            </div>

            <div className="mt-4 border-t border-slate-700/50 pt-4">
              <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2">Artículos</p>
              <table className="dax-table w-full text-xs">
                <thead><tr><th>Producto</th><th className="text-right">Cant.</th><th className="text-right">Precio</th><th className="text-right">Total</th></tr></thead>
                <tbody>
                  {selected.lines?.map((line, i) => (
                    <tr key={i}>
                      <td>{line.description ?? line.sku ?? '—'}</td>
                      <td className="text-right">{line.quantity}</td>
                      <td className="text-right">{formatCurrency(Number(line.unit_price))}</td>
                      <td className="text-right font-semibold">{formatCurrency(Number(line.total_line))}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="mt-4 border-t border-slate-700/50 pt-4 space-y-1 text-sm">
              <div className="flex justify-between text-slate-400"><span>Subtotal</span><span>{formatCurrency(Number(selected.subtotal))}</span></div>
              {Number(selected.tax_amount) > 0 && <div className="flex justify-between text-slate-400"><span>IVA</span><span>{formatCurrency(Number(selected.tax_amount))}</span></div>}
              <div className="flex justify-between font-black text-white text-base pt-1"><span>Total</span><span>{formatCurrency(selected.total_amount)}</span></div>
              {Number(selected.card_surcharge_amount ?? 0) > 0 && (
                <>
                  <div className="flex justify-between text-slate-400">
                    <span>Comisión tarjeta {selected.card_surcharge_pct ?? ''}%</span>
                    <span>{formatCurrency(Number(selected.card_surcharge_amount))}</span>
                  </div>
                  <div className="flex justify-between font-black text-emerald-400 text-base">
                    <span>Total cobrado</span>
                    <span>{formatCurrency(Number(selected.total_amount) + Number(selected.card_surcharge_amount))}</span>
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
