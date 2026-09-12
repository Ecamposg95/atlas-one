import { useState } from 'react'

interface Props {
  /** Folio o identificador legible del ticket, para que se vea cuál se autoriza. */
  etiqueta?: string
  onCancel: () => void
  /** Devuelve el mensaje de error si el PIN no sirvió, o null si ya imprimió. */
  onSubmit: (pin: string) => Promise<string | null>
}

/**
 * Pide el PIN de un supervisor para reimprimir un ticket.
 *
 * El backend (app/services/reprint_auth.py) exige rol gerencial o el PIN de un
 * supervisor de la organización: sin esto, un cajero reimprime un ticket y lo
 * entrega como comprobante de una venta que no ocurrió. El PIN es la
 * contraseña del supervisor, así que el campo va como `password` y nunca se
 * guarda ni se reenvía.
 */
export function ReprintPinModal({ etiqueta, onCancel, onSubmit }: Props) {
  const [pin, setPin] = useState('')
  const [enviando, setEnviando] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const enviar = async () => {
    if (!pin.trim() || enviando) return
    setEnviando(true)
    setError(null)
    const mensaje = await onSubmit(pin)
    setEnviando(false)
    if (mensaje) {
      setError(mensaje)
      setPin('')
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 backdrop-blur-sm"
      style={{ background: 'var(--dax-modal-backdrop)' }}
      onClick={onCancel}
    >
      <div className="dax-card p-6 w-full max-w-sm" onClick={(e) => e.stopPropagation()}>
        <h3 className="text-lg font-black mb-1" style={{ color: 'var(--dax-text)' }}>
          Autorización para reimprimir
        </h3>
        <p className="text-xs mb-4" style={{ color: 'var(--dax-text-muted)' }}>
          {etiqueta
            ? `Un supervisor debe autorizar la reimpresión de ${etiqueta}.`
            : 'Un supervisor debe autorizar esta reimpresión.'}
        </p>

        <label
          htmlFor="reprint-pin"
          className="block text-[10px] font-bold uppercase tracking-wider mb-1"
          style={{ color: 'var(--dax-text-muted)' }}
        >
          PIN del supervisor
        </label>
        <input
          id="reprint-pin"
          type="password"
          autoComplete="off"
          value={pin}
          onChange={(e) => setPin(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') enviar() }}
          className="dax-input text-center tracking-widest"
          placeholder="••••••"
          autoFocus
        />

        {error && (
          <p className="text-red-400 text-xs mt-2 text-center">{error}</p>
        )}

        <div className="flex gap-2 mt-4">
          <button onClick={onCancel} className="dax-btn-secondary flex-1" disabled={enviando}>
            Cancelar
          </button>
          <button
            onClick={enviar}
            disabled={enviando || !pin.trim()}
            className="dax-btn-primary flex-1 justify-center"
          >
            {enviando ? <i className="fa-solid fa-spinner fa-spin" /> : 'Autorizar'}
          </button>
        </div>
      </div>
    </div>
  )
}
