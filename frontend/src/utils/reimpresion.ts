/**
 * Lectura de la respuesta del backend al reimprimir un ticket.
 *
 * `app/routers/printer.py` distingue cuatro conflictos y el historial de
 * ventas los mostraba todos como "Error al reimprimir", así que el cajero no
 * sabía si le faltaba el PIN, si lo tecleó mal, si estaba bloqueado o si la
 * venta simplemente ya no tiene ticket que emitir:
 *
 * - 428 → falta el PIN de un supervisor (pedirlo y reintentar).
 * - 403 → el PIN no coincide con ningún supervisor de la organización.
 * - 423 → demasiados intentos fallidos; hay que esperar.
 * - 409 → la venta está cancelada: no se reimprime, con PIN o sin él.
 */

/** Forma mínima de un error de axios que nos interesa aquí. */
interface ErrorConRespuesta {
  response?: {
    status?: number
    data?: { detail?: unknown }
  }
}

/** `detail` estructurado del backend: `{code, message}`. */
interface DetalleConCodigo {
  code?: string
  message?: string
}

/** Código que el backend pone SOLO en el 403 del PIN equivocado. */
const CODIGO_PIN_INCORRECTO = 'PIN_INCORRECTO'

function estado(error: unknown): number | undefined {
  return (error as ErrorConRespuesta)?.response?.status
}

function crudo(error: unknown): unknown {
  return (error as ErrorConRespuesta)?.response?.data?.detail
}

function codigo(error: unknown): string | undefined {
  const d = crudo(error)
  if (d && typeof d === 'object' && !Array.isArray(d)) return (d as DetalleConCodigo).code
  return undefined
}

function detalle(error: unknown): string | undefined {
  const d = crudo(error)
  if (typeof d === 'string' && d.trim() !== '') return d
  if (d && typeof d === 'object' && !Array.isArray(d)) {
    const msg = (d as DetalleConCodigo).message
    if (typeof msg === 'string' && msg.trim() !== '') return msg
  }
  return undefined
}

/** El backend pide el PIN de un supervisor para esta reimpresión. */
export function requierePin(error: unknown): boolean {
  return estado(error) === 428
}

/**
 * El PIN tecleado no corresponde a ningún supervisor: se puede reintentar.
 *
 * Se exige el código y no solo el 403: el mismo endpoint responde 403 cuando la
 * venta es de otra organización, y ahí reintentar el PIN no arregla nada — el
 * modal se quedaría abierto pidiendo algo inútil.
 */
export function pinIncorrecto(error: unknown): boolean {
  return estado(error) === 403 && codigo(error) === CODIGO_PIN_INCORRECTO
}

/** Demasiados intentos fallidos: el modal debe cerrarse, no reintentar. */
export function pinBloqueado(error: unknown): boolean {
  return estado(error) === 423
}

/** Mensaje para el aviso. Prefiere el `detail` del backend, que es accionable. */
export function mensajeReimpresion(error: unknown): string {
  if (requierePin(error)) return detalle(error) ?? 'Se requiere el PIN de un supervisor'
  if (pinIncorrecto(error)) return detalle(error) ?? 'PIN incorrecto'
  if (pinBloqueado(error)) return detalle(error) ?? 'Demasiados intentos fallidos. Espera unos minutos.'
  return detalle(error) ?? 'Error al reimprimir'
}
