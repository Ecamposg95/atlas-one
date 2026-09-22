import { useEffect, useState, useCallback } from 'react'
import { BLIND_MASK, BLIND_LABEL, isValidCount, shouldRevealExpected } from '../../utils/blindCash'
import { useIsBranchUser } from '../../components/branch/useIsBranchUser'
import { CashBranchView } from '../../components/branch/CashBranchView'
import { cashApi, type CashSummary } from '../../api/cash'
import { printerApi } from '../../api/printer'
import { usePOSStore } from '../../store/posStore'
import type { CashSession } from '../../types/cash'
import { DaxCard } from '../../components/ui/DaxCard'
import { Spinner } from '../../components/ui/Spinner'
import { formatCurrency } from '../../utils/currency'
import { toast } from '../../store/toastStore'

// Surface FastAPI `detail` so 409/422 messages reach the user.
function serverDetail(err: unknown, fallback: string): string {
  const detail = (err as any)?.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  return fallback
}

function MovementModal({ type, onClose, onConfirm }: { type: 'IN' | 'OUT'; onClose: () => void; onConfirm: (amount: number, concept: string) => Promise<void> }) {
  const [amount, setAmount] = useState('')
  const [concept, setConcept] = useState('')
  const [loading, setLoading] = useState(false)

  const submit = async () => {
    const amt = parseFloat(amount)
    if (!amt || amt <= 0 || !concept.trim()) return
    setLoading(true)
    try { await onConfirm(amt, concept) } finally { setLoading(false) }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm" onClick={onClose}>
      <div className="dax-card p-6 w-full max-w-sm" onClick={(e) => e.stopPropagation()}>
        <h3 className="text-lg font-black text-white mb-4">
          {type === 'IN' ? '💰 Entrada de Efectivo' : '💸 Salida / Gasto'}
        </h3>
        <div className="space-y-3">
          <div>
            <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1">Monto</label>
            <input type="number" value={amount} onChange={(e) => setAmount(e.target.value)} className="dax-input" placeholder="0.00" min="0" step="0.01" autoFocus />
          </div>
          <div>
            <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1">Concepto</label>
            <input type="text" value={concept} onChange={(e) => setConcept(e.target.value)} className="dax-input" placeholder="Ej: Fondo de cambio, Gasto operativo..." />
          </div>
        </div>
        <div className="flex gap-2 mt-5">
          <button onClick={onClose} className="dax-btn-secondary flex-1">Cancelar</button>
          <button onClick={submit} disabled={loading || !amount || !concept} className={`flex-1 ${type === 'IN' ? 'dax-btn-primary' : 'dax-btn-danger'} justify-center`}>
            {loading ? <i className="fa-solid fa-spinner fa-spin" /> : `Registrar ${type === 'IN' ? 'Entrada' : 'Salida'}`}
          </button>
        </div>
      </div>
    </div>
  )
}

function CloseModal({ summary, onClose, onConfirm }: { summary: CashSummary; onClose: () => void; onConfirm: (amount: number) => Promise<void> }) {
  // Conteo ciego: NO pre-llenar con el esperado. Esta pantalla se habia quedado
  // fuera del arreglo de CashBranchView, asi que aqui se seguia cerrando con un
  // clic y diferencia 0.00.
  const [closing, setClosing] = useState('')
  const [loading, setLoading] = useState(false)

  const diff = parseFloat(closing) - summary.expected_cash

  const submit = async () => {
    if (!isValidCount(closing)) return
    setLoading(true)
    try { await onConfirm(parseFloat(closing)) } finally { setLoading(false) }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm" onClick={onClose}>
      <div className="dax-card p-6 w-full max-w-md" onClick={(e) => e.stopPropagation()}>
        <h3 className="text-lg font-black text-white mb-4">Finalizar Turno</h3>
        <div className="space-y-3 text-sm mb-4">
          <div className="flex justify-between"><span className="text-slate-500">Fondo inicial</span><span>{formatCurrency(summary.opening_amount)}</span></div>
          <div className="flex justify-between"><span className="text-slate-500">Ventas efectivo</span><span>{formatCurrency(summary.total_cash)}</span></div>
          <div className="flex justify-between"><span className="text-slate-500">Entradas</span><span className="text-emerald-400">+{formatCurrency(summary.total_inflows)}</span></div>
          <div className="flex justify-between"><span className="text-slate-500">Salidas</span><span className="text-red-400">-{formatCurrency(summary.total_outflows)}</span></div>
          {summary.cash_refunds > 0 && (
            <div className="flex justify-between">
              <span className="text-slate-500">Reembolsos efectivo {summary.returns_count > 0 ? `(${summary.returns_count})` : ''}</span>
              <span className="text-red-400">-{formatCurrency(summary.cash_refunds)}</span>
            </div>
          )}
          <div className="flex justify-between font-bold text-white border-t border-slate-700/50 pt-2">
            <span>Esperado en caja</span>
            <span title={`${BLIND_LABEL} — cuenta el efectivo y captúralo abajo`}>
              {shouldRevealExpected(closing) ? formatCurrency(summary.expected_cash) : BLIND_MASK}
            </span>
          </div>
        </div>
        <div>
          <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1">Efectivo contado</label>
          <input type="number" value={closing} onChange={(e) => setClosing(e.target.value)} className="dax-input" step="0.01" />
          {diff !== 0 && (
            <p className={`text-xs mt-1 ${diff > 0 ? 'text-emerald-400' : 'text-red-400'}`}>
              Diferencia: {diff > 0 ? '+' : ''}{formatCurrency(diff)}
            </p>
          )}
        </div>
        <div className="flex gap-2 mt-5">
          <button onClick={onClose} className="dax-btn-secondary flex-1">Cancelar</button>
          <button onClick={submit} disabled={loading} className="dax-btn-danger flex-1 justify-center">
            {loading ? <i className="fa-solid fa-spinner fa-spin" /> : <><i className="fa-solid fa-lock" /> Cerrar Turno</>}
          </button>
        </div>
      </div>
    </div>
  )
}

export function CashHistory() {
  if (useIsBranchUser()) return <CashBranchView />
  return <CashHistoryHQView />
}

// Separado para no romper Rules of Hooks: el return condicional de arriba
// no puede convivir con hooks en el mismo componente.
function CashHistoryHQView() {
  const printerName = usePOSStore(s => s.printerName)
  const [session, setSession] = useState<CashSession | null>(null)
  const [summary, setSummary] = useState<CashSummary | null>(null)
  const [history, setHistory] = useState<CashSession[]>([])
  const [loading, setLoading] = useState(true)
  const [modal, setModal] = useState<'IN' | 'OUT' | 'CLOSE' | null>(null)
  const [printingId, setPrintingId] = useState<number | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const s = await cashApi.getStatus()
      setSession(s)
      if (s?.status === 'OPEN') {
        const sum = await cashApi.getSummary().catch(() => null)
        setSummary(sum)
      } else {
        setSummary(null)
      }
      const hist = await cashApi.history(0, 20).catch(() => [] as CashSession[])
      setHistory(hist)
    } catch {
      setSession(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const handleMovement = async (amount: number, concept: string) => {
    try {
      if (modal === 'IN') await cashApi.inflow(amount, concept)
      else await cashApi.outflow(amount, concept)
    } catch (err) {
      // El modal queda abierto para reintentar; el movimiento NO se registró.
      toast.error(serverDetail(err, 'No se pudo registrar el movimiento. Verifica tu conexión e intenta de nuevo.'))
      return
    }
    setModal(null)
    toast.success(modal === 'IN' ? 'Entrada registrada' : 'Salida registrada')
    load()
  }

  const handleClose = async (closingAmount: number) => {
    try {
      await cashApi.close(closingAmount)
    } catch (err) {
      // El turno sigue ABIERTO en el servidor; no se cierra la UI en falso.
      toast.error(serverDetail(err, 'No se pudo cerrar el turno. El turno sigue abierto; intenta de nuevo.'))
      return
    }
    setModal(null)
    toast.success('Turno cerrado')
    load()
  }

  const downloadPdf = async (sessionId: number) => {
    const blob = await cashApi.getPdf(sessionId)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = `corte-${sessionId}.pdf`; a.click()
    URL.revokeObjectURL(url)
  }

  const printCut = async (sessionId: number) => {
    if (!printerName) return
    setPrintingId(sessionId)
    try {
      const b64 = await printerApi.getCashCutBase64(sessionId)
      if (b64) await printerApi.printViaAgent(printerName, b64)
    } catch { /* silencioso */ } finally { setPrintingId(null) }
  }

  if (loading) return <Spinner text="Cargando control de caja..." />

  const noSession = !session || session.status !== 'OPEN'
  const fmtDate = (s: string) =>
    new Date(s).toLocaleString('es-MX', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <i className="fa-solid fa-vault text-indigo-400 text-xl" />
          <h1 className="text-2xl font-black text-white">Control de Caja</h1>
        </div>
        <div className="flex gap-2">
          <button onClick={load} className="dax-btn-secondary text-xs"><i className="fa-solid fa-rotate-right" /></button>
          {session?.id && <button onClick={() => downloadPdf(session.id)} className="dax-btn-secondary text-xs"><i className="fa-solid fa-file-pdf" /> PDF</button>}
        </div>
      </div>

      {noSession ? (
        <DaxCard>
          <div className="text-center py-8">
            <i className="fa-solid fa-lock text-slate-600 text-4xl mb-4" />
            <p className="text-slate-400 font-semibold">No hay turno activo</p>
            <p className="text-slate-600 text-sm mt-1">Abre un turno desde el Punto de Venta</p>
          </div>
        </DaxCard>
      ) : (
        <>
          {/* KPIs */}
          {summary && (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {[
                { label: 'Ventas totales', value: formatCurrency(summary.total_sales), icon: 'fa-coins', color: 'text-emerald-400' },
                { label: 'Efectivo', value: formatCurrency(summary.total_cash), icon: 'fa-money-bill', color: 'text-white' },
                { label: 'Tarjeta', value: formatCurrency(summary.total_card), icon: 'fa-credit-card', color: 'text-indigo-400' },
                { label: 'Transferencia', value: formatCurrency(summary.total_transfer), icon: 'fa-mobile-screen', color: 'text-blue-400' },
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

          {/* Flujo de efectivo */}
          {summary && (
            <div className="grid grid-cols-2 gap-3">
              <DaxCard>
                <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-1">Entradas manuales</p>
                <p className="text-2xl font-black text-emerald-400 tabular-nums">+{formatCurrency(summary.total_inflows)}</p>
              </DaxCard>
              <DaxCard>
                <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-1">Salidas / Gastos</p>
                <p className="text-2xl font-black text-red-400 tabular-nums">-{formatCurrency(summary.total_outflows)}</p>
              </DaxCard>
            </div>
          )}

          {/* Movimientos recientes */}
          {summary?.movements && summary.movements.length > 0 && (
            <DaxCard padding={false}>
              <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest px-4 py-3 border-b border-slate-700/50">Movimientos recientes</p>
              <table className="dax-table w-full">
                <thead><tr><th>Tipo</th><th>Concepto</th><th className="text-right">Monto</th><th>Hora</th></tr></thead>
                <tbody>
                  {summary.movements.map((m) => (
                    <tr key={m.id}>
                      <td><span className={`dax-badge ${m.type === 'IN' ? 'dax-badge-green' : 'dax-badge-red'}`}>{m.type === 'IN' ? 'Entrada' : 'Salida'}</span></td>
                      <td className="text-sm">{m.concept}</td>
                      <td className={`text-right font-semibold ${m.type === 'IN' ? 'text-emerald-400' : 'text-red-400'}`}>
                        {m.type === 'IN' ? '+' : '-'}{formatCurrency(m.amount)}
                      </td>
                      <td className="text-xs text-slate-500">
                        {new Date(m.created_at).toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' })}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </DaxCard>
          )}

          {/* Acciones */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <button onClick={() => setModal('IN')} className="dax-card p-4 text-center hover:border-emerald-500/40 transition-colors group">
              <i className="fa-solid fa-arrow-down text-emerald-400 text-xl mb-2 group-hover:scale-110 transition-transform block" />
              <p className="text-sm font-semibold text-white">Entrada</p>
            </button>
            <button onClick={() => setModal('OUT')} className="dax-card p-4 text-center hover:border-red-500/40 transition-colors group">
              <i className="fa-solid fa-arrow-up text-red-400 text-xl mb-2 group-hover:scale-110 transition-transform block" />
              <p className="text-sm font-semibold text-white">Salida / Gasto</p>
            </button>
            <button onClick={() => { }} className="dax-card p-4 text-center opacity-40 cursor-not-allowed">
              <i className="fa-solid fa-scissors text-slate-400 text-xl mb-2 block" />
              <p className="text-sm font-semibold text-slate-400">Corte Parcial</p>
            </button>
            <button onClick={() => session?.id && downloadPdf(session.id)} className="dax-card p-4 text-center hover:border-indigo-500/40 transition-colors group">
              <i className="fa-solid fa-file-pdf text-indigo-400 text-xl mb-2 group-hover:scale-110 transition-transform block" />
              <p className="text-sm font-semibold text-white">Exportar PDF</p>
            </button>
          </div>

          {/* Cerrar turno */}
          <button
            onClick={async () => {
              const sum = await cashApi.getSummary().catch(() => null)
              if (sum) { setSummary(sum); setModal('CLOSE') }
            }}
            className="w-full dax-btn-danger py-4 text-base font-black justify-center"
          >
            <i className="fa-solid fa-lock" /> Finalizar Turno
          </button>
        </>
      )}

      {/* Historial de cortes */}
      {history.length > 0 && (
        <DaxCard padding={false}>
          <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest px-4 py-3 border-b border-slate-700/50">
            Historial de cortes
          </p>
          <div className="overflow-x-auto">
            <table className="dax-table w-full text-xs">
              <thead>
                <tr>
                  <th>Apertura</th>
                  <th>Cierre</th>
                  <th>Cajero</th>
                  <th className="text-right">Fondo</th>
                  <th className="text-right">Cierre reportado</th>
                  <th>Estado</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {history.map((h) => (
                  <tr key={h.id}>
                    <td className="text-slate-400">{fmtDate(h.opened_at)}</td>
                    <td className="text-slate-400">{h.closed_at ? fmtDate(h.closed_at) : <span className="text-emerald-400">Activo</span>}</td>
                    <td>{h.user_name ?? `#${h.user_id}`}</td>
                    <td className="text-right tabular-nums">{formatCurrency(h.opening_balance)}</td>
                    <td className="text-right tabular-nums">{h.closing_balance != null ? formatCurrency(h.closing_balance) : '—'}</td>
                    <td>
                      <span className={`dax-badge ${h.status === 'OPEN' ? 'dax-badge-green' : 'dax-badge-blue'}`}>
                        {h.status === 'OPEN' ? 'Abierto' : 'Cerrado'}
                      </span>
                    </td>
                    <td>
                      <div className="flex gap-1">
                        <button
                          onClick={() => downloadPdf(h.id)}
                          className="text-slate-500 hover:text-indigo-400 transition-colors"
                          title="Descargar PDF"
                        >
                          <i className="fa-solid fa-file-pdf" />
                        </button>
                        {printerName && (
                          <button
                            onClick={() => printCut(h.id)}
                            disabled={printingId === h.id}
                            className="text-slate-500 hover:text-white transition-colors disabled:opacity-40"
                            title="Reimprimir corte"
                          >
                            {printingId === h.id
                              ? <i className="fa-solid fa-spinner fa-spin" />
                              : <i className="fa-solid fa-print" />
                            }
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </DaxCard>
      )}

      {/* Modales */}
      {(modal === 'IN' || modal === 'OUT') && (
        <MovementModal type={modal} onClose={() => setModal(null)} onConfirm={handleMovement} />
      )}
      {modal === 'CLOSE' && summary && (
        <CloseModal summary={summary} onClose={() => setModal(null)} onConfirm={handleClose} />
      )}
    </div>
  )
}
