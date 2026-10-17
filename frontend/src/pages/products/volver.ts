/**
 * A dónde regresa el formulario al terminar: `?volver=/ruta` interna o el defecto.
 * Solo rutas del mismo sitio: sin `\` (el navegador lo normaliza a `/` y `/\\evil.com`
 * acaba en otro dominio), sin `//` y sin que `new URL` cambie el origen.
 */
export function destinoDeRegreso(search: string, defecto: string): string {
  const v = new URLSearchParams(search).get('volver')
  if (!v || !v.startsWith('/') || v.startsWith('//') || v.includes('\\')) return defecto
  try {
    if (new URL(v, 'http://x').origin !== 'http://x') return defecto
  } catch {
    return defecto
  }
  return v
}
