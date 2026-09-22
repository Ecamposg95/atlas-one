/**
 * Diccionarios de los enums del backend, en español llano.
 *
 * El backend manda constantes (`CLOSED`, `ADJUSTMENT_IN`, `TOGGLE_MODULE`,
 * `SOPORTE_OPERATIVO`) y varias pantallas de administración las pintaban tal
 * cual. Aquí viven las traducciones, en un módulo sin React para poder
 * probarlas y para que no se dupliquen pantalla por pantalla.
 *
 * Regla de oro: un valor desconocido NUNCA se oculta. Si el backend agrega un
 * estado nuevo, se muestra legible (guiones bajos fuera, capitalizado) en vez
 * de desaparecer o romper la tabla.
 */

/** Último recurso: `REFUNDED_PARTIAL` → `Refunded partial`. */
export function humanizar(valor: string): string {
  const limpio = valor.replace(/_/g, ' ').trim().toLowerCase()
  if (!limpio) return '—'
  return limpio.charAt(0).toUpperCase() + limpio.slice(1)
}

function traductor(tabla: Record<string, string>) {
  return (valor: string | null | undefined): string => {
    if (valor === null || valor === undefined || valor === '') return '—'
    return tabla[valor] ?? humanizar(valor)
  }
}

/** Estado de una venta — `DocumentStatus` (app/models/sales.py). */
export const ESTADOS_VENTA: Record<string, string> = {
  DRAFT: 'Borrador',
  PENDING: 'Por cobrar',
  PAID: 'Pagada',
  CLOSED: 'Cerrada',
  OPEN: 'Abierta',
  CANCELLED: 'Cancelada',
  REFUNDED_PARTIAL: 'Devuelta en parte',
  REFUNDED_TOTAL: 'Devuelta completa',
}
export const estadoVenta = traductor(ESTADOS_VENTA)

/** Forma de pago — `PaymentMethod`. */
export const METODOS_PAGO: Record<string, string> = {
  CASH: 'Efectivo',
  CARD: 'Tarjeta',
  TRANSFER: 'Transferencia',
  OTHER: 'Otro',
}
export const metodoPago = traductor(METODOS_PAGO)

/** Movimiento del kardex — `MovementType` (app/models/inventory.py). */
export const TIPOS_MOVIMIENTO: Record<string, string> = {
  PURCHASE_IN: 'Entrada por compra',
  SALE_OUT: 'Venta',
  ADJUSTMENT_IN: 'Ajuste (+)',
  ADJUSTMENT_OUT: 'Ajuste (−)',
  TRANSFER_IN: 'Traspaso recibido',
  TRANSFER_OUT: 'Traspaso enviado',
  SALE_RETURN: 'Devolución',
  RECIPE_CONSUMPTION: 'Consumo por receta',
}
export const tipoMovimiento = traductor(TIPOS_MOVIMIENTO)

/** Acción de la bitácora de auditoría. */
export const ACCIONES_BITACORA: Record<string, string> = {
  CREATE: 'Alta',
  UPDATE: 'Cambio',
  DELETE: 'Baja',
  UPDATE_ORG_INDUSTRY: 'Cambio de giro',
  TOGGLE_MODULE: 'Módulo encendido o apagado',
  APPROVE: 'Aprobación',
  REJECT: 'Rechazo',
  ARCHIVE: 'Archivado',
}
export const accionBitacora = traductor(ACCIONES_BITACORA)

/** Estado de una devolución — `ReturnStatus`. */
export const ESTADOS_DEVOLUCION: Record<string, string> = {
  PENDING: 'Por aprobar',
  APPROVED: 'Aprobada',
  REJECTED: 'Rechazada',
}
export const estadoDevolucion = traductor(ESTADOS_DEVOLUCION)

/** Rol del usuario dentro de la organización. */
export const ROLES_USUARIO: Record<string, string> = {
  ADMINISTRADOR: 'Administrador',
  DUEÑO: 'Dueño',
  GERENTE: 'Gerente',
  CAJERO: 'Cajero',
  VENDEDOR: 'Vendedor',
  SOPORTE_OPERATIVO: 'Soporte',
  CLIENTE: 'Cliente',
}
export const rolUsuario = traductor(ROLES_USUARIO)
