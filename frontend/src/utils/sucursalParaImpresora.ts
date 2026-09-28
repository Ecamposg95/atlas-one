/**
 * Qué sucursal configura la pantalla de impresora cuando el usuario no trae una
 * (la dueña entra en contexto HQ). Reglas, en orden:
 *   1. Si exactamente una sucursal vende, es esa: ahí está la impresora, aunque
 *      la dueña esté asignada a la matriz (Kaory: Alicia en la HQ, caja en Pino Suárez).
 *   2. Si varias venden, la asignada a la dueña.
 *   3. Si solo hay una, esa.
 *   4. Si no, `null`: hay que preguntarle.
 */
export interface SucursalParaImpresora {
  id: number
  name: string
  branch_type: string
  is_headquarters?: boolean
  can_sell?: boolean
}

export function elegirSucursalParaImpresora<T extends SucursalParaImpresora>(
  branchIdDelUsuario: number | null,
  sucursales: T[],
): T | null {
  if (sucursales.length === 0) return null
  const venden = sucursales.filter((s) => s.can_sell !== false)
  if (venden.length === 1) return venden[0]
  const propia = branchIdDelUsuario != null ? sucursales.find((s) => s.id === branchIdDelUsuario) : undefined
  if (propia) return propia
  if (sucursales.length === 1) return sucursales[0]
  return null
}
