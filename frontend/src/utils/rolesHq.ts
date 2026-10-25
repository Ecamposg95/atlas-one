// frontend/src/utils/rolesHq.ts
/**
 * Roles de oficina (spec 2026-10-23 §4.1, "Solo HQ"): ven toda la organización,
 * los costos y las acciones de catálogo. Es la misma lista que usaban
 * `HQInventory` (ADMIN_ROLES) y `Products` (HQ_ROLES). No mira `platform_role`:
 * quien impersona trae un rol de tenant.
 */
export const ROLES_HQ: ReadonlySet<string> = new Set(['ADMINISTRADOR', 'DUEÑO'])

export const esRolHq = (role: string | null | undefined): boolean => ROLES_HQ.has(role ?? '')
