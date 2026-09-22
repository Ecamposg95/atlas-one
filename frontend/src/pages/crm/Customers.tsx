import { useEffect, useState, useCallback, useRef } from 'react'
import { customersApi, type Customer, type CustomerStats, type LedgerEntry } from '../../api/customers'
import { DaxCard } from '../../components/ui/DaxCard'
import { Spinner } from '../../components/ui/Spinner'
import { Badge } from '../../components/ui/Badge'
import { formatCurrency } from '../../utils/currency'
import { toWaPhone } from '../../utils/phone'
import { CustomerFormModal } from './CustomerFormModal'
import { toast } from '../../store/toastStore'
import { confirm as confirmDialog } from '../../components/ui/ConfirmDialog'
import { ErrorState } from '../../components/ui/ErrorState'
import { useAuthStore } from '../../store/authStore'

interface PayModal { id: number; name: string }

const apiErrorMessage = (err: unknown, fallback: string) => {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return typeof detail === 'string' && detail.trim() ? detail : fallback
}

export function Customers() {
  // Borrar un cliente y registrar un abono son de administrador/dueño; la
  // cajera consulta, da de alta y edita. El backend responde 403 en esos dos
  // endpoints (app/modules/customers/router.py), así que esconder los botones
  // evita ofrecer algo que va a fallar — no es el candado.
  const user = useAuthStore((s) => s.user)
  const esAdmin = user?.role === 'ADMINISTRADOR' || user?.role === 'DUEÑO'
  const [customers, setCustomers] = useState<Customer[]>([])
  const [stats, setStats] = useState<CustomerStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(0)
  const [total, setTotal] = useState(0)
  const [selected, setSelected] = useState<Customer | null>(null)
  const [ledger, setLedger] = useState<LedgerEntry[]>([])
  const [ledgerLoading, setLedgerLoading] = useState(false)
  const [payModal, setPayModal] = useState<PayModal | null>(null)
  const [payAmount, setPayAmount] = useState('')
  const [payLoading, setPayLoading] = useState(false)
  const [formModal, setFormModal] = useState<{ open: boolean; customer: Customer | null }>({ open: false, customer: null })
  const [deleting, setDeleting] = useState(false)
  const [sharing, setSharing] = useState(false)
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [loadError, setLoadError] = useState(false)
  const LIMIT = 50

  const load = useCallback(async (q: string, pg: number) => {
    setLoading(true)
    setLoadError(false)
    try {
      const res = await customersApi.getAll({ search: q || undefined, skip: pg * LIMIT, limit: LIMIT })
      setCustomers(res.items ?? [])
      setTotal(res.total ?? 0)
    } catch { setLoadError(true) } finally { setLoading(false) }
  }, [])

  useEffect(() => {
    customersApi.getStats().then(setStats).catch(() => {})
    load('', 0)
  }, [])

  const onSearch = (val: string) => {
    setSearch(val)
    if (searchTimer.current) clearTimeout(searchTimer.current)
    searchTimer.current = setTimeout(() => { setPage(0); load(val, 0) }, 400)
  }

  const openDetail = async (c: Customer) => {
    setSelected(c)
    setLedgerLoading(true)
    try {
      const data = await customersApi.getStatement(c.id, { limit: 20 })
      setLedger(data)
    } catch { setLedger([]) } finally { setLedgerLoading(false) }
  }

  const handlePay = async () => {
    if (!payModal || !payAmount) return
    setPayLoading(true)
    try {
      await customersApi.pay(payModal.id, { amount: parseFloat(payAmount) })
      setPayModal(null); setPayAmount('')
      await customersApi.getStats().then(setStats).catch(() => {})
      load(search, page)
      if (selected?.id === payModal.id) openDetail({ ...selected })
    } catch (err) {
      toast.error(apiErrorMessage(err, 'No se pudo registrar el pago'))
    } finally { setPayLoading(false) }
  }

  const pages = Math.ceil(total / LIMIT)
  const balanceColor = (b: number) => b > 0 ? 'text-red-400' : b < 0 ? 'text-emerald-400' : 'text-slate-400'

  const downloadBlob = (blob: Blob, filename: string) => {
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = filename; a.click()
    URL.revokeObjectURL(url)
  }

  const handlePdf = async (c: Customer) => {
    setSharing(true)
    try {
      const blob = await customersApi.getStatementPdf(c.id)
      downloadBlob(blob, `EdoCuenta_${c.name.replace(/[^\w-]+/g, '_')}.pdf`)
    } catch { toast.error('No se pudo generar el PDF del estado de cuenta') } finally { setSharing(false) }
  }

  const handleWhatsApp = async (c: Customer) => {
    setSharing(true)
    try {
      const blob = await customersApi.getStatementPdf(c.id)
      const file = new File([blob], `EdoCuenta_${c.name.replace(/[^\w-]+/g, '_')}.pdf`, { type: 'application/pdf' })
      const shareData = { files: [file], title: 'Estado de cuenta', text: `Estado de cuenta de ${c.name}` }
      if (typeof navigator.canShare === 'function' && navigator.canShare(shareData)) {
        // Móvil: share sheet nativo — el usuario elige WhatsApp y el PDF va adjunto
        try { await navigator.share(shareData) } catch { /* usuario canceló: no es error */ }
      } else {
        // Escritorio: descarga + chat de WhatsApp con mensaje; el PDF se adjunta a mano
        downloadBlob(blob, file.name)
        const tel = toWaPhone(c.phone)
        if (tel) {
          const msg = `Hola ${c.name}, te comparto tu estado de cuenta al ${new Date().toLocaleDateString('es-MX')}. Saldo: ${formatCurrency(c.current_balance)}.`
          window.open(`https://wa.me/${tel}?text=${encodeURIComponent(msg)}`, '_blank')
        }
      }
    } catch { toast.error('No se pudo generar el PDF del estado de cuenta') } finally { setSharing(false) }
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <i className="fa-solid fa-address-book text-indigo-400 text-xl" />
        <h1 className="text-2xl font-black text-white">Clientes</h1>
      </div>

      {/* KPI Cards */}
      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[
            { label: 'Total clientes', value: String(stats.total), icon: 'fa-users', color: 'text-white' },
            { label: 'Con deuda', value: String(stats.with_debt), icon: 'fa-exclamation-circle', color: 'text-red-400' },
            { label: 'Deuda total', value: formatCurrency(stats.total_debt), icon: 'fa-coins', color: 'text-red-400' },
            { label: 'Saldo a favor', value: String(stats.with_credit), icon: 'fa-circle-check', color: 'text-emerald-400' },
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

      {/* Búsqueda */}
      <div className="flex gap-2">
        <input
          type="text" placeholder="Buscar por nombre, teléfono, RFC..."
          value={search} onChange={(e) => onSearch(e.target.value)}
          className="dax-input flex-1 text-sm" />
        <button onClick={() => setFormModal({ open: true, customer: null })} className="dax-btn-primary text-sm whitespace-nowrap">
          <i className="fa-solid fa-user-plus" /> Nuevo cliente
        </button>
      </div>

      {/* Tabla */}
      <DaxCard padding={false}>
        {loading ? <Spinner text="Cargando clientes..." /> : loadError ? (
          <ErrorState onRetry={() => load(search, page)} />
        ) : customers.length === 0 ? (
          <div className="p-12 text-center text-slate-600">Sin clientes encontrados</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="dax-table w-full">
              <thead>
                <tr>
                  <th>Nombre</th>
                  <th>Teléfono</th>
                  <th>RFC</th>
                  <th className="text-right">Saldo</th>
                  <th className="text-right">Crédito</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {customers.map((c) => (
                  <tr key={c.id}>
                    <td className="font-semibold text-white">{c.name}</td>
                    <td className="text-slate-400 text-sm">{c.phone ?? '—'}</td>
                    <td className="text-slate-400 text-xs font-mono">{c.tax_id ?? '—'}</td>
                    <td className={`text-right font-semibold tabular-nums ${balanceColor(c.current_balance)}`}>{formatCurrency(c.current_balance)}</td>
                    <td className="text-right text-slate-500 text-sm tabular-nums">{c.credit_limit != null ? formatCurrency(c.credit_limit) : '—'}</td>
                    <td>
                      <button onClick={() => openDetail(c)} className="dax-btn-icon text-slate-500 hover:text-white text-xs mr-2">
                        <i className="fa-solid fa-eye" />
                      </button>
                      {esAdmin && c.current_balance > 0 && (
                        <button onClick={() => setPayModal({ id: c.id, name: c.name })} className="text-emerald-500 hover:text-emerald-400 text-xs">
                          <i className="fa-solid fa-money-bill-wave" />
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {pages > 1 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-slate-700/50">
            <button onClick={() => { const np = page - 1; setPage(np); load(search, np) }} disabled={page === 0} className="dax-btn-secondary text-xs disabled:opacity-40">← Anterior</button>
            <span className="text-slate-500 text-xs">Pág. {page + 1} / {pages} · {total} clientes</span>
            <button onClick={() => { const np = page + 1; setPage(np); load(search, np) }} disabled={page >= pages - 1} className="dax-btn-secondary text-xs disabled:opacity-40">Siguiente →</button>
          </div>
        )}
      </DaxCard>

      {/* Modal estado de cuenta */}
      {selected && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm" onClick={() => setSelected(null)}>
          <div className="dax-card p-6 w-full max-w-lg max-h-[85vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <div>
                <p className="text-[10px] text-slate-500 uppercase tracking-widest">Cliente</p>
                <p className="text-xl font-black text-white">{selected.name}</p>
              </div>
              <div className="flex items-center gap-3">
                <button onClick={() => setFormModal({ open: true, customer: selected })}
                  className="text-slate-500 hover:text-white" title="Editar">
                  <i className="fa-solid fa-pen" />
                </button>
                {esAdmin && <button
                  onClick={async () => {
                    const ok = await confirmDialog({
                      title: `Eliminar a ${selected.name}`,
                      message: 'El cliente se eliminará; su historial de movimientos se conserva.',
                      variant: 'danger',
                      confirmText: 'Eliminar',
                    })
                    if (!ok) return
                    setDeleting(true)
                    try {
                      await customersApi.delete(selected.id)
                      setSelected(null)
                      customersApi.getStats().then(setStats).catch(() => {})
                      load(search, page)
                    } catch (e) {
                      toast.error(apiErrorMessage(e, 'No se pudo eliminar el cliente'))
                    } finally { setDeleting(false) }
                  }}
                  className="text-slate-500 hover:text-red-400 disabled:opacity-40" title="Eliminar" disabled={deleting}>
                  <i className="fa-solid fa-trash" />
                </button>}
                <button onClick={() => setSelected(null)} className="dax-btn-icon text-slate-500 hover:text-white"><i className="fa-solid fa-xmark text-lg" /></button>
              </div>
            </div>

            <div className="grid grid-cols-3 gap-2 mb-4">
              <div className="dax-card p-3 text-center">
                <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-0.5">Saldo</p>
                <p className={`font-black text-lg tabular-nums ${balanceColor(selected.current_balance)}`}>{formatCurrency(selected.current_balance)}</p>
              </div>
              <div className="dax-card p-3 text-center">
                <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-0.5">Crédito</p>
                <p className="font-black text-lg text-slate-300 tabular-nums">{selected.credit_limit != null ? formatCurrency(selected.credit_limit) : '—'}</p>
              </div>
              <div className="dax-card p-3 text-center">
                <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-0.5">RFC</p>
                <p className="font-mono text-sm text-slate-400">{selected.tax_id ?? '—'}</p>
              </div>
            </div>

            {esAdmin && selected.current_balance > 0 && (
              <button onClick={() => setPayModal({ id: selected.id, name: selected.name })}
                className="dax-btn-primary w-full justify-center mb-4 text-sm">
                <i className="fa-solid fa-money-bill-wave" /> Registrar Pago
              </button>
            )}

            <div className="grid grid-cols-2 gap-2 mb-4">
              <button onClick={() => handlePdf(selected)} disabled={sharing}
                className="dax-btn-secondary justify-center text-sm disabled:opacity-40">
                <i className="fa-solid fa-file-pdf text-red-400" /> Descargar PDF
              </button>
              <button onClick={() => handleWhatsApp(selected)} disabled={sharing || !toWaPhone(selected.phone)}
                title={!toWaPhone(selected.phone) ? 'El cliente no tiene teléfono válido' : 'Enviar por WhatsApp'}
                className="dax-btn-secondary justify-center text-sm disabled:opacity-40">
                <i className="fa-brands fa-whatsapp text-emerald-400" /> WhatsApp
              </button>
            </div>

            <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2">Estado de Cuenta</p>
            {ledgerLoading ? <Spinner text="Cargando..." /> : ledger.length === 0 ? (
              <p className="text-center text-slate-600 py-6">Sin movimientos</p>
            ) : (
              <div className="space-y-1">
                {ledger.map((e) => (
                  <div key={e.id} className="flex items-center justify-between text-xs py-1.5 border-b border-slate-700/30">
                    <div>
                      <p className="text-slate-300">{e.description ?? '—'}</p>
                      <p className="text-slate-600">{new Date(e.created_at).toLocaleDateString('es-MX')}{e.sales_document_id && ` · ${e.sales_document_id}`}</p>
                    </div>
                    <p className={`font-semibold tabular-nums ${e.amount >= 0 ? 'text-red-400' : 'text-emerald-400'}`}>
                      {e.amount >= 0 ? '+' : ''}{formatCurrency(e.amount)}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Modal pago */}
      {payModal && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm" onClick={() => { setPayModal(null); setPayAmount('') }}>
          <div className="dax-card p-6 w-full max-w-sm" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-lg font-black text-white mb-4">Registrar Pago</h3>
            <p className="text-slate-400 text-sm mb-4">{payModal.name}</p>
            <div className="space-y-3">
              <div>
                <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wider block mb-1">Monto</label>
                <input type="number" step="0.01" value={payAmount} onChange={(e) => setPayAmount(e.target.value)}
                  placeholder="0.00" className="dax-input w-full text-lg font-bold" autoFocus />
              </div>
            </div>
            <div className="flex gap-2 mt-4">
              <button onClick={() => { setPayModal(null); setPayAmount('') }} className="dax-btn-secondary flex-1">Cancelar</button>
              <button onClick={handlePay} disabled={!payAmount || payLoading} className="dax-btn-primary flex-1 justify-center disabled:opacity-40">
                {payLoading ? <i className="fa-solid fa-spinner fa-spin" /> : <><i className="fa-solid fa-check" /> Confirmar</>}
              </button>
            </div>
          </div>
        </div>
      )}

      {formModal.open && (
        <CustomerFormModal
          customer={formModal.customer}
          onClose={() => setFormModal({ open: false, customer: null })}
          onSaved={(saved) => {
            setFormModal({ open: false, customer: null })
            customersApi.getStats().then(setStats).catch(() => {})
            load(search, page)
            if (selected && selected.id === saved.id) setSelected(saved)
          }}
        />
      )}
    </div>
  )
}
