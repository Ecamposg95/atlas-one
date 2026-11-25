// frontend/src/components/layout/SoloMovil.tsx
import type { ReactNode } from 'react'
import { useAuthStore } from '../../store/authStore'
import { useIsMobile } from '../../hooks/useIsMobile'
import { rolesConAcceso } from './navConfig'
import { RedirigirConQuery } from './RedirigirConQuery'
import type { Role } from '../../types/auth'

/**
 * Pantalla pensada para teléfono y tablet (< 1024 px, el mismo corte del
 * armazón). En escritorio redirige a su equivalente —conservando `?…`— siempre
 * que el rol tenga esa pantalla; si no (soporte operativo, cuyo trabajo ES esta
 * pantalla) se queda donde está.
 */
export function SoloMovil({ enEscritorio, children }: { enEscritorio: string; children: ReactNode }) {
  const enMovil = useIsMobile()
  const rol = useAuthStore((s) => s.user?.role) as Role | undefined
  if (!enMovil && rol && rolesConAcceso(enEscritorio).includes(rol)) {
    return <RedirigirConQuery a={enEscritorio} />
  }
  return <>{children}</>
}
