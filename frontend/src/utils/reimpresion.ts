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

function estado(error: unknown): number | undefined {
  return (error as ErrorConRespuesta)?.response?.status
}

function detalle(error: unknown): string | undefined {
  const d = (error as ErrorConRespuesta)?.response?.data?.detail
  return typeof d === 'string' && d.trim() !== '' ? d : undefined
}

/** El backend pide el PIN de un supervisor para esta reimpresión. */
export function requierePin(error: unknown): boolean {
  return estado(error) === 428
}

/** El PIN tecleado no corresponde a ningún supervisor: se puede reintentar. */
export function pinIncorrecto(error: unknown): boolean {
  return estado(error) === 403
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
