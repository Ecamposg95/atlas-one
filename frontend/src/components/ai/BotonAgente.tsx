import { lazy, Suspense } from 'react'

import { useAuthStore } from '../../store/authStore'
import { useAgenteStore } from '../../store/agenteStore'
import { useEnabledModulesStore } from '../../store/enabledModulesStore'
import { agenteVisible, previaDelAgente } from '../../utils/agenteVisible'

/**
 * Entradas al agente. El panel (`PanelAgente`) baja con `lazy()` la primera
 * vez que alguien lo abre: nada del chat pesa en la ruta crítica.
 *
 * La regla de quién ve el botón vive en `utils/agenteVisible.ts`: mientras el
 * módulo `ai` siga `en_construccion` no se ve (salvo en vista previa).
 */
const PanelAgente = lazy(() => import('./PanelAgente'))

export const ROTULO_AGENTE = 'Preguntar al agente'
const ICONO = 'fa-wand-magic-sparkles'

export function useAgenteVisible(): boolean {
  const role = useAuthStore((s) => s.user?.role)
  const enabledModules = useEnabledModulesStore((s) => s.enabledModules)
  const noDisponibles = useEnabledModulesStore((s) => s.noDisponibles)
  const loaded = useEnabledModulesStore((s) => s.loaded)
  return loaded && agenteVisible({ role, enabledModules, noDisponibles, previa: previaDelAgente() })
}

export type VarianteBotonAgente = 'barra' | 'menu' | 'riel' | 'texto'

interface Props {
  /** `barra`: icono de la barra del teléfono. `menu` y `riel`: menú lateral abierto y contraído. `texto`: botón con rótulo. */
  variante: VarianteBotonAgente
  /** Texto con el que abre la caja de mensaje (Consultar manda lo escrito). */
  borrador?: string
  className?: string
}

export function BotonAgente({ variante, borrador, className = '' }: Props) {
  const visible = useAgenteVisible()
  const abrir = useAgenteStore((s) => s.abrir)
  if (!visible) return null
  const alPulsar = () => abrir(borrador?.trim() ?? '')

  if (variante === 'texto') {
    return (
      <button type="button" onClick={alPulsar} className={`dax-btn-secondary ${className}`}>
        <i className={`fa-solid ${ICONO} mr-2`} aria-hidden="true" />
        {ROTULO_AGENTE}
      </button>
    )
  }
  if (variante === 'menu') {
    return (
      <button type="button" onClick={alPulsar} className={`sb-item w-full ${className}`}>
        <i className={`fa-solid ${ICONO} sb-item-icono`} aria-hidden="true" />
        <span className="sb-item-rotulo text-left">Agente</span>
      </button>
    )
  }
  return (
    <button
      type="button"
      onClick={alPulsar}
      aria-label={ROTULO_AGENTE}
      title={ROTULO_AGENTE}
      className={`${variante === 'riel' ? 'sb-boton w-[34px] h-[34px]' : 'dax-btn-icon flex-shrink-0'} ${className}`}
    >
      <i className={`fa-solid ${ICONO} text-sm`} aria-hidden="true" />
    </button>
  )
}

/** Se monta una vez por armazón (`Layout`, `MobileLayout`): pinta el panel cuando alguien lo abre. */
export function AnfitrionAgente() {
  const abierto = useAgenteStore((s) => s.abierto)
  if (!abierto) return null
  return (
    <Suspense fallback={null}>
      <PanelAgente />
    </Suspense>
  )
}
