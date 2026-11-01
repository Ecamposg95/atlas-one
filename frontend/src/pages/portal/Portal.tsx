import { useCallback, useEffect, useState } from 'react'
import { portalApi } from '../../api/portal'
import type { LinkedAccount, CustomerBalance, AccountTransaction, PortalQuote } from '../../api/portal'
import { DaxCard } from '../../components/ui/DaxCard'
import { Spinner } from '../../components/ui/Spinner'
import { ErrorState } from '../../components/ui/ErrorState'
import { formatCurrency } from '../../utils/currency'

type Tab = 'balance' | 'transactions' | 'quotes'

function fmtDate(s: string) {
  return new Date(s).toLocaleDateString('es-MX', { day: 'numeric', month: 'short', year: 'numeric' })
}

const TX_LABELS: Record<string, string> = {
  PURCHASE: 'Compra',
  PAYMENT: 'Pago',
  CREDIT: 'Crédito',
  ADJUSTMENT: 'Ajuste',
  REFUND: 'Devolución',
}

const QUOTE_STATUS_CLASS: Record<string, string> = {
  OPEN: 'bg-amber-500/20 text-amber-400',
  QUOTE: 'bg-blue-500/20 text-blue-400',
  COMPLETED: 'bg-emerald-500/20 text-emerald-400',
  CANCELLED: 'bg-red-500/20 text-red-400',
}

const QUOTE_STATUS_LABEL: Record<string, string> = {
  OPEN: 'Pendiente',
  QUOTE: 'Cotización',
  COMPLETED: 'Completado',
  CANCELLED: 'Cancelado',
}

export function Portal() {
  const [tab, setTab] = useState<Tab>('balance')
  const [loading, setLoading] = useState(true)
  const [accounts, setAccounts] = useState<LinkedAccount[]>([])
  const [balance, setBalance] = useState<CustomerBalance | null>(null)
  const [transactions, setTransactions] = useState<AccountTransaction[]>([])
  const [quotes, setQuotes] = useState<PortalQuote[]>([])
  const [loadError, setLoadError] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setLoadError(false)
    const results = await Promise.allSettled([
      portalApi.getAccounts(),
      portalApi.getBalance(),
      portalApi.getTransactions(),
      portalApi.getQuotes(),
    ])
    const [accsRes, balRes, txsRes, qsRes] = results
    if (accsRes.status === 'fulfilled') setAccounts(Array.isArray(accsRes.value) ? accsRes.value : [])
    if (balRes.status === 'fulfilled') setBalance(balRes.value)
    if (txsRes.status === 'fulfilled') setTransactions(Array.isArray(txsRes.value) ? txsRes.value : [])
    if (qsRes.status === 'fulfilled') setQuotes(Array.isArray(qsRes.value) ? qsRes.value : [])
    // Si TODAS las llamadas clave fallaron, no hay portal que mostrar: es un error de red.
    if (results.every((r) => r.status === 'rejected')) setLoadError(true)
    setLoading(false)
  }, [])

  useEffect(() => { load() }, [load])

  if (loading) return <Spinner text="Cargando portal..." />

  if (loadError) {
    return (
      <div className="max-w-4xl mx-auto">
        <DaxCard>
          <ErrorState message="No se pudo cargar tu portal. Verifica tu conexión." onRetry={load} />
        </DaxCard>
      </div>
    )
  }

  return (
    <div className="space-y-5 max-w-4xl mx-auto">
      {/* Header */}
      <div className="flex items-center gap-3">
        <i className="fa-solid fa-circle-user text-indigo-400 text-2xl" />
        <div>
          <h1 className="text-2xl font-black text-white">Mi Portal</h1>
          <p className="text-slate-500 text-sm">Estado de cuenta y cotizaciones</p>
        </div>
      </div>

      {/* Balance card */}
      {balance && (
        <DaxCard>
          <div className="flex items-center justify-between flex-wrap gap-4">
            <div>
              <p className="text-slate-400 text-xs uppercase tracking-wider mb-1">Saldo actual</p>
              <p className={`text-3xl font-black ${balance.current_balance > 0 ? 'text-dax-danger' : 'text-dax-success'}`}>
                {formatCurrency(balance.current_balance)}
              </p>
              <p className="text-slate-500 text-xs mt-1">Actualizado {fmtDate(balance.last_updated)}</p>
            </div>
            <div className="text-right">
              <p className="text-slate-400 text-xs uppercase tracking-wider mb-1">Cuentas vinculadas</p>
              <p className="text-2xl font-bold text-white">{accounts.length}</p>
            </div>
          </div>
        </DaxCard>
      )}

      {/* Linked accounts */}
      {accounts.length > 0 && (
        <DaxCard>
          <p className="text-xs text-slate-400 uppercase tracking-wider mb-3">Mis cuentas</p>
          <div className="space-y-2">
            {accounts.map((a) => (
              <div key={`${a.organization_id}-${a.customer_id}`}
                className="flex items-center justify-between py-2 border-b border-slate-700/40 last:border-0">
                <div>
                  <p className="text-white text-sm font-medium">{a.organization_name}</p>
                  <p className="text-slate-500 text-xs">ID cliente #{a.customer_id}</p>
                </div>
                <p className={`text-sm font-bold ${a.current_balance > 0 ? 'text-dax-danger' : 'text-dax-success'}`}>
                  {formatCurrency(a.current_balance, { currency: a.currency })}
                </p>
              </div>
            ))}
          </div>
        </DaxCard>
      )}

      {/* Tabs */}
      <div className="flex gap-1 bg-slate-900/60 p-1 rounded-xl w-fit">
        {([['balance', 'Resumen'], ['transactions', 'Movimientos'], ['quotes', 'Cotizaciones']] as [Tab, string][]).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`px-4 py-1.5 rounded-lg text-sm font-semibold transition-colors ${
              tab === key ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-white'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Tab: Movimientos */}
      {tab === 'transactions' && (
        <DaxCard padding={false}>
          {transactions.length === 0 ? (
            <div className="p-12 text-center text-slate-600">
              <i className="fa-solid fa-receipt text-4xl mb-3 block" />
              Sin movimientos registrados
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="dax-table w-full">
                <thead>
                  <tr>
                    <th>Fecha</th>
                    <th>Tipo</th>
                    <th>Descripción</th>
                    <th className="text-right">Monto</th>
                    <th className="text-right">Saldo</th>
                  </tr>
                </thead>
                <tbody>
                  {transactions.map((t) => (
                    <tr key={t.id}>
                      <td className="text-slate-400 text-xs whitespace-nowrap">{fmtDate(t.created_at)}</td>
                      <td>
                        <span className="text-xs font-semibold text-slate-300">
                          {TX_LABELS[t.transaction_type] ?? t.transaction_type}
                        </span>
                      </td>
                      <td className="text-slate-400 text-xs max-w-[200px] truncate">
                        {t.description ?? t.reference ?? '—'}
                      </td>
                      <td className={`text-right font-mono text-sm font-bold ${t.amount < 0 ? 'text-red-400' : 'text-emerald-400'}`}>
                        {formatCurrency(t.amount)}
                      </td>
                      <td className="text-right font-mono text-sm text-slate-300">
                        {formatCurrency(t.balance_after)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </DaxCard>
      )}

      {/* Tab: Cotizaciones */}
      {tab === 'quotes' && (
        <DaxCard padding={false}>
          {quotes.length === 0 ? (
            <div className="p-12 text-center text-slate-600">
              <i className="fa-solid fa-file-invoice text-4xl mb-3 block" />
              Sin cotizaciones
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="dax-table w-full">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Fecha</th>
                    <th>Empresa</th>
                    <th>Artículos</th>
                    <th>Estado</th>
                    <th className="text-right">Total</th>
                  </tr>
                </thead>
                <tbody>
                  {quotes.map((q) => (
                    <tr key={q.id}>
                      <td className="font-mono text-slate-400 text-xs">{q.id.slice(0, 8)}</td>
                      <td className="text-slate-400 text-xs whitespace-nowrap">{fmtDate(q.date)}</td>
                      <td className="text-white text-sm font-medium">{q.organization_name}</td>
                      <td className="text-slate-400 text-xs text-center">{q.items_count}</td>
                      <td>
                        <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${QUOTE_STATUS_CLASS[q.status] ?? 'bg-slate-700/50 text-slate-400'}`}>
                          {QUOTE_STATUS_LABEL[q.status] ?? q.status}
                        </span>
                      </td>
                      <td className="text-right font-mono text-sm font-bold text-white">{formatCurrency(q.total)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </DaxCard>
      )}

      {/* Tab: Resumen (balance tab) */}
      {tab === 'balance' && (
        <DaxCard>
          <p className="text-xs text-slate-400 uppercase tracking-wider mb-4">Últimos movimientos</p>
          {transactions.length === 0 ? (
            <p className="text-slate-600 text-sm text-center py-6">Sin movimientos</p>
          ) : (
            <div className="space-y-2">
              {transactions.slice(0, 5).map((t) => (
                <div key={t.id} className="flex items-center justify-between py-2 border-b border-slate-700/40 last:border-0">
                  <div className="flex items-center gap-3">
                    <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs ${
                      t.amount < 0 ? 'bg-red-500/20 text-red-400' : 'bg-emerald-500/20 text-emerald-400'
                    }`}>
                      <i className={`fa-solid ${t.amount < 0 ? 'fa-arrow-up-right' : 'fa-arrow-down-left'}`} />
                    </div>
                    <div>
                      <p className="text-white text-sm">{TX_LABELS[t.transaction_type] ?? t.transaction_type}</p>
                      <p className="text-slate-500 text-xs">{fmtDate(t.created_at)}</p>
                    </div>
                  </div>
                  <p className={`font-mono font-bold text-sm ${t.amount < 0 ? 'text-red-400' : 'text-emerald-400'}`}>
                    {formatCurrency(t.amount)}
                  </p>
                </div>
              ))}
            </div>
          )}
          {transactions.length > 5 && (
            <button onClick={() => setTab('transactions')}
              className="mt-3 text-xs text-indigo-400 hover:text-indigo-300 flex items-center gap-1">
              Ver todos los movimientos <i className="fa-solid fa-arrow-right" />
            </button>
          )}
        </DaxCard>
      )}
    </div>
  )
}
