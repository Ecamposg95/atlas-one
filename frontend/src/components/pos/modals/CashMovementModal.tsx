import { useState } from 'react'
import { cashApi } from '../../../api/cash'
import { formatCurrency } from '../../../utils/currency'

const QUICK = [50, 100, 200, 500, 1000]

// El backend (app/routers/cash.py, MIN_REASON_LENGTH) exige un motivo de al
// menos 10 caracteres tanto para /inflow como para /outflow. Antes esta
// validación pedía "más de 0 caracteres", así que el 422 del backend era la
// primera vez que el cajero se enteraba del requisito real.
const MIN_REASON_LENGTH = 10

interface Props {
  type: 'IN' | 'OUT'
  onClose: () => void
  onSuccess: (msg: string) => void
}

export function CashMovementModal({ type, onClose, onSuccess }: Props) {
  const [amount, setAmount] = useState('')
  const [concept, setConcept] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const isIn = type === 'IN'
  const amtNum = parseFloat(amount) || 0
  const conceptLen = concept.trim().length
  const isValid = amtNum > 0 && conceptLen >= MIN_REASON_LENGTH

  const submit = async () => {
    if (!isValid) return
    setLoading(true)
    setError(null)
    try {
      if (isIn) await cashApi.inflow(amtNum, concept.trim())
      else await cashApi.outflow(amtNum, concept.trim())
      onSuccess(`${isIn ? 'Entrada' : 'Salida'} de ${formatCurrency(amtNum)} registrada`)
      onClose()
    } catch (e: unknown) {
      // El backend distingue 422 (motivo insuficiente), 409 (saldo
      // insuficiente para la salida) y 403 (monto alto sin rol autorizado).
      // Antes los tres se mostraban igual, como "Error al registrar
      // movimiento" — propagamos el `detail` real para que el cajero sepa
      // qué corregir.
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(detail ?? 'Error al registrar movimiento')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 backdrop-blur-sm"
      style={{ background: 'var(--dax-modal-backdrop)' }}
      onClick={onClose}
    >
      <div className="dax-card dax-modal p-6 pb-0 w-full max-w-sm" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-3 mb-4">
          <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${
            isIn ? 'bg-emerald-600/20' : 'bg-red-600/20'
          }`}>
            <i className={`fa-solid ${isIn ? 'fa-plus' : 'fa-minus'} ${isIn ? 'text-emerald-400' : 'text-red-400'}`} />
          </div>
          <div>
            <h3 className="text-lg font-black text-white">{isIn ? 'Entrada de Efectivo' : 'Salida de Efectivo'}</h3>
            <p className="text-xs text-slate-500">{isIn ? 'Registrar ingreso a caja' : 'Registrar retiro de caja'}</p>
          </div>
        </div>

        <div className="space-y-3 mb-1">
          <div>
            <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1">Monto</label>
            <input
              type="number"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              className="dax-input text-2xl font-black text-center tabular-nums"
              placeholder="0.00"
              inputMode="decimal"
              min="0.01"
              step="0.01"
              autoFocus
            />
          </div>

          <div className="grid grid-cols-3 sm:grid-cols-5 gap-1.5">
            {QUICK.map((q) => (
              <button
                key={q}
                onClick={() => setAmount(String(q))}
                className={`py-3 min-h-[44px] rounded-lg text-xs font-semibold border transition-colors ${
                  amtNum === q
                    ? 'border-indigo-500 bg-indigo-600/20 text-white'
                    : 'border-slate-700/50 text-slate-400 hover:border-slate-600 hover:text-white'
                }`}
              >
                ${q}
              </button>
            ))}
          </div>

          <div>
            <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1 flex items-center justify-between">
              <span>Concepto <span className="text-red-400">*</span></span>
              <span className={conceptLen >= MIN_REASON_LENGTH ? 'text-slate-500' : 'text-amber-400'}>
                {conceptLen}/{MIN_REASON_LENGTH}
              </span>
            </label>
            <input
              type="text"
              value={concept}
              onChange={(e) => setConcept(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') submit() }}
              className="dax-input text-sm"
              placeholder={isIn ? 'Ej: Préstamo del dueño...' : 'Ej: Compra de materiales...'}
            />
            {conceptLen > 0 && conceptLen < MIN_REASON_LENGTH && (
              <p className="text-amber-400 text-[11px] mt-1">
                Describe el motivo con al menos {MIN_REASON_LENGTH} caracteres.
              </p>
            )}
          </div>
        </div>

        {error && <p className="text-red-400 text-xs mb-3 text-center">{error}</p>}

        <div className="dax-modal-footer flex gap-2 pb-6">
          <button onClick={onClose} className="dax-btn-secondary flex-1 min-h-[44px]">Cancelar</button>
          <button
            onClick={submit}
            disabled={loading || !isValid}
            className={`flex-1 justify-center font-bold py-2 min-h-[44px] px-4 rounded-xl text-white text-sm transition disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2 ${
              isIn
                ? 'bg-emerald-600 hover:bg-emerald-500'
                : 'bg-red-600 hover:bg-red-500'
            }`}
          >
            {loading
              ? <i className="fa-solid fa-spinner fa-spin" />
              : <><i className={`fa-solid ${isIn ? 'fa-arrow-down-to-line' : 'fa-arrow-up-from-line'}`} /> Registrar</>
            }
          </button>
        </div>
      </div>
    </div>
  )
}
