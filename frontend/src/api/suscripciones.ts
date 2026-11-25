import client from './client'

/**
 * Cobro de suscripciones (megaplan F3): lo que Atlas le cobra a cada tienda.
 * No es CRM Cobranza. Los importes llegan como cadena ("499.00"): convertir
 * con `num()`.
 */

export type EstadoSuscripcion = 'al_corriente' | 'por_vencer' | 'vencida' | 'suspendida' | 'cortesia'
export type EstadoCargo = 'pendiente' | 'pagado' | 'cancelado'
export type MetodoPago = 'transferencia' | 'deposito' | 'efectivo' | 'tarjeta' | 'otro'
export type Periodicidad = 'mensual' | 'anual'

export const ESTADOS: EstadoSuscripcion[] = ['al_corriente', 'por_vencer', 'vencida', 'suspendida', 'cortesia']
export const ETIQUETA_ESTADO: Record<EstadoSuscripcion, string> = {
  al_corriente: 'Al corriente',
  por_vencer: 'Por vencer',
  vencida: 'Vencida',
  suspendida: 'Suspendida',
  cortesia: 'Cortesía',
}
export const ETIQUETA_CARGO: Record<EstadoCargo, string> = {
  pendiente: 'Pendiente',
  pagado: 'Pagado',
  cancelado: 'Cancelado',
}
export const METODOS: MetodoPago[] = ['transferencia', 'deposito', 'efectivo', 'tarjeta', 'otro']
export const ETIQUETA_METODO: Record<MetodoPago, string> = {
  transferencia: 'Transferencia',
  deposito: 'Depósito',
  efectivo: 'Efectivo',
  tarjeta: 'Tarjeta',
  otro: 'Otro',
}

export interface Pago {
  id: number
  importe: string
  fecha_pago: string
  metodo: MetodoPago
  referencia: string | null
  notas: string | null
  registrado_por: string | null
  created_at: string | null
}

export interface Cargo {
  id: number
  periodo_desde: string
  periodo_hasta: string
  importe: string
  pagado: string
  saldo: string
  vence_el: string
  estado: EstadoCargo
  vencido: boolean
  pagado_at: string | null
  cancelado_at: string | null
  motivo_cancelacion: string | null
  pagos: Pago[]
}

export interface Suscripcion {
  id: number
  organization_id: number
  plan: string
  plan_nombre: string
  precio_mxn: string
  precio_lista_mxn: string
  periodicidad: Periodicidad
  dia_corte: number
  fecha_inicio: string
  proxima_renovacion: string
  estado: EstadoSuscripcion
  estado_manual: boolean
  notas: string | null
  rfc: string | null
  razon_social: string | null
  correo_facturacion: string | null
}

export interface SuscripcionDetalle {
  organization_id: number
  organizacion: string
  plan_organizacion: string | null
  suscripcion: Suscripcion | null
  cargos: Cargo[]
}

export interface FilaSuscripcion {
  organization_id: number
  organizacion: string
  plan: string
  plan_nombre: string
  precio_mxn: string
  periodicidad: Periodicidad
  proxima_renovacion: string
  estado: EstadoSuscripcion
  saldo_vencido: string
  saldo_por_vencer: string
}

export interface TotalesSuscripciones {
  cartera_vencida: string
  por_vencer: string
  ingreso_mensual_recurrente: string
  por_estado: Record<EstadoSuscripcion, number>
  sin_suscripcion: number
}

export interface ListaSuscripciones {
  totales: TotalesSuscripciones
  items: FilaSuscripcion[]
}

export interface MiSuscripcion {
  plan: {
    clave: string
    nombre: string
    precio_lista_mxn: string
    max_usuarios: number | null
    max_sucursales_venta: number | null
  }
  uso: { usuarios_activos: number; sucursales_venta: number }
  suscripcion: Suscripcion | null
  cargos: Cargo[]
}

export interface SuscripcionEntrada {
  plan?: string
  precio_mxn?: string
  periodicidad?: Periodicidad
  dia_corte?: number
  fecha_inicio?: string
  proxima_renovacion?: string
  estado?: EstadoSuscripcion
  notas?: string | null
  rfc?: string | null
  razon_social?: string | null
  correo_facturacion?: string | null
}

export interface PagoEntrada {
  importe: string
  metodo: MetodoPago
  fecha_pago?: string
  referencia?: string
  notas?: string
}

/** Cadena Numeric del backend → número para pintar. Vacío o basura → 0. */
export function num(v: string | number | null | undefined): number {
  const n = typeof v === 'number' ? v : parseFloat(v ?? '')
  return Number.isFinite(n) ? n : 0
}

/** "2026-11-24" → "24 nov 2026", sin pasar por la zona horaria del navegador. */
export function fechaCorta(iso: string | null | undefined): string {
  if (!iso) return '—'
  const [a, m, d] = iso.slice(0, 10).split('-').map(Number)
  if (!a || !m || !d) return iso
  const meses = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']
  return `${d} ${meses[m - 1]} ${a}`
}

export const suscripcionesApi = {
  /** La tienda: su plan, uso e historial (solo administrador y dueño). */
  mia: () => client.get<MiSuscripcion>('/suscripcion/mia').then((r) => r.data),

  // ── Plataforma ──
  listar: (params?: { estado?: EstadoSuscripcion; q?: string }) =>
    client.get<ListaSuscripciones>('/platform/suscripciones', { params }).then((r) => r.data),
  detalle: (orgId: number) =>
    client.get<SuscripcionDetalle>(`/platform/organizations/${orgId}/suscripcion`).then((r) => r.data),
  guardar: (orgId: number, datos: SuscripcionEntrada) =>
    client.put<SuscripcionDetalle>(`/platform/organizations/${orgId}/suscripcion`, datos).then((r) => r.data),
  generarCargo: (orgId: number, datos: { periodo_desde?: string; importe?: string; vence_el?: string } = {}) =>
    client.post<{ creado: boolean; cargo: Cargo }>(`/platform/organizations/${orgId}/suscripcion/cargos`, datos).then((r) => r.data),
  registrarPago: (cargoId: number, datos: PagoEntrada) =>
    client.post<SuscripcionDetalle>(`/platform/suscripciones/cargos/${cargoId}/pagos`, datos).then((r) => r.data),
  cancelarCargo: (cargoId: number, motivo?: string) =>
    client.post<SuscripcionDetalle>(`/platform/suscripciones/cargos/${cargoId}/cancelar`, { motivo }).then((r) => r.data),
}
