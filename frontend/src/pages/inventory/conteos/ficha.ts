import type { Product } from '../../../types/products'

/**
 * Formulario de la ficha completa que se corrige durante el conteo. Los campos
 * del PRODUCTO (nombre, marca, modelo, descripción, departamento) van al PUT
 * del producto; los de ESTA TALLA (talla, color, código, precio, costo) al PUT
 * de la variante. Todo se captura como texto y se normaliza al comparar.
 */
export interface FormFicha {
  name: string
  brand_id: string
  model: string
  description: string
  department_id: string
  size: string
  color: string
  barcode: string
  price: string
  cost: string
}

export interface CambiosProducto {
  name?: string
  brand_id?: string | null
  model?: string | null
  description?: string | null
  department_id?: string | null
}

export interface CambiosVariante {
  size?: string | null
  color?: string | null
  barcode?: string | null
  price?: number
  cost?: number
}

export interface CambiosFicha {
  producto: CambiosProducto | null
  variante: CambiosVariante | null
  /** Motivo por el que no se puede guardar; `null` si el formulario es válido. */
  error: string | null
}

const FORM_VACIO: FormFicha = {
  name: '', brand_id: '', model: '', description: '', department_id: '',
  size: '', color: '', barcode: '', price: '', cost: '',
}

/** Arma el formulario desde el producto completo del catálogo y la talla que se está revisando. */
export function formDesde(p: Product, variantId: string): FormFicha {
  const v = p.variants?.find((x) => x.id === variantId)
  return {
    ...FORM_VACIO,
    name: p.name ?? '',
    brand_id: p.brand_id ?? '',
    model: p.model ?? '',
    description: p.description ?? '',
    department_id: p.department?.id ?? '',
    size: v?.size ?? '',
    color: v?.color ?? '',
    barcode: v?.barcode ?? '',
    price: v ? String(v.price) : String(p.price ?? ''),
    cost: v ? String(v.cost) : String(p.cost ?? ''),
  }
}

const texto = (s: string): string | null => { const t = s.trim(); return t === '' ? null : t }

function numero(s: string, etiqueta: string): { valor: number | null; error: string | null } {
  const t = s.trim()
  if (t === '') return { valor: null, error: null }
  const n = Number(t)
  if (!Number.isFinite(n) || n < 0) return { valor: null, error: `${etiqueta} no es válido` }
  return { valor: n, error: null }
}

/**
 * Diferencia entre lo que había y lo que se capturó. Solo viaja lo que cambió;
 * un bloque sin cambios es `null` y no genera llamada. Vacío = quitar el dato
 * (null), salvo el nombre, que es obligatorio, y precio/costo, que se dejan
 * como estaban si se borran.
 */
export function cambiosFicha(original: FormFicha, form: FormFicha): CambiosFicha {
  const nombre = texto(form.name)
  if (nombre === null) return { producto: null, variante: null, error: 'El nombre no puede quedar vacío' }

  const producto: CambiosProducto = {}
  if (nombre !== texto(original.name)) producto.name = nombre
  for (const k of ['brand_id', 'model', 'description', 'department_id'] as const) {
    const nuevo = texto(form[k]); if (nuevo !== texto(original[k])) producto[k] = nuevo
  }

  const variante: CambiosVariante = {}
  for (const k of ['size', 'color', 'barcode'] as const) {
    const nuevo = texto(form[k]); if (nuevo !== texto(original[k])) variante[k] = nuevo
  }
  for (const [k, etiqueta] of [['price', 'El precio'], ['cost', 'El costo']] as const) {
    const n = numero(form[k], etiqueta)
    if (n.error) return { producto: null, variante: null, error: n.error }
    if (n.valor !== null && n.valor !== numero(original[k], etiqueta).valor) variante[k] = n.valor
  }

  return {
    producto: Object.keys(producto).length ? producto : null,
    variante: Object.keys(variante).length ? variante : null,
    error: null,
  }
}
