import type { ClaseRenglon } from '../../../api/cargas'

/** Cantidad sin ceros de relleno: "3.00" → "3", "1.50" → "1.5". */
export function cantidad(s: string | number | null | undefined): string {
  const n = Number(s)
  return Number.isFinite(n) ? String(n) : String(s ?? '')
}

export const CLASES: Record<ClaseRenglon, string> = {
  EXISTE: 'Ya existe',
  SUMA: 'Se suman piezas',
  NUEVO: 'Nuevo',
  YA_CARGADO: 'Ya cargado',
  IGNORADO: 'Ignorado',
}

/** Etiquetas en español de los campos técnicos de un cambio; lo desconocido se muestra tal cual. */
const CAMPOS: Record<string, string> = {
  precio: 'Precio', costo: 'Costo', clase: 'Clase', sku: 'SKU', talla: 'Talla', color: 'Color',
  marca: 'Marca', tipo: 'Tipo', departamento: 'Departamento', genero: 'Género', cantidad: 'Piezas',
  nombre: 'Nombre',
}
export const campo = (k: string): string => CAMPOS[k] ?? k

export function valor(v: unknown): string {
  if (v === null || v === undefined || v === '') return '—'
  if (typeof v === 'string' && v in CLASES) return CLASES[v as ClaseRenglon]
  return String(v)
}

const MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']

/** "10 nov": fijo, sin depender de los datos de idioma del navegador. */
export function fechaCorta(iso: string): string {
  const d = new Date(iso)
  return `${d.getDate()} ${MESES[d.getMonth()]}`
}
