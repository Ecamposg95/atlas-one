import type { Cambio } from '../../../../api/cargas'
import { campo, valor } from '../formato'

/** Lo que cambió una respuesta: por grupo, campo antes → después; con Deshacer si el servidor lo permite. */
export function CambiosAntesDespues({ cambio, ocupado, onDeshacer }: {
  cambio: Cambio
  ocupado: boolean
  onDeshacer: (cambioId: string) => void
}) {
  const { resumen } = cambio
  const lista = (n: number[]) => n.join(', ')
  return (
    <div className={`dax-card p-3 space-y-2 ${cambio.deshecho ? 'opacity-60' : ''}`} data-cambio={cambio.id}>
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm font-semibold text-dax-text">
          {cambio.texto ? `“${cambio.texto}”` : `Cambio ${cambio.secuencia}`}
          {cambio.deshecho && <span className="text-xs text-dax-muted"> · Deshecho</span>}
        </p>
        {cambio.puede_deshacer && !cambio.deshecho && (
          <button type="button" disabled={ocupado} onClick={() => onDeshacer(cambio.id)}
            className="dax-btn-ghost text-sm max-md:min-h-[44px] disabled:opacity-40">Deshacer</button>
        )}
      </div>
      {resumen.grupos.map((g) => (
        <div key={g.grupo} className="text-xs">
          <p className="font-bold text-dax-text">{g.titulo}</p>
          <ul className="mt-0.5 space-y-0.5">
            {Object.entries(g.cambios).map(([k, c]) => (
              <li key={k} className="text-dax-muted">
                {campo(k)}: {valor(c.antes)} → <span className="text-dax-text">{valor(c.despues)}</span>
              </li>
            ))}
          </ul>
        </div>
      ))}
      {resumen.dudas_resueltas.length > 0 && (
        <p className="text-xs text-dax-muted">Preguntas resueltas: {lista(resumen.dudas_resueltas)}</p>
      )}
      {resumen.dudas_nuevas.length > 0 && (
        <p className="text-xs text-dax-muted">Preguntas nuevas: {lista(resumen.dudas_nuevas)}</p>
      )}
    </div>
  )
}
