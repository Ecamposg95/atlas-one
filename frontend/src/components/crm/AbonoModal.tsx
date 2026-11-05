import { useEffect, useRef, useState } from 'react'
import { customersApi, type AbonoResponse, type UnpaidDocument } from '../../api/customers'
import { Modal } from '../ui/Modal'
import { formatCurrency } from '../../utils/currency'

type Metodo = 'CASH' | 'CARD' | 'TRANSFER'

interface Props {
  customerId: number
  customerName: string
  onClose: () => void
  /** Recibe la respuesta del backend; el padre refresca saldo y listas. */
  onDone?: (r: AbonoResponse) => void
  /** Con ella aparece la casilla "Imprimir recibo" (marcada) y se llama tras abonar. */
  imprimir?: (paymentId: string) => Promise<void>
}

const apiErrorMessage = (err: unknown, fallback: string) => {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return typeof detail === 'string' && detail.trim() ? detail : fallback
}

/**
 * Registrar un abono a la cuenta de un cliente (spec 2026-10-29 §4.1). Lo
 * usan Clientes, Cuentas por cobrar y el POS. Sin ticket elegido el backend
 * cubre primero la deuda anterior y reparte del ticket más viejo al más
 * nuevo; lo que sobre queda a favor.
 */
export function AbonoModal({ customerId, customerName, onClose, onDone, imprimir }: Props) {
  const [monto, setMonto] = useState('')
  const [metodo, setMetodo] = useState<Metodo>('CASH')
  const [referencia, setReferencia] = useState('')
  const [ticket, setTicket] = useState('')
  const [tickets, setTickets] = useState<UnpaidDocument[]>([])
  const [imprimirRecibo, setImprimirRecibo] = useState(true)
  const [guardando, setGuardando] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // Id del pago ya registrado cuando falló la impresión: el formulario se retira para que no se pueda abonar dos veces.
  const [registrado, setRegistrado] = useState<string | null>(null)
  const montoRef = useRef<HTMLInputElement>(null)

  // El Modal del kit enfoca su primer control (cerrar) al montar; este efecto corre después y devuelve el foco al monto.
  useEffect(() => { montoRef.current?.focus() }, [])
  useEffect(() => {
    let vivo = true
    customersApi.getUnpaidDocuments(customerId).then((d) => { if (vivo) setTickets(d) }).catch(() => {})
    return () => { vivo = false }
  }, [customerId])

  const importe = parseFloat(monto)
  // Antes todo abono entraba como efectivo: una transferencia quedaba en el cajón y descuadraba el corte.
  const referenciaOk = metodo === 'CASH' || referencia.trim().length > 0
  const valido = Number.isFinite(importe) && importe > 0 && referenciaOk && !guardando

  const confirmar = async () => {
    if (!valido) return
    setGuardando(true)
    setError(null)
    let r: AbonoResponse
    try {
      r = await customersApi.pay(customerId, {
        amount: importe,
        method: metodo,
        // En efectivo no hay referencia: ignora lo que se escribió antes de cambiar de método.
        reference: metodo === 'CASH' ? undefined : referencia.trim() || undefined,
        sales_document_id: ticket || undefined,
      })
    } catch (err) {
      setError(apiErrorMessage(err, 'No se pudo registrar el abono'))
      setGuardando(false)
      return
    }
    // Desde aquí el abono ya existe: nada de lo que falle abajo puede reabrir el formulario.
    try {
      onDone?.(r)
    } catch {
      // El padre falló al refrescar; el abono sigue registrado y el modal se cierra igual.
    }
    if (imprimir && imprimirRecibo) {
      try {
        await imprimir(r.payment_id)
      } catch {
        setRegistrado(r.payment_id)
        setGuardando(false)
        return
      }
    }
    onClose()
  }

  const reintentarImpresion = async () => {
    if (!imprimir || !registrado || guardando) return
    setGuardando(true)
    try {
      await imprimir(registrado)
      onClose()
    } catch {
      setGuardando(false)
    }
  }

  // En vuelo no se cierra: la respuesta del abono se perdería y se podría reenviar.
  const cerrar = () => { if (!guardando) onClose() }

  const fecha = (iso: string) => new Date(iso).toLocaleDateString('es-MX')

  if (registrado) {
    return (
      <Modal open onClose={cerrar} size="sm" title="Registrar abono"
        closeOnBackdrop={!guardando} closeOnEscape={!guardando}
        footer={<>
          <button onClick={cerrar} disabled={guardando} className="dax-btn-secondary flex-1 disabled:opacity-40">Cerrar</button>
          <button onClick={reintentarImpresion} disabled={guardando} className="dax-btn-primary flex-1 justify-center disabled:opacity-40">
            {guardando ? <i className="fa-solid fa-spinner fa-spin" /> : <><i className="fa-solid fa-print" /> Reintentar impresión</>}
          </button>
        </>}>
        <p className="text-dax-muted text-sm mb-4">{customerName}</p>
        <p className="text-dax-danger text-xs" role="alert">El abono quedó registrado, pero el recibo no se imprimió</p>
      </Modal>
    )
  }

  return (
    <Modal open onClose={cerrar} size="sm" title="Registrar abono"
      closeOnBackdrop={!guardando} closeOnEscape={!guardando}
      footer={<>
        <button onClick={cerrar} disabled={guardando} className="dax-btn-secondary flex-1 disabled:opacity-40">Cancelar</button>
        <button onClick={confirmar} disabled={!valido} className="dax-btn-primary flex-1 justify-center disabled:opacity-40">
          {guardando ? <i className="fa-solid fa-spinner fa-spin" /> : <><i className="fa-solid fa-check" /> Confirmar</>}
        </button>
      </>}>
      <p className="text-dax-muted text-sm mb-4">{customerName}</p>
      <div className="space-y-3">
        <div>
          <label htmlFor="abono-monto" className="text-[10px] font-bold text-dax-muted uppercase tracking-wider block mb-1">Monto</label>
          <input id="abono-monto" type="number" step="0.01" min="0" value={monto} onChange={(e) => setMonto(e.target.value)}
            placeholder="0.00" className="dax-input w-full text-lg font-bold" ref={montoRef} />
        </div>
        <div>
          <label htmlFor="abono-metodo" className="text-[10px] font-bold text-dax-muted uppercase tracking-wider block mb-1">Método</label>
          <select id="abono-metodo" value={metodo} onChange={(e) => setMetodo(e.target.value as Metodo)} className="dax-input w-full text-sm">
            <option value="CASH">Efectivo</option>
            <option value="CARD">Tarjeta</option>
            <option value="TRANSFER">Transferencia</option>
          </select>
        </div>
        {metodo !== 'CASH' && (
          <div>
            <label htmlFor="abono-referencia" className="text-[10px] font-bold text-dax-muted uppercase tracking-wider block mb-1">Referencia (obligatoria)</label>
            <input id="abono-referencia" type="text" value={referencia} onChange={(e) => setReferencia(e.target.value)}
              placeholder={metodo === 'TRANSFER' ? 'Folio de la transferencia' : 'Últimos dígitos / autorización'} className="dax-input w-full text-sm" />
          </div>
        )}
        {tickets.length > 0 && (
          <div>
            <label htmlFor="abono-ticket" className="text-[10px] font-bold text-dax-muted uppercase tracking-wider block mb-1">Aplicar a ticket</label>
            <select id="abono-ticket" value={ticket} onChange={(e) => setTicket(e.target.value)} className="dax-input w-full text-sm">
              <option value="">Del más viejo al más nuevo</option>
              {tickets.map((t) => (
                <option key={t.id} value={t.id}>{t.folio} · {fecha(t.created_at)} · debe {formatCurrency(t.balance)}</option>
              ))}
            </select>
          </div>
        )}
        {imprimir && (
          <label className="flex items-center gap-2 text-sm text-dax-text min-h-[44px]">
            <input type="checkbox" checked={imprimirRecibo} onChange={(e) => setImprimirRecibo(e.target.checked)} />
            Imprimir recibo
          </label>
        )}
        <p className="text-xs text-dax-muted">Sin ticket elegido, el abono cubre primero la deuda anterior y luego del ticket más viejo al más nuevo; lo que sobre queda a favor.</p>
        {error && <p className="text-dax-danger text-xs" role="alert">{error}</p>}
      </div>
    </Modal>
  )
}
