import { Navigate } from 'react-router-dom'
import { useAuthStore } from '../../store/authStore'
import type { Role } from '../../types/auth'
import { rolesConAcceso } from './navConfig'

/**
 * Route guard that restricts children to users whose tenant `role` is in
 * `roles`. SUPERADMIN/SUPPORT on the platform side bypass tenant RBAC.
 *
 * Defense in depth: this is a UX guard only — the backend still enforces
 * authorization on every API call. Do not rely on this to hide sensitive
 * data; rely on it to prevent confusing redirects and unreachable UI.
 *
 * Unauthorized users are redirected to `/atlas-pos` (the default home).
 */
export function RequireRole({
  roles,
  children,
  redirectTo = '/atlas-pos',
}: {
  roles: Role[]
  children: React.ReactNode
  redirectTo?: string
}) {
  const user = useAuthStore((s) => s.user)
  const hydrated = useAuthStore((s) => s.hydrated)

  // Wait for auth hydration before deciding — avoid flashing redirect for valid users.
  if (!hydrated) return null

  // Platform staff (SUPERADMIN/SUPPORT) bypass tenant-role checks.
  if (user?.platform_role === 'SUPERADMIN' || user?.platform_role === 'SUPPORT') {
    return <>{children}</>
  }

  if (!user || !roles.includes(user.role)) {
    return <Navigate to={redirectTo} replace />
  }

  return <>{children}</>
}

/**
 * Guarda una ruta con los mismos roles que la ven en el menú (`ROLE_ROUTES`).
 *
 * Antes solo 5 de ~55 rutas verificaban el rol: cualquier usuario autenticado
 * que escribiera `/users` veía la lista completa de usuarios, y en
 * `/organization` la configuración fiscal y de comisión de tarjeta
 * (audit-funcional #13). Quien no tiene permiso vuelve a `/`, que reenvía a
 * su propio inicio según su rol.
 *
 * Sigue siendo una guarda de interfaz: el backend es el que autoriza de
 * verdad en cada llamada.
 */
export function RutaPorRol({ url, children }: { url: string; children: React.ReactNode }) {
  return <RequireRole roles={rolesConAcceso(url)} redirectTo="/">{children}</RequireRole>
}
