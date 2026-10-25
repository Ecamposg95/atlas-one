// frontend/src/components/graficas/tema.ts
import { useMemo } from 'react'
import { useTemaActual } from '../../utils/cssToken'

/**
 * Colores del tema para chart.js (spec 2026-10-23 §3.3). El canvas no entiende
 * `var(--dax-accent)`: aquí se leen los tokens de `<html>` con
 * `getComputedStyle` y se vuelven a leer cuando cambia la clase (`.dark`) o
 * el `data-preset` de `<html>` (MutationObserver en `useTemaActual`), para que
 * la gráfica se repinte al cambiar de tema sin recargar.
 */
export interface TemaGrafica {
  texto: string
  muted: string
  faint: string
  /** `--dax-border-dim`: rejilla y bordes de tooltip. */
  borde: string
  /** `--dax-card-solid`: fondo del tooltip y separación entre gajos de la dona. */
  cardSolid: string
  acento: string
  success: string
  warning: string
  danger: string
}

/** Respaldos = tema oscuro de index.css; solo se usan sin DOM o sin la variable. */
const RESPALDO: TemaGrafica = {
  texto: '#ededf8', muted: '#b9b9d0', faint: '#8c8cab', borde: 'rgba(237, 237, 248, 0.08)', cardSolid: '#14142e',
  acento: '#6366f1', success: '#34D399', warning: '#FBBF24', danger: '#F87171',
}

const VARIABLES: Record<keyof TemaGrafica, string> = {
  texto: '--dax-text', muted: '--dax-text-muted', faint: '--dax-text-faint', borde: '--dax-border-dim',
  cardSolid: '--dax-card-solid', acento: '--dax-accent', success: '--dax-success', warning: '--dax-warning',
  danger: '--dax-danger',
}

/** El token en <html>: el valor calculado y, si el entorno no lo calcula (jsdom), el declarado en línea. */
function leerVariable(nombre: string): string {
  const raiz = document.documentElement
  return (getComputedStyle(raiz).getPropertyValue(nombre) || raiz.style.getPropertyValue(nombre)).trim()
}

/** `color-mix(...)` (acento del tema oscuro) no lo entiende el canvas: una sonda hace que el navegador lo calcule a `rgb(...)`. */
function resolver(valor: string): string {
  if (/^(#[0-9a-f]{3,8}|rgba?\(.*\))$/i.test(valor) || !document.body) return valor
  const sonda = document.createElement('span')
  sonda.style.color = valor
  document.body.appendChild(sonda)
  const c = getComputedStyle(sonda).color
  sonda.remove()
  return c || valor
}

export function leerTemaGrafica(): TemaGrafica {
  if (typeof document === 'undefined') return RESPALDO
  const salida: TemaGrafica = { ...RESPALDO }
  for (const clave of Object.keys(VARIABLES) as (keyof TemaGrafica)[]) {
    const v = leerVariable(VARIABLES[clave])
    if (v) salida[clave] = resolver(v)
  }
  return salida
}

/** Colores del tema actual; cambia de identidad cuando cambia la clase de <html>. */
export function useTemaGrafica(): TemaGrafica {
  const claveTema = useTemaActual()
  // La señal es la dependencia a propósito: es lo que avisa que hay que releer.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  return useMemo(() => leerTemaGrafica(), [claveTema])
}

/** Efectivo = success, tarjeta = acento, transferencia = warning, lo demás tenue (spec §3.3). */
export function colorMetodo(metodo: string, tema: TemaGrafica): string {
  switch (metodo.toUpperCase()) {
    case 'CASH': return tema.success
    case 'CARD': return tema.acento
    case 'TRANSFER': return tema.warning
    default: return tema.faint
  }
}
