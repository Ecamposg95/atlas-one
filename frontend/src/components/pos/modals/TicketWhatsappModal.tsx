import { useEffect, useMemo, useState } from 'react'
import { Modal } from '../../ui/Modal'
import { salesApi } from '../../../api/sales'
import { useAuthStore } from '../../../store/authStore'
import type { SalesDocument } from '../../../types/sales'
import { saleLabel } from '../../../types/sales'
import { enlaceWhatsapp, textoTicketWhatsapp } from '../../../utils/ticketWhatsapp'

interface Props {
  /** Venta a enviar: el id basta (se lee del API); si ya se tiene completa, se usa tal cual. */
  saleId: string | null
  venta?: SalesDocument | null
  onClose: () => void
}

/**
 * Enviar ticket por WhatsApp: muestra el texto que se va a mandar y abre
 * `wa.me`. El número es opcional (sin él WhatsApp pide elegir el chat).
 */
export function TicketWhatsappModal({ saleId, venta: dada, onClose }: Props) {
  const negocio = useAuthStore((s) => s.org?.name)
  const [venta, setVenta] = useState<SalesDocument | null>(dada?.lines?.length ? dada : null)
  const [error, setError] = useState<string | null>(null)
  const [telefono, setTelefono] = useState('')

  useEffect(() => {
    setTelefono('')
    setError(null)
    if (!saleId) { setVenta(null); return }
    if (dada?.id === saleId && dada.lines?.length) { setVenta(dada); return }
    setVenta(null)
    let vivo = true
    salesApi.getById(saleId)
      .then((v) => { if (vivo) setVenta(v) })
      .catch(() => { if (vivo) setError('No se pudo leer la venta') })
    return () => { vivo = false }
  }, [saleId, dada])

  const texto = useMemo(() => (venta ? textoTicketWhatsapp(venta, negocio) : ''), [venta, negocio])
  const enlace = enlaceWhatsapp(texto, telefono)
  const numeroMalo = !enlace.ok && telefono.trim().length > 0

  return (
    <Modal
      open={saleId !== null}
      onClose={onClose}
      size="sm"
      title={<span><i className="fa-brands fa-whatsapp mr-2 text-dax-success" aria-hidden="true" />Ticket {venta ? saleLabel(venta) : ''}</span>}
      footer={
        <>
          <button type="button" onClick={onClose} className="dax-btn-secondary flex-1 justify-center">Cerrar</button>
          {enlace.ok && venta ? (
            <a href={enlace.url} target="_blank" rel="noopener noreferrer" onClick={() => onClose()}
               className="dax-btn-primary flex-1 justify-center" aria-label="Enviar por WhatsApp">
              <i className="fa-brands fa-whatsapp" aria-hidden="true" /> Enviar
            </a>
          ) : (
            <button type="button" disabled className="dax-btn-primary flex-1 justify-center disabled:opacity-40">
              <i className="fa-brands fa-whatsapp" aria-hidden="true" /> Enviar
            </button>
          )}
        </>
      }
    >
      <label className="block text-xs font-semibold text-dax-muted mb-1" htmlFor="wa-telefono">
        WhatsApp de la clienta (opcional)
      </label>
      <input
        id="wa-telefono"
        type="tel"
        inputMode="numeric"
        autoComplete="off"
        placeholder="10 dígitos"
        value={telefono}
        onChange={(e) => setTelefono(e.target.value)}
        className="dax-input w-full"
        aria-invalid={numeroMalo}
      />
      <p className={`text-xs mt-1 ${numeroMalo ? 'text-dax-danger' : 'text-dax-muted'}`}>
        {numeroMalo && !enlace.ok ? enlace.error : 'Sin número, WhatsApp te deja elegir el chat.'}
      </p>
      <div className="mt-3 rounded-xl p-3 text-xs font-mono whitespace-pre-wrap max-h-64 overflow-y-auto bg-dax-elevated text-dax-text">
        {error ?? (venta ? texto : 'Cargando ticket…')}
      </div>
    </Modal>
  )
}
