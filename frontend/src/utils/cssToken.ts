import { useEffect, useState } from 'react'

/**
 * chart.js pinta en <canvas>: un color `var(--p-accent)` no se resuelve y la
 * serie sale negra o invisible. Estas dos funciones traducen los tokens del
 * tema a colores concretos en el momento de pintar.
 */
export function token(nombre: string, respaldo: string, el?: Element | null): string {
  if (typeof document === 'undefined') return respaldo
  // /platform redefine los --p-* bajo `.pv2` (alias de --dax-*): ahí manda el tema.
  const base = el ?? document.querySelector('.pv2') ?? document.documentElement
  const valor = getComputedStyle(base).getPropertyValue(nombre).trim()
  if (!valor) return respaldo
  return resolverColor(valor)
}

/**
 * `color-mix(...)` (tema oscuro) y otras funciones CSS no las entiende conAlpha
 * ni siempre el canvas: un elemento sonda hace que el navegador las calcule a
 * `rgb(...)`. Sin DOM o si falla, devuelve el valor tal cual.
 */
function resolverColor(valor: string): string {
  if (typeof document === 'undefined' || !document.body) return valor
  if (/^#[0-9a-f]{6}$/i.test(valor)) return valor
  const sonda = document.createElement('span')
  sonda.style.color = valor
  document.body.appendChild(sonda)
  const c = getComputedStyle(sonda).color
  sonda.remove()
  return c || valor
}

/**
 * Señal que cambia cuando el tema (clase `.dark`) o el vertical (`data-preset`)
 * de <html> cambian. Úsala como clave de useMemo de los colores de chart.js.
 */
export function useTemaActual(): string {
  const leer = () =>
    typeof document === 'undefined'
      ? ''
      : `${document.documentElement.className}|${document.documentElement.getAttribute('data-preset') ?? ''}`
  const [tema, setTema] = useState(leer)
  useEffect(() => {
    if (typeof MutationObserver === 'undefined') return
    const obs = new MutationObserver(() => setTema(leer()))
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ['class', 'data-preset'] })
    return () => obs.disconnect()
  }, [])
  return tema
}

/** `#rrggbb`, `rgb(r, g, b)` o `rgba(r, g, b, a)` → `rgba(r, g, b, alpha)`; otro formato se devuelve tal cual. */
export function conAlpha(color: string, alpha: number): string {
  const rgb = /^rgba?\(\s*(\d+(?:\.\d+)?)[,\s]+(\d+(?:\.\d+)?)[,\s]+(\d+(?:\.\d+)?)\s*(?:[,/]\s*[\d.]+%?\s*)?\)$/i.exec(color)
  if (rgb) return `rgba(${rgb[1]}, ${rgb[2]}, ${rgb[3]}, ${alpha})`
  const m = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(color)
  if (!m) return color
  const [r, g, b] = [m[1], m[2], m[3]].map((h) => parseInt(h, 16))
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}
