import { useState, type ReactNode } from 'react'

/**
 * "Más opciones" plegado del modo básico. Con `activo=false` (perfil
 * completo) devuelve los hijos tal cual, sin envoltorio: la pantalla de paga
 * queda idéntica. Con `activo`, los hijos se MONTAN solo al abrir (render
 * condicional, no `hidden`).
 */
export function MasOpciones({ activo, titulo = 'Más opciones', children }: { activo: boolean; titulo?: string; children: ReactNode }) {
  const [abierto, setAbierto] = useState(false)
  if (!activo) return <>{children}</>
  return (
    <div className="space-y-4">
      <button
        type="button"
        onClick={() => setAbierto((a) => !a)}
        aria-expanded={abierto}
        className="dax-btn-secondary text-xs min-h-[44px] sm:min-h-0 w-full sm:w-auto justify-center"
      >
        <i className={`fa-solid ${abierto ? 'fa-chevron-up' : 'fa-chevron-down'}`} aria-hidden="true" /> {titulo}
      </button>
      {abierto && <div className="space-y-4">{children}</div>}
    </div>
  )
}
