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

/** Perfil que de verdad ve la tienda: el forzado, o el que deriva del plan (solo FREE explícito = básico). */
export function perfilEfectivoUi(perfilUi: string | null | undefined, plan: string | null | undefined): 'basico' | 'completo' {
  if (perfilUi === 'basico' || perfilUi === 'completo') return perfilUi
  return String(plan ?? '').trim().toUpperCase() === 'FREE' ? 'basico' : 'completo'
}

/** Línea "Efectivo: básico/completo" junto al selector. */
export function PerfilEfectivoHint({ perfilUi, plan }: { perfilUi: string | null | undefined; plan: string | null | undefined }) {
  return <span style={{ fontSize: 11, color: 'var(--p-muted)' }}>{`Efectivo: ${perfilEfectivoUi(perfilUi, plan) === 'basico' ? 'básico' : 'completo'}`}</span>
}
