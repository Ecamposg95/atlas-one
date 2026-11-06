/**
 * Reglas del cajón de dinero. El cajón se abre por el agente local de la PC:
 * dentro de los bytes del ticket (lo arma el servidor) o con `/drawer/open`
 * cuando no hay ticket. `open_drawer_on_print` de la sucursal manda en los dos.
 */
const clave = (branchId: number) => `atlas_cajon_al_cobrar:${branchId}`

type Pago = { method?: string | null }

/** Por qué no se puede abrir el cajón desde esta PC; `null` si se puede. */
export function motivoSinCajon(impresora: string | null | undefined, agente: boolean | null): string | null {
  if (agente === false) return 'El agente de impresión no responde en esta PC.'
  if (!impresora) return 'Elige tu impresora primero.'
  if (impresora.startsWith('BT:')) return 'Las impresoras Bluetooth todavía no abren el cajón.'
  return null
}

/** La impresora es de cada PC; la de la sucursal solo cubre a la PC que no ha elegido una. */
export function impresoraEfectiva(local: string | null | undefined, sucursal: string | null | undefined): string | null {
  return local || sucursal || null
}

export function pagoIncluyeEfectivo(pagos: Pago[]): boolean {
  return pagos.some((p) => ['CASH', 'EFECTIVO'].includes((p.method ?? '').toUpperCase()))
}

/** Un cobro sin ticket no lleva la orden en los bytes: hay que pedirla aparte. */
export function debeAbrirCajonSinTicket({ pagos, impresora, abreAlCobrar }: {
  pagos: Pago[]
  impresora: string | null | undefined
  abreAlCobrar: boolean
}): boolean {
  return abreAlCobrar && !!impresora && !impresora.startsWith('BT:') && pagoIncluyeEfectivo(pagos)
}

/** Recordado en el navegador para saberlo también sin red; `true` es el valor de la columna. */
export function leerCajonAlCobrar(branchId: number | null | undefined): boolean {
  if (branchId == null) return true
  try { return localStorage.getItem(clave(branchId)) !== '0' } catch { return true }
}

export function guardarCajonAlCobrar(branchId: number, valor: boolean): void {
  try { localStorage.setItem(clave(branchId), valor ? '1' : '0') } catch { /* queda el valor por omisión */ }
}
