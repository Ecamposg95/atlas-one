import { useState } from 'react'
import { formatCurrency } from '../../../utils/currency'

interface Props {
  total: number
  onClose: () => void
  onConfirm: (reference: string) => Promise<void>
}

export function TransferPaymentModal({ total, onClose, onConfirm }: Props) {
  const [reference, setReference] = useState('')
  const [loading, setLoading] = useState(false)

  const submit = async () => {
    if (!reference.trim()) return
    setLoading(true)
    try { await onConfirm(reference) } finally { setLoading(false) }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 backdrop-blur-sm"
      style={{ background: 'var(--dax-modal-backdrop)' }}
      onClick={onClose}
    >
      <div className="dax-card dax-modal p-6 pb-0 w-full max-w-sm" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-3 mb-4">
          <i className="fa-solid fa-mobile-screen text-blue-400 text-xl" />
          <div>
            <h3 className="text-lg font-black text-white">Transferencia / SPEI</h3>
            <p className="text-slate-500 text-sm">{formatCurrency(total)}</p>
          </div>
        </div>

        <div className="bg-blue-600/10 border border-blue-600/20 rounded-xl p-4 mb-4 text-center">
          <i className="fa-solid fa-qrcode text-blue-400 text-3xl mb-2 block" />
          <p className="text-slate-300 text-sm font-semibold">Solicita al cliente el comprobante</p>
          <p className="text-slate-500 text-xs mt-1">Ingresa la referencia del comprobante</p>
        </div>

        <div className="mb-1">
          <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1">
            Referencia <span className="text-red-400">*</span>
          </label>
          <input
            type="text"
            value={reference}
            onChange={(e) => setReference(e.target.value)}
            className="dax-input"
            placeholder="Folio de transferencia o CLABE..."
            autoFocus
            onKeyDown={(e) => { if (e.key === 'Enter' && reference.trim()) submit() }}
          />
          {!reference.trim() && <p className="text-red-400 text-xs mt-1">Campo requerido</p>}
        </div>

        <div className="dax-modal-footer flex gap-2 pb-6">
          <button onClick={onClose} className="dax-btn-secondary flex-1 min-h-[44px]">Cancelar</button>
          <button onClick={submit} disabled={loading || !reference.trim()} className="dax-btn-primary flex-1 justify-center disabled:opacity-50 min-h-[44px]">
            {loading ? <i className="fa-solid fa-spinner fa-spin" /> : <><i className="fa-solid fa-check" /> Confirmar</>}
          </button>
        </div>
      </div>
    </div>
  )
}
