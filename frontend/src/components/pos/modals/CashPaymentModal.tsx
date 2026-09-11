import { useState } from 'react'
import { formatCurrency } from '../../../utils/currency'
import { cashPaymentValidity, OVERPAY_FACTOR } from '../../../pages/pos/cashPayment'

const QUICK = [50, 100, 200, 500, 1000]
const BILLS = [1000, 500, 200, 100, 50, 20]
const COINS = [10, 5, 2, 1]

interface Props {
  total: number
  onClose: () => void
  onConfirm: (received: number, printTicket: boolean) => Promise<void>
}

export function CashPaymentModal({ total, onClose, onConfirm }: Props) {
  const [received, setReceived] = useState('')
  const [printTicket, setPrintTicket] = useState(true)
  const [loading, setLoading] = useState(false)

  const receivedNum = parseFloat(received) || 0
  const change = receivedNum - total
  // Espejo del guard del backend (sales.py): falta de pago o sobrepago >10x
  // son 422. Vale más avisarlo aquí que dejar que el cobro falle al final.
  const validity = cashPaymentValidity(receivedNum, total)
  const isValid = validity.ok

  const addDenomination = (d: number) => {
    setReceived((prev) => String((parseFloat(prev) || 0) + d))
  }

  const submit = async () => {
    if (!isValid) return
    setLoading(true)
    try { await onConfirm(receivedNum, printTicket) } finally { setLoading(false) }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 backdrop-blur-sm"
      style={{ background: 'var(--dax-modal-backdrop)' }}
      onClick={onClose}
    >
      <div className="dax-card p-6 w-full max-w-[560px]" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-baseline justify-between mb-1">
          <h3 className="text-xl font-black" style={{ color: 'var(--dax-text)' }}>Pago en Efectivo</h3>
          <span className="text-xs font-bold uppercase tracking-wider" style={{ color: 'var(--dax-text-faint)' }}>Cobro</span>
        </div>

        {/* Total destacado */}
        <div className="rounded-xl p-3 mb-3 text-center" style={{ background: 'var(--dax-elevated)', border: '1px solid var(--dax-border-dim)' }}>
          <p className="text-[10px] font-bold uppercase tracking-wider mb-0.5" style={{ color: 'var(--dax-text-faint)' }}>Total a cobrar</p>
          <p className="text-3xl font-black text-emerald-700 tabular-nums">{formatCurrency(total)}</p>
        </div>

        {/* Monto recibido */}
        <div className="mb-3">
          <div className="flex items-center justify-between mb-1">
            <label className="block text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--dax-text-muted)' }}>
              Monto recibido
            </label>
            <button
              onClick={() => setReceived('')}
              className="text-[10px] font-bold text-red-500 hover:text-red-600 uppercase transition"
            >
              Limpiar
            </button>
          </div>
          <input
            type="number"
            value={received}
            onChange={(e) => setReceived(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && isValid && !loading) submit() }}
            className="dax-input text-4xl font-black text-center tabular-nums py-3"
            min={0}
            step="0.50"
            autoFocus
          />
          {validity.overpay && (
            <p className="mt-1.5 text-sm font-semibold" style={{ color: 'var(--p-danger)' }} role="alert">
              Monto muy alto: son más de {OVERPAY_FACTOR} veces el total. Revisa lo recibido.
            </p>
          )}
        </div>

        {/* Cambio */}
        <div className={`rounded-xl p-4 mb-4 text-center border-2 ${
          change >= 0 ? 'bg-emerald-600/10 border-emerald-600/40' : 'bg-red-600/10 border-red-600/40'
        }`}>
          <p className="text-[10px] font-bold uppercase tracking-wider mb-0.5" style={{ color: 'var(--dax-text-muted)' }}>
            {change >= 0 ? 'Cambio a devolver' : 'Faltante'}
          </p>
          <p className={`text-4xl font-black tabular-nums ${change >= 0 ? 'text-emerald-700' : 'text-red-600'}`}>
            {formatCurrency(Math.abs(change))}
          </p>
        </div>

        {/* Pago rápido — denominaciones grandes */}
        <div className="mb-3">
          <p className="text-[10px] font-bold uppercase tracking-wider mb-2" style={{ color: 'var(--dax-text-muted)' }}>Pago rápido</p>
          <div className="grid grid-cols-5 gap-1.5">
            {QUICK.map((d) => (
              <button
                key={d}
                onClick={() => addDenomination(d)}
                className="py-3 rounded-xl text-sm font-black border-2 transition-colors active:scale-95 hover:bg-emerald-50"
                style={{ borderColor: 'var(--dax-border)', color: 'var(--dax-text)' }}
              >
                ${d}
              </button>
            ))}
          </div>
        </div>

        {/* Billetes */}
        <div className="mb-1">
          <p className="text-[10px] font-bold uppercase tracking-wider mb-2" style={{ color: 'var(--dax-text-faint)' }}>Billetes</p>
          <div className="grid grid-cols-6 gap-1.5 mb-2">
            {BILLS.map((d) => (
              <button
                key={d}
                onClick={() => addDenomination(d)}
                className="py-2 rounded-lg text-xs font-bold border transition-colors active:scale-95"
                style={{ borderColor: 'var(--dax-border-dim)', color: 'var(--dax-text-muted)' }}
              >
                ${d}
              </button>
            ))}
          </div>
        </div>

        {/* Monedas */}
        <div className="mb-3">
          <p className="text-[10px] font-bold uppercase tracking-wider mb-2" style={{ color: 'var(--dax-text-faint)' }}>Monedas</p>
          <div className="grid grid-cols-4 gap-1.5">
            {COINS.map((d) => (
              <button
                key={d}
                onClick={() => addDenomination(d)}
                className="py-2 rounded-lg text-[11px] font-bold border transition-colors active:scale-95"
                style={{ borderColor: 'var(--dax-border-dim)', color: 'var(--dax-text-muted)' }}
              >
                ${d}
              </button>
            ))}
          </div>
        </div>

        {/* Cantidad exacta */}
        <button
          onClick={() => setReceived(String(total))}
          className="w-full py-2 border border-emerald-500/40 text-emerald-700 hover:bg-emerald-600/10 font-semibold rounded-xl text-xs uppercase tracking-widest transition mb-4"
        >
          <i className="fa-solid fa-check-circle mr-2" />Cantidad Exacta
        </button>

        {/* Print toggle */}
        <label className="flex items-center gap-3 cursor-pointer mb-4">
          <input
            type="checkbox"
            checked={printTicket}
            onChange={(e) => setPrintTicket(e.target.checked)}
            className="sr-only"
          />
          <div className={`w-10 h-5 rounded-full transition-colors relative flex-shrink-0 ${printTicket ? 'bg-emerald-600' : 'bg-slate-300'}`}>
            <div className={`absolute top-1 w-3 h-3 bg-white rounded-full transition-all ${printTicket ? 'left-6' : 'left-1'}`} />
          </div>
          <span className="text-xs font-semibold" style={{ color: 'var(--dax-text-muted)' }}>Imprimir Ticket</span>
        </label>

        <div className="flex gap-2">
          <button onClick={onClose} className="dax-btn-secondary flex-1 min-h-[52px]">Cancelar</button>
          <button
            onClick={submit}
            disabled={loading || !isValid}
            className="dax-btn-primary flex-1 justify-center disabled:opacity-50 min-h-[52px] text-base font-black"
          >
            {loading ? <i className="fa-solid fa-spinner fa-spin" /> : <><i className="fa-solid fa-check" /> Cobrar</>}
          </button>
        </div>
      </div>
    </div>
  )
}
