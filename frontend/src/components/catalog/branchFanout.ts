import type { BranchStatusPatch } from '../../api/products'

/**
 * Qué escrituras hay que mandar para aplicar un cambio de sucursal a TODAS
 * las tallas vivas de un producto.
 *
 * La matriz de sucursales y los ajustes por sucursal editaban solo la
 * variante principal (`variants[0]`): apagar el POS o poner un precio de
 * sucursal dejaba las demás tallas vendiéndose, y al precio viejo. Es un bug
 * de dinero, así que el cambio viaja a todas.
 *
 * - `is_active_pos` tiene endpoint masivo (`/branch-status/bulk-toggle`): un
 *   solo request para las N tallas. Pero ese endpoint es admin-only y la
 *   matriz también la abre un CAJERO desde el catálogo, así que `canBulk`
 *   decide si se puede usar; si no, el POS también va talla por talla.
 * - El resto de campos no lo tiene: un `PATCH .../branch-status` por talla.
 * - Con UNA sola talla todo va por PATCH, igual que antes del fix (mismo
 *   endpoint, misma bitácora `PBS_UPDATE`).
 */
export interface BranchStatusPlan {
  bulk: { variantIds: string[]; isActivePos: boolean } | null
  patches: { variantIds: string[]; patch: BranchStatusPatch } | null
}

export function planBranchStatusWrites(
  variantIds: string[],
  patch: BranchStatusPatch,
  canBulk = true,
): BranchStatusPlan {
  if (variantIds.length === 0) return { bulk: null, patches: null }

  const resto: BranchStatusPatch = { ...patch }
  let bulk: BranchStatusPlan['bulk'] = null

  if (canBulk && variantIds.length > 1 && patch.is_active_pos !== undefined) {
    bulk = { variantIds, isActivePos: patch.is_active_pos }
    delete resto.is_active_pos
  }

  const hayResto = Object.keys(resto).length > 0
  return { bulk, patches: hayResto ? { variantIds, patch: resto } : null }
}
