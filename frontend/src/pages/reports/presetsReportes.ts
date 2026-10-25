// frontend/src/pages/reports/presetsReportes.ts
import { daysAgoStr, todayStr } from '../../utils/dates'

/**
 * Periodos de Reportes (spec 2026-10-23 §3.2). Replican
 * `metricas_ventas.periodo_preset`: `7d` = hoy y 6 anteriores, `30d` = hoy y
 * 29, `mes` = del 1 a hoy. El comparativo lo calcula el backend
 * (`Periodo.anterior()`: mismo largo, termina el día antes del inicio).
 * Fechas `YYYY-MM-DD` locales (como `todayStr`), inclusivas.
 */
export type ClavePreset = 'hoy' | 'ayer' | '7d' | '30d' | 'mes'
export interface Rango { inicio: string; fin: string }

export const PRESETS: { clave: ClavePreset; etiqueta: string }[] = [
  { clave: 'hoy', etiqueta: 'Hoy' },
  { clave: 'ayer', etiqueta: 'Ayer' },
  { clave: '7d', etiqueta: '7 días' },
  { clave: '30d', etiqueta: '30 días' },
  { clave: 'mes', etiqueta: 'Este mes' },
]

export function rangoPreset(clave: ClavePreset): Rango {
  const hoy = todayStr()
  switch (clave) {
    case 'hoy': return { inicio: hoy, fin: hoy }
    case 'ayer': return { inicio: daysAgoStr(1), fin: daysAgoStr(1) }
    case '7d': return { inicio: daysAgoStr(6), fin: hoy }
    case '30d': return { inicio: daysAgoStr(29), fin: hoy }
    case 'mes': return { inicio: `${hoy.slice(0, 8)}01`, fin: hoy }
  }
}

/** Qué botón de la barra corresponde al rango; null si lo escribió a mano. */
export function presetActivo(r: Rango): ClavePreset | null {
  for (const p of PRESETS) {
    const x = rangoPreset(p.clave)
    if (x.inicio === r.inicio && x.fin === r.fin) return p.clave
  }
  return null
}

/** A mediodía local para que la zona horaria no mueva el día. */
const aFecha = (iso: string) => new Date(`${iso}T12:00:00`)
const aIso = (d: Date) => d.toLocaleDateString('en-CA')

export function fechasDelRango(r: Rango): string[] {
  const salida: string[] = []
  const d = aFecha(r.inicio)
  while (aIso(d) <= r.fin && salida.length < 400) {
    salida.push(aIso(d))
    d.setDate(d.getDate() + 1)
  }
  return salida
}

export const diasDelRango = (r: Rango): number => fechasDelRango(r).length

/** "vie 23" */
export const etiquetaDia = (iso: string): string =>
  aFecha(iso).toLocaleDateString('es-MX', { weekday: 'short', day: 'numeric' })

const diaMes = (iso: string) => aFecha(iso).toLocaleDateString('es-MX', { day: 'numeric', month: 'short' })

/** "23 oct" o "17 oct – 23 oct". */
export const etiquetaRango = (r: Rango): string =>
  r.inicio === r.fin ? diaMes(r.inicio) : `${diaMes(r.inicio)} – ${diaMes(r.fin)}`

/**
 * Etiquetas de la tendencia: las fechas del rango en español (el backend las
 * manda en inglés, `strftime("%a %d")`). Si el servidor devolvió otra cantidad
 * de puntos, se usan las suyas para no desalinear la gráfica.
 */
export function etiquetasTendencia(r: Rango, puntos: number, respaldo: string[]): string[] {
  const fechas = fechasDelRango(r)
  return fechas.length === puntos ? fechas.map(etiquetaDia) : respaldo
}
