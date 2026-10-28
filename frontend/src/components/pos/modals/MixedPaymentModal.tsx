import { useState } from 'react'
import { formatCurrency } from '../../../utils/currency'
import { formatPct, mixedSurcharge } from '../../../pages/pos/cardSurcharge'

type Method = 'CASH' | 'CARD' | 'TRANSFER'

interface PaymentLine {
  method: Method
  amount: string
  reference: string
}

const METHOD_LABELS: Record<Method, { label: string; icon: string; color: string }> = {
  CASH: { label: 'Efectivo', icon: 'fa-money-bill', color: 'text-emerald-400' },
  CARD: { label: 'Tarjeta', icon: 'fa-credit-card', color: 'text-indigo-400' },
  TRANSFER: { label: 'Transferencia', icon: 'fa-mobile-screen', color: 'text-blue-400' },
}

interface Props {
  total: number
  /** Comisión por pago con tarjeta de la organización. 0 = apagada. */
  surchargePct?: number
  /**
   * Cliente del CRM en el carrito. Con uno, lo que no se cobre queda a su
   * cuenta (fiado): el backend asienta el saldo y la venta nace PENDING. Un
   * nombre libre sin ficha no puede fiar: no hay cuenta a la cual cargarle.
   */
  customerId?: number | null
  customerName?: string | null
  onClose: () => void
  onConfirm: (payments: { method: string; amount: number; reference?: string }[]) => Promise<void>
}

export function MixedPaymentModal({ total, surchargePct = 0, customerId = null, customerName = null, onClose, onConfirm }: Props) {
  const [lines, setLines] = useState<PaymentLine[]>([
    { method: 'CASH', amount: String(total.toFixed(2)), reference: '' },
  ])
  const [loading, setLoading] = useState(false)

  const paid = lines.reduce((s, l) => s + (parseFloat(l.amount) || 0), 0)
  // La comisión se calcula sobre lo que NO se paga con tarjeta, en vivo: si el
  // cajero mueve el renglón de efectivo, el total a pagar se mueve con él.
  // `cargo` es lo que el backend va a cobrar de verdad (CERO mientras no haya
  // un renglón de tarjeta); `proyectado` es lo que costaría completar el
  // faltante con tarjeta, y es lo que anuncia el botón de abajo.
  const { charged: cargo, projected: proyectado } = mixedSurcharge(total, lines, surchargePct)
  // Neutralidad: con la comisión apagada, `totalDue` es el `total` tal cual y
  // el modal se comporta exactamente como antes.
  const totalDue = cargo.amount > 0 ? cargo.totalDue : total
  const remaining = totalDue - paid
  const change = paid - totalDue

  const addLine = () => setLines((l) => [...l, { method: 'CASH', amount: '', reference: '' }])
  const removeLine = (i: number) => setLines((l) => l.filter((_, idx) => idx !== i))
  const updateLine = (i: number, patch: Partial<PaymentLine>) =>
    setLines((l) => l.map((line, idx) => idx === i ? { ...line, ...patch } : line))

  const puedeFiar = customerId != null
  const fiado = puedeFiar && remaining > 0.005 ? remaining : 0
  // Sin cliente, cada renglón cobra algo y entre todos cubren el total. Con
  // cliente, un renglón vacío se ignora (dejar todo a crédito) y lo que falte
  // es el saldo fiado; nunca se manda un importe negativo.
  const renglonesValidos = puedeFiar
    ? lines.every((l) => l.amount === '' || (parseFloat(l.amount) || 0) >= 0)
    : lines.every((l) => parseFloat(l.amount) > 0)
  const isValid = renglonesValidos && (puedeFiar || remaining <= 0.005)

  const submit = async () => {
    if (!isValid) return
    setLoading(true)
    try {
      await onConfirm(
        lines
          .filter((l) => (parseFloat(l.amount) || 0) > 0)
          .map((l) => ({
            method: l.method,
            amount: parseFloat(l.amount),
            reference: l.reference || undefined,
          }))
      )
    } finally { setLoading(false) }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 backdrop-blur-sm"
      style={{ background: 'var(--dax-modal-backdrop)' }}
      onClick={onClose}
    >
      <div className="dax-card dax-modal p-6 pb-0 w-full max-w-md" onClick={(e) => e.stopPropagation()}>
        <h3 className="text-lg font-black text-white mb-1">Pago Mixto</h3>
        <p className="text-slate-500 text-sm mb-4">Total: <span className="text-white font-bold">{formatCurrency(total)}</span></p>
        {puedeFiar && (
          <p className="text-xs mb-3 text-slate-400">
            <i className="fa-solid fa-user mr-1" />
            Lo que no se cobre queda a la cuenta de <span className="font-semibold text-white">{customerName ?? 'la clienta'}</span>.
          </p>
        )}

        <div className="space-y-3 mb-4 max-h-[40dvh] overflow-y-auto pr-1">
          {lines.map((line, i) => (
            <div key={i} className="rounded-xl p-3" style={{ background: 'var(--dax-elevated)', border: '1px solid var(--dax-border-dim)' }}>
              <div className="flex items-center gap-2 mb-2">
                {/* Método */}
                <select
                  value={line.method}
                  onChange={(e) => updateLine(i, { method: e.target.value as Method })}
                  className="dax-input text-sm flex-1"
                >
                  {(Object.keys(METHOD_LABELS) as Method[]).map((m) => (
                    <option key={m} value={m}>{METHOD_LABELS[m].label}</option>
                  ))}
                </select>
                {lines.length > 1 && (
                  <button onClick={() => removeLine(i)} className="text-red-400 hover:text-red-300 text-sm p-1.5">
                    <i className="fa-solid fa-xmark" />
                  </button>
                )}
              </div>
              <div className="flex gap-2">
                <input
                  type="number"
                  value={line.amount}
                  onChange={(e) => updateLine(i, { amount: e.target.value })}
                  className="dax-input flex-1 text-sm tabular-nums"
                  placeholder="0.00"
                  inputMode="decimal"
                  min="0"
                  step="0.01"
                />
                {(line.method === 'CARD' || line.method === 'TRANSFER') && (
                  <input
                    type="text"
                    value={line.reference}
                    onChange={(e) => updateLine(i, { reference: e.target.value })}
                    className="dax-input flex-1 text-sm"
                    placeholder={line.method === 'TRANSFER' ? 'Referencia *' : 'Ref. (opcional)'}
                  />
                )}
              </div>
            </div>
          ))}
        </div>

        {proyectado.amount > 0 && (
          <button
            onClick={() => {
              const idx = lines.findIndex((l) => l.method === 'CARD')
              const monto = proyectado.cardDue.toFixed(2)
              if (idx === -1) setLines((l) => [...l, { method: 'CARD', amount: monto, reference: '' }])
              else updateLine(idx, { amount: monto })
            }}
            className="dax-btn-secondary text-xs w-full justify-center mb-2"
            title="Pone en el renglón de tarjeta lo que falta, con la comisión incluida"
          >
            <i className="fa-solid fa-credit-card" /> Completar con tarjeta ({formatCurrency(proyectado.cardDue)})
          </button>
        )}

        <div className="flex gap-2 mb-4">
          <button onClick={addLine} className="dax-btn-secondary text-xs flex-1 justify-center">
            <i className="fa-solid fa-plus" /> Agregar método
          </button>
          {puedeFiar && (
            <button
              onClick={() => setLines([{ method: 'CASH', amount: '', reference: '' }])}
              className="dax-btn-secondary text-xs flex-1 justify-center"
              title="No cobra nada hoy: el total completo queda a la cuenta del cliente"
            >
              <i className="fa-solid fa-hand-holding-dollar" /> Todo a crédito
            </button>
          )}
        </div>

        {/* Resumen */}
        <div className={`rounded-xl p-3 mb-1 text-sm space-y-1 ${remaining > 0.005 && !puedeFiar ? 'bg-red-600/10 border border-red-600/30' : fiado > 0 ? 'bg-amber-500/10 border border-amber-500/30' : 'bg-emerald-600/10 border border-emerald-600/30'}`}>
          <div className="flex justify-between text-slate-400">
            <span>{cargo.amount > 0 ? 'Mercancía' : 'Total'}</span><span>{formatCurrency(total)}</span>
          </div>
          {cargo.amount > 0 && (
            <>
              <div className="flex justify-between text-slate-400">
                <span>Comisión tarjeta {formatPct(cargo.pct)}%</span>
                <span>{formatCurrency(cargo.amount)}</span>
              </div>
              <div className="flex justify-between text-white font-semibold">
                <span>Total a pagar</span><span>{formatCurrency(totalDue)}</span>
              </div>
            </>
          )}
          <div className="flex justify-between text-slate-400">
            <span>Pagado</span><span>{formatCurrency(paid)}</span>
          </div>
          <div className={`flex justify-between font-bold pt-1 ${fiado > 0 ? 'text-amber-400' : remaining > 0.005 ? 'text-red-400' : 'text-emerald-400'}`} style={{ borderTop: '1px solid var(--dax-border-dim)' }}>
            <span>{fiado > 0 ? 'Queda a crédito' : remaining > 0.005 ? 'Pendiente' : change > 0.005 ? 'Cambio' : 'Exacto'}</span>
            <span>{formatCurrency(remaining > 0.005 ? remaining : change)}</span>
          </div>
        </div>

        {change > 0.005 && (
          <p className="text-xs text-center mb-3 text-slate-400">
            <i className="fa-solid fa-circle-info mr-1" />
            {lines.some((l) => l.method === 'CASH')
              ? 'El cambio se entrega del efectivo'
              : 'El cobro excede el total de la venta'}
          </p>
        )}

        <div className="dax-modal-footer flex gap-2 pb-6">
          <button onClick={onClose} className="dax-btn-secondary flex-1 min-h-[44px]">Cancelar</button>
          <button onClick={submit} disabled={loading || !isValid} className="dax-btn-primary flex-1 justify-center disabled:opacity-50 min-h-[44px]">
            {loading ? <i className="fa-solid fa-spinner fa-spin" /> : fiado > 0 ? <><i className="fa-solid fa-hand-holding-dollar" /> Cobrar y fiar</> : <><i className="fa-solid fa-check" /> Cobrar</>}
          </button>
        </div>
      </div>
    </div>
  )
}
