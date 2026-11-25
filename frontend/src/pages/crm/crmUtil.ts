/** Utilidades del CRM de la tienda (ficha, campos propios, seguimiento). */

/** Cajera y vendedor: alta rápida y corrección de contacto; lo demás es de la gerencia. */
export const esRolDeCaja = (role: string | null | undefined): boolean => role === 'CAJERO' || role === 'VENDEDOR'

export const fechaCorta = (iso: string | null | undefined): string => {
  if (!iso) return '—'
  // Fecha sola (YYYY-MM-DD): sin zona, para que no se recorra un día.
  const d = /^\d{4}-\d{2}-\d{2}$/.test(iso) ? new Date(`${iso}T12:00:00`) : new Date(iso)
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleDateString('es-MX', { day: '2-digit', month: 'short', year: 'numeric' })
}

export const hoyIso = (): string => {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

/** Vencido (antes de hoy), para hoy, o próximo. */
export function estadoDeFecha(due: string, hoy = hoyIso()): 'vencido' | 'hoy' | 'proximo' {
  if (due < hoy) return 'vencido'
  return due === hoy ? 'hoy' : 'proximo'
}

export function valorDeCampo(tipo: string, v: unknown): string {
  if (v == null || v === '') return '—'
  if (tipo === 'SI_NO') return v ? 'Sí' : 'No'
  if (tipo === 'FECHA') return fechaCorta(String(v))
  return String(v)
}

export function apiErrorMessage(err: unknown, fallback: string): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return typeof detail === 'string' ? detail : fallback
}
