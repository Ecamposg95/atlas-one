// frontend/src/components/layout/RedirigirConQuery.tsx
import { Navigate, useLocation } from 'react-router-dom'

/**
 * Redirección que conserva la consulta (`?q=…&variant=…`) y el hash. Para las
 * URL viejas del admin que la Fase 3 fusionó (`/hq/sales` → `/sales`, …): un
 * enlace guardado con filtros sigue abriendo lo mismo en la ruta nueva.
 */
export function RedirigirConQuery({ a }: { a: string }) {
  const { search, hash } = useLocation()
  return <Navigate to={`${a}${search}${hash}`} replace />
}
