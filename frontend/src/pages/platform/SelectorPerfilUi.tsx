import type { CSSProperties } from 'react'

/** Valores de `organization.perfil_ui` (app/services/perfil_ui.py). */
export const OPCIONES_PERFIL_UI = [
  { valor: 'auto', etiqueta: 'Automático (FREE = básico)' },
  { valor: 'basico', etiqueta: 'Básico' },
  { valor: 'completo', etiqueta: 'Completo' },
] as const

/** Selector del perfil de interfaz junto a "Plan y uso". NULL guardado = automático. */
export function SelectorPerfilUi({ valor, onCambio, deshabilitado, estilo }: {
  valor: string | null | undefined
  onCambio: (v: string) => void
  deshabilitado?: boolean
  estilo?: CSSProperties
}) {
  return (
    <select
      value={valor ?? 'auto'}
      onChange={(e) => onCambio(e.target.value)}
      disabled={deshabilitado}
      aria-label="Perfil de interfaz"
      style={estilo}
    >
      {OPCIONES_PERFIL_UI.map((o) => <option key={o.valor} value={o.valor}>{o.etiqueta}</option>)}
    </select>
  )
}
