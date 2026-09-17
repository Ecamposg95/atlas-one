import { useState } from 'react'
import { formatCurrency } from '../../../utils/currency'
import { formatPct, surchargeFor } from '../../../pages/pos/cardSurcharge'

interface Props {
  total: number
  /** Comisión por pago con tarjeta de la organización. 0 = apagada. */
  surchargePct?: number
  onClose: () => void
  onConfirm: (reference: string) => Promise<void>
}

export function CardPaymentModal({ total, surchargePct = 0, onClose, onConfirm }: Props) {
  const [reference, setReference] = useState('')
  const [loading, setLoading] = useState(false)

  // 100 % tarjeta: no hay pagos de otro método, así que la comisión va sobre
  // el total completo. Con `surchargePct = 0` el desglose no se pinta y el
  // modal queda idéntico al de siempre.
  const cargo = surchargeFor(total, 0, surchargePct)

  const submit = async () => {
    setLoading(true)
    try { await onConfirm(reference) } finally { setLoading(false) }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 backdrop-blur-sm"
      style={{ background: 'var(--dax-modal-backdrop)' }}
      onClick={onClose}
    >
      <div className="dax-card p-6 w-full max-w-sm" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-3 mb-4">
          <i className="fa-solid fa-credit-card text-indigo-400 text-xl" />
          <div>
            <h3 className="text-lg font-black text-white">Pago con Tarjeta</h3>
            <p className="text-slate-500 text-sm">{formatCurrency(cargo.amount > 0 ? cargo.totalDue : total)}</p>
          </div>
        </div>

        <div className="rounded-xl p-4 mb-4 text-center" style={{ background: 'var(--dax-elevated)', border: '1px solid var(--dax-border-dim)' }}>
          <i className="fa-solid fa-contactless-pay text-indigo-400 text-3xl mb-2 block" />
          <p className="text-slate-400 text-sm">Pasa la tarjeta en la terminal</p>
        </div>

        {cargo.amount > 0 && (
          <div className="rounded-xl p-3 mb-4 text-sm space-y-1" style={{ background: 'var(--dax-elevated)', border: '1px solid var(--dax-border-dim)' }}>
            <div className="flex justify-between text-slate-400">
              <span>Mercancía</span><span className="tabular-nums">{formatCurrency(total)}</span>
            </div>
            <div className="flex justify-between text-slate-400">
              <span>Comisión tarjeta {formatPct(cargo.pct)}%</span>
              <span className="tabular-nums">{formatCurrency(cargo.amount)}</span>
            </div>
            <div className="flex justify-between font-bold text-white pt-1" style={{ borderTop: '1px solid var(--dax-border-dim)' }}>
              <span>Total a pagar</span><span className="tabular-nums">{formatCurrency(cargo.totalDue)}</span>
            </div>
          </div>
        )}

        <div className="mb-4">
          <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1">
            Referencia (opcional)
          </label>
          <input
            type="text"
            value={reference}
            onChange={(e) => setReference(e.target.value)}
            className="dax-input"
            placeholder="Últimos 4 dígitos o autorización..."
            autoFocus
            onKeyDown={(e) => { if (e.key === 'Enter') submit() }}
          />
        </div>

        <div className="flex gap-2">
          <button onClick={onClose} className="dax-btn-secondary flex-1">Cancelar</button>
          <button onClick={submit} disabled={loading} className="dax-btn-primary flex-1 justify-center">
            {loading ? <i className="fa-solid fa-spinner fa-spin" /> : <><i className="fa-solid fa-check" /> Confirmar</>}
          </button>
        </div>
      </div>
    </div>
  )
}
