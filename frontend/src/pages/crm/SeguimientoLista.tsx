import { useState } from 'react'
import { customersApi, TIPOS_SEGUIMIENTO, type Seguimiento, type TipoSeguimiento } from '../../api/customers'
import { toast } from '../../store/toastStore'
import { apiErrorMessage, estadoDeFecha, fechaCorta, hoyIso } from './crmUtil'

const ICONO = Object.fromEntries(TIPOS_SEGUIMIENTO.map((t) => [t.clave, t])) as Record<TipoSeguimiento, (typeof TIPOS_SEGUIMIENTO)[number]>

interface Props {
  items: Seguimiento[]
  /** Con cliente fijo se ofrece el alta de una tarea nueva para él. */
  customerId?: number
  /** En la lista general cada renglón dice de qué cliente es. */
  conCliente?: boolean
  onCambio: () => void
}

/** Tareas con clientes: qué hay que hacer, cuándo, y el botón para marcarla hecha. */
export function SeguimientoLista({ items, customerId, conCliente = false, onCambio }: Props) {
  const [tipo, setTipo] = useState<TipoSeguimiento>('LLAMADA')
  const [nota, setNota] = useState('')
  const [fecha, setFecha] = useState(hoyIso())
  const [guardando, setGuardando] = useState(false)
  const [cerrando, setCerrando] = useState<number | null>(null)

  const crear = async () => {
    if (!customerId || guardando) return
    setGuardando(true)
    try {
      await customersApi.crearSeguimiento({ customer_id: customerId, tipo, nota: nota.trim() || undefined, due_date: fecha })
      setNota('')
      onCambio()
    } catch (e) {
      toast.error(apiErrorMessage(e, 'No se pudo guardar el seguimiento'))
    } finally { setGuardando(false) }
  }

  const cerrar = async (s: Seguimiento) => {
    setCerrando(s.id)
    try {
      await customersApi.cerrarSeguimiento(s.id)
      onCambio()
    } catch (e) {
      toast.error(apiErrorMessage(e, 'No se pudo marcar como hecho'))
    } finally { setCerrando(null) }
  }

  return (
    <div className="space-y-2">
      {customerId != null && (
        <div className="grid grid-cols-1 sm:grid-cols-[auto_1fr_auto_auto] gap-2">
          <select aria-label="Tipo de seguimiento" value={tipo} onChange={(e) => setTipo(e.target.value as TipoSeguimiento)} className="dax-input text-sm">
            {TIPOS_SEGUIMIENTO.map((t) => <option key={t.clave} value={t.clave}>{t.label}</option>)}
          </select>
          <input aria-label="Nota del seguimiento" value={nota} onChange={(e) => setNota(e.target.value)} maxLength={300}
            placeholder="Ej. avisar que llegó su talla" className="dax-input text-sm" />
          <input aria-label="Fecha del seguimiento" type="date" value={fecha} min={hoyIso()} onChange={(e) => setFecha(e.target.value)} className="dax-input text-sm" />
          <button type="button" onClick={crear} disabled={guardando || !fecha} className="dax-btn-secondary text-sm justify-center disabled:opacity-50">
            <i className="fa-solid fa-plus" aria-hidden="true" /> Agendar
          </button>
        </div>
      )}
      {items.length === 0 ? (
        <p className="text-sm text-dax-muted">Sin seguimientos.</p>
      ) : (
        <ul className="space-y-1.5">
          {items.map((s) => {
            const estado = s.status === 'HECHO' ? 'hecho' : estadoDeFecha(s.due_date)
            return (
              <li key={s.id} className="flex items-start gap-2 rounded-lg p-2 bg-dax-elevated border border-dax-border-dim text-sm">
                <i className={`fa-solid ${ICONO[s.tipo]?.icon ?? 'fa-thumbtack'} mt-1 text-dax-muted`} aria-hidden="true" />
                <div className="flex-1 min-w-0">
                  <p className={`text-dax-text ${s.status === 'HECHO' ? 'line-through opacity-60' : ''}`}>
                    {conCliente && <span className="font-semibold">{s.customer_name ?? 'Cliente'} · </span>}
                    {ICONO[s.tipo]?.label ?? s.tipo}{s.nota ? `: ${s.nota}` : ''}
                  </p>
                  <p className={`text-xs ${estado === 'vencido' ? 'text-dax-danger' : estado === 'hoy' ? 'text-dax-warning' : 'text-dax-muted'}`}>
                    {estado === 'hecho' ? `Hecho${s.resultado ? ` — ${s.resultado}` : ''}`
                      : estado === 'vencido' ? `Vencido · ${fechaCorta(s.due_date)}`
                      : estado === 'hoy' ? 'Para hoy' : fechaCorta(s.due_date)}
                    {s.assigned_name ? ` · ${s.assigned_name}` : ''}
                    {conCliente && s.customer_phone ? ` · ${s.customer_phone}` : ''}
                  </p>
                </div>
                {s.status !== 'HECHO' && (
                  <button type="button" onClick={() => cerrar(s)} disabled={cerrando === s.id}
                    className="dax-btn-secondary text-xs disabled:opacity-50" aria-label={`Marcar hecho: ${s.nota ?? s.tipo}`}>
                    <i className="fa-solid fa-check" aria-hidden="true" /> Hecho
                  </button>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
