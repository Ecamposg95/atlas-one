import { useCallback, useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'

import { aiApi, type MensajeAgente, type TablaAgente } from '../../api/ai'
import { useEsTelefono } from '../../hooks/useIsMobile'
import { useAgenteStore } from '../../store/agenteStore'
import { formatCurrency } from '../../utils/currency'
import { errorDetailText } from '../../utils/errorDetail'
import { Modal } from '../ui/Modal'
import { Spinner } from '../ui/Spinner'

/**
 * Panel del agente (fase A1: consultas). Texto simple y, cuando el servidor
 * las manda, tablas pequeñas con el resultado de cada consulta. El servidor
 * decide qué puede ver cada rol; aquí solo se pinta.
 *
 * Vive sobre `ui/Modal`: en teléfono es hoja inferior a todo lo ancho.
 */
type Burbuja = Pick<MensajeAgente, 'id' | 'rol' | 'contenido' | 'tablas'>

const TOPE_TEXTO = 4000
const DINERO = /precio|costo|importe|total|venta|ticket promedio/i

function estado(e: unknown): number | undefined {
  return (e as { response?: { status?: number } })?.response?.status
}

/** Texto para la persona según lo que respondió el servidor. */
export function mensajeDeError(e: unknown): string {
  const detalle = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  switch (estado(e)) {
    case 429:
      return errorDetailText(detalle, 'Se alcanzó el límite de uso del agente por hoy. Intenta mañana.')
    case 503:
      return errorDetailText(detalle, 'El agente no está disponible en este momento. Intenta de nuevo en un minuto.')
    case 403:
      return errorDetailText(detalle, 'Tu usuario no tiene acceso al agente.')
    case 422:
      return errorDetailText(detalle, 'Revisa tu pregunta e intenta de nuevo.')
    default:
      return 'No se pudo enviar tu pregunta. Revisa tu conexión e intenta de nuevo.'
  }
}

export function celda(valor: string | number | boolean | null, columna: string): string {
  if (valor === null || valor === '') return '—'
  if (typeof valor === 'boolean') return valor ? 'Sí' : 'No'
  if (typeof valor === 'number') {
    return DINERO.test(columna) ? formatCurrency(valor) : valor.toLocaleString('es-MX', { maximumFractionDigits: 2 })
  }
  return valor
}

function TablaRespuesta({ tabla, esTelefono }: { tabla: TablaAgente; esTelefono: boolean }) {
  return (
    <div className="mt-2 rounded-lg border border-dax-border-dim bg-dax-surface" data-testid="tabla-agente">
      <p className="px-3 pt-2 text-xs font-semibold text-dax-muted">{tabla.titulo}</p>
      {esTelefono ? (
        <ul className="divide-y divide-dax-border-dim">
          {tabla.filas.map((fila, i) => (
            <li key={i} className="px-3 py-2 text-xs">
              <p className="font-semibold text-dax-text">{celda(fila[0], tabla.columnas[0])}</p>
              <dl className="mt-1 space-y-0.5">
                {fila.slice(1).map((valor, j) => (
                  <div key={j} className="flex justify-between gap-2 min-w-0">
                    <dt className="text-dax-muted truncate">{tabla.columnas[j + 1]}</dt>
                    <dd className="text-dax-text text-right">{celda(valor, tabla.columnas[j + 1])}</dd>
                  </div>
                ))}
              </dl>
            </li>
          ))}
        </ul>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr>
                {tabla.columnas.map((c) => (
                  <th key={c} className="px-3 py-1.5 text-left font-medium text-dax-muted whitespace-nowrap">{c}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {tabla.filas.map((fila, i) => (
                <tr key={i} className="border-t border-dax-border-dim">
                  {fila.map((valor, j) => (
                    <td key={j} className="px-3 py-1.5 text-dax-text">{celda(valor, tabla.columnas[j])}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {tabla.mas > 0 && (
        <p className="px-3 py-1.5 text-xs text-dax-faint border-t border-dax-border-dim">
          y {tabla.mas} más. Afina la pregunta para verlos.
        </p>
      )}
    </div>
  )
}

export default function PanelAgente() {
  const cerrar = useAgenteStore((s) => s.cerrar)
  const borrador = useAgenteStore((s) => s.borrador)
  const conversacionId = useAgenteStore((s) => s.conversacionId)
  const fijarConversacion = useAgenteStore((s) => s.fijarConversacion)
  const esTelefono = useEsTelefono()

  const [burbujas, setBurbujas] = useState<Burbuja[]>([])
  const [texto, setTexto] = useState(borrador)
  const [enviando, setEnviando] = useState(false)
  const [cargando, setCargando] = useState(conversacionId !== null)
  const [error, setError] = useState<string | null>(null)
  const finRef = useRef<HTMLDivElement | null>(null)

  // Al abrir: retoma la conversación en curso. Si ya no existe (otra persona
  // en la misma caja, o se borró), empieza una nueva sin ruido.
  useEffect(() => {
    if (!conversacionId) return
    let vigente = true
    aiApi.leer(conversacionId)
      .then((d) => { if (vigente) setBurbujas(d.mensajes) })
      .catch(() => { if (vigente) fijarConversacion(null) })
      .finally(() => { if (vigente) setCargando(false) })
    return () => { vigente = false }
    // Solo al montar: después el panel lleva la cuenta él mismo.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => { finRef.current?.scrollIntoView?.({ block: 'end' }) }, [burbujas, enviando])

  const enviar = useCallback(async () => {
    const pregunta = texto.trim()
    if (!pregunta || enviando) return
    const provisional: Burbuja = { id: `local-${Date.now()}`, rol: 'user', contenido: pregunta, tablas: [] }
    setBurbujas((b) => [...b, provisional])
    setTexto('')
    setError(null)
    setEnviando(true)
    try {
      let id = useAgenteStore.getState().conversacionId
      if (!id) {
        id = (await aiApi.crear()).id
        fijarConversacion(id)
      }
      let respuesta: MensajeAgente
      try {
        respuesta = await aiApi.enviar(id, pregunta)
      } catch (e) {
        if (estado(e) !== 404) throw e
        // La conversación ya no es de esta sesión: se abre otra.
        id = (await aiApi.crear()).id
        fijarConversacion(id)
        setBurbujas([provisional])
        respuesta = await aiApi.enviar(id, pregunta)
      }
      setBurbujas((b) => [...b, respuesta])
    } catch (e) {
      // La pregunta vuelve a la caja para que no se pierda.
      setBurbujas((b) => b.filter((x) => x.id !== provisional.id))
      setTexto(pregunta)
      setError(mensajeDeError(e))
    } finally {
      setEnviando(false)
    }
  }, [texto, enviando, fijarConversacion])

  const nueva = () => {
    fijarConversacion(null)
    setBurbujas([])
    setError(null)
  }

  const alTeclear = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      void enviar()
    }
  }
  const alEnviar = (e: FormEvent) => {
    e.preventDefault()
    void enviar()
  }

  return (
    <Modal
      open
      onClose={cerrar}
      title="Agente"
      size="lg"
      closeOnBackdrop={false}
      footer={
        <form onSubmit={alEnviar} className="flex w-full items-end gap-2">
          <textarea
            value={texto}
            onChange={(e) => setTexto(e.target.value.slice(0, TOPE_TEXTO))}
            onKeyDown={alTeclear}
            rows={esTelefono ? 1 : 2}
            placeholder="Pregunta por un precio, una existencia o tus ventas"
            aria-label="Tu pregunta"
            className="dax-input flex-1 resize-none"
          />
          <button type="submit" className="dax-btn-primary" disabled={enviando || !texto.trim()}>
            Enviar
          </button>
        </form>
      }
    >
      <div className="flex flex-col gap-3 min-h-[40dvh]" aria-live="polite">
        {burbujas.length > 0 && (
          <div className="flex justify-end">
            <button type="button" className="dax-btn-ghost text-xs" onClick={nueva} disabled={enviando}>
              Nueva conversación
            </button>
          </div>
        )}
        {cargando && <div className="flex justify-center py-6"><Spinner /></div>}
        {!cargando && burbujas.length === 0 && (
          <p className="text-sm text-dax-muted">
            Pregunta lo que necesites saber de tu tienda: precios, existencias, ventas. El agente solo consulta,
            no cambia nada, y solo ve lo que tu usuario puede ver.
          </p>
        )}
        {burbujas.map((b) => (
          <div key={b.id} className={b.rol === 'user' ? 'flex justify-end' : 'flex justify-start'}>
            <div
              className={
                b.rol === 'user'
                  ? 'max-w-[85%] rounded-xl px-3 py-2 text-sm bg-dax-accent-soft text-dax-text'
                  : 'max-w-full sm:max-w-[92%] rounded-xl px-3 py-2 text-sm bg-dax-elevated text-dax-text'
              }
            >
              <p className="whitespace-pre-wrap break-words">{b.contenido}</p>
              {b.tablas?.map((t, i) => <TablaRespuesta key={i} tabla={t} esTelefono={esTelefono} />)}
            </div>
          </div>
        ))}
        {enviando && (
          <p className="text-sm text-dax-muted" role="status">
            <i className="fa-solid fa-circle-notch fa-spin mr-2" aria-hidden="true" />
            Consultando…
          </p>
        )}
        {error && (
          <p role="alert" className="rounded-lg px-3 py-2 text-sm bg-dax-danger-soft text-dax-danger">
            {error}
          </p>
        )}
        <div ref={finRef} />
      </div>
    </Modal>
  )
}
