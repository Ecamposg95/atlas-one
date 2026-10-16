/**
 * chart.js pinta en <canvas>: un color `var(--p-accent)` no se resuelve y la
 * serie sale negra o invisible. Estas dos funciones traducen los tokens del
 * tema a colores concretos en el momento de pintar.
 */
export function token(nombre: string, respaldo: string): string {
  if (typeof document === 'undefined') return respaldo
  return getComputedStyle(document.documentElement).getPropertyValue(nombre).trim() || respaldo
}

/** `#rrggbb` → `rgba(r, g, b, alpha)`; cualquier otro formato se devuelve tal cual. */
export function conAlpha(color: string, alpha: number): string {
  const m = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(color)
  if (!m) return color
  const [r, g, b] = [m[1], m[2], m[3]].map((h) => parseInt(h, 16))
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}
