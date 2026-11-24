// frontend/src/components/layout/RedirigirConQuery.tsx
import { Navigate, useLocation, useParams } from 'react-router-dom'

/**
 * Redirección que conserva la consulta (`?q=…&variant=…`) y el hash. Para las
 * URL viejas del admin que la Fase 3 fusionó (`/hq/sales` → `/sales`, …): un
 * enlace guardado con filtros sigue abriendo lo mismo en la ruta nueva.
 */
export function RedirigirConQuery({ a }: { a: string }) {
  const { search, hash } = useLocation()
  // El destino puede traer su propia consulta (`/configuracion?tab=…`): la de la URL vieja se le suma.
  const extra = a.includes('?') ? search.replace(/^\?/, '&') : search
  return <Navigate to={`${a}${extra}${hash}`} replace />
}

/** `/hq/branches/:branchId` → la pestaña Sucursales de Configuración con esa sucursal abierta. */
export function RedirigirASucursal() {
  const { branchId } = useParams<{ branchId: string }>()
  return <Navigate to={`/configuracion?tab=sucursales&sucursal=${encodeURIComponent(branchId ?? '')}`} replace />
}
