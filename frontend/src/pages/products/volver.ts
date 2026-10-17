/** A dónde regresa el formulario al terminar: `?volver=/ruta` interna o el defecto. */
export function destinoDeRegreso(search: string, defecto: string): string {
  const v = new URLSearchParams(search).get('volver')
  if (!v || !v.startsWith('/') || v.startsWith('//')) return defecto
  return v
}
