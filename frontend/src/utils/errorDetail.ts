/**
 * Texto legible a partir del `detail` de un error de FastAPI.
 *
 * `detail` es una CADENA en los errores que lanza la app
 * (`HTTPException(detail="...")`) pero un ARREGLO de objetos en los 422 de
 * validación de Pydantic. Pintarlo directo en un toast daba
 * "[object Object]" — justo cuando el usuario más necesita saber qué pasó.
 */
export function errorDetailText(detail: unknown, fallback: string): string {
  if (typeof detail === 'string') return detail.trim() || fallback

  if (Array.isArray(detail)) {
    const msgs = detail
      .map((d) => (d && typeof d === 'object' ? (d as { msg?: unknown }).msg : null))
      .filter((m): m is string => typeof m === 'string' && m.trim() !== '')
    if (msgs.length) return msgs.join('; ')
  }

  return fallback
}
