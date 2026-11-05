import { useEffect, useRef, useState } from 'react'
import { customersApi, type DeudaAnteriorResponse } from '../../api/customers'
import { Modal } from '../ui/Modal'

interface Props {
  customerId: number
  customerName: string
  onClose: () => void
  onDone?: (r: DeudaAnteriorResponse) => void
}

const apiErrorMessage = (err: unknown, fallback: string) => {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return typeof detail === 'string' && detail.trim() ? detail : fallback
}

/** Hoy en México como YYYY-MM-DD (el valor de un <input type="date">). */
export const hoyMx = () => new Date().toLocaleDateString('en-CA', { timeZone: 'America/Mexico_City' })

/**
 * Cargar lo que una clienta ya debía antes del sistema (la libreta). Lo usa
 * el dueño desde Clientes. No es venta ni toca caja: sube el saldo con la
 * fecha real de la deuda, y los abonos la cubren antes que los tickets.
 */
export function DeudaAnteriorModal({ customerId, customerName, onClose, onDone }: Props) {
  const [monto, setMonto] = useState('')
  const [fecha, setFecha] = useState(hoyMx)
  const [nota, setNota] = useState('')
  const [guardando, setGuardando] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const montoRef = useRef<HTMLInputElement>(null)

  useEffect(() => { montoRef.current?.focus() }, [])

  const importe = parseFloat(monto)
  const valido = Number.isFinite(importe) && importe > 0 && !!fecha && fecha <= hoyMx() && !guardando

  const guardar = async () => {
    if (!valido) return
    setGuardando(true)
    setError(null)
    try {
      const r = await customersApi.cargarDeudaAnterior(customerId, { amount: importe, fecha, nota: nota.trim() || undefined })
      onDone?.(r)
      onClose()
    } catch (err) {
      setError(apiErrorMessage(err, 'No se pudo cargar la deuda'))
      setGuardando(false)
    }
  }

  const cerrar = () => { if (!guardando) onClose() }

  return (
    <Modal open onClose={cerrar} size="sm" title="Deuda anterior"
      closeOnBackdrop={!guardando} closeOnEscape={!guardando}
      footer={<>
        <button onClick={cerrar} disabled={guardando} className="dax-btn-secondary flex-1 disabled:opacity-40">Cancelar</button>
        <button onClick={guardar} disabled={!valido} className="dax-btn-primary flex-1 justify-center disabled:opacity-40">
          {guardando ? <i className="fa-solid fa-spinner fa-spin" /> : <><i className="fa-solid fa-check" /> Guardar</>}
        </button>
      </>}>
      <p className="text-dax-muted text-sm mb-4">{customerName}</p>
      <div className="space-y-3">
        <div>
          <label htmlFor="deuda-monto" className="text-[10px] font-bold text-dax-muted uppercase tracking-wider block mb-1">Cuánto debe</label>
          <input id="deuda-monto" type="number" step="0.01" min="0" inputMode="decimal" value={monto} onChange={(e) => setMonto(e.target.value)}
            placeholder="0.00" className="dax-input w-full text-lg font-bold" ref={montoRef} />
        </div>
        <div>
          <label htmlFor="deuda-fecha" className="text-[10px] font-bold text-dax-muted uppercase tracking-wider block mb-1">Desde cuándo</label>
          <input id="deuda-fecha" type="date" value={fecha} max={hoyMx()} onChange={(e) => setFecha(e.target.value)} className="dax-input w-full text-sm" />
        </div>
        <div>
          <label htmlFor="deuda-nota" className="text-[10px] font-bold text-dax-muted uppercase tracking-wider block mb-1">Nota (opcional)</label>
          <input id="deuda-nota" type="text" maxLength={200} value={nota} onChange={(e) => setNota(e.target.value)}
            placeholder="Libreta: vestido Zara" className="dax-input w-full text-sm" />
        </div>
        <p className="text-xs text-dax-muted">No cuenta como venta ni toca la caja ni el inventario. Los abonos la cubren antes que los tickets.</p>
        {error && <p className="text-dax-danger text-xs" role="alert">{error}</p>}
      </div>
    </Modal>
  )
}
