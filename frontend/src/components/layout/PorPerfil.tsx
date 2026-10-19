// frontend/src/components/layout/PorPerfil.tsx
import { useEffect, type ReactNode } from 'react'
import { useEnabledModulesStore } from '../../store/enabledModulesStore'
import { Spinner } from '../ui/Spinner'

/**
 * Elige pantalla por perfil de interfaz (modo básico). Espera al contexto
 * antes de decidir: así una FREE no monta la pantalla completa (ni baja su
 * chunk) para cambiarla un segundo después, y una de paga nunca ve la básica.
 * Si el contexto falla, el store queda en 'completo' (fail-open).
 */
export function PorPerfil({ basico, completo }: { basico: ReactNode; completo: ReactNode }) {
  const loaded = useEnabledModulesStore((s) => s.loaded)
  const load = useEnabledModulesStore((s) => s.load)
  const perfilUi = useEnabledModulesStore((s) => s.perfilUi)
  useEffect(() => {
    if (!loaded) void load()
  }, [loaded, load])
  if (!loaded) {
    return (
      <div className="flex items-center justify-center h-full">
        <Spinner size="lg" text="Cargando..." />
      </div>
    )
  }
  return <>{perfilUi === 'basico' ? basico : completo}</>
}
