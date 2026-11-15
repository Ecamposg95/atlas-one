import { useState } from 'react'

import type { Duda } from '../../../../api/cargas'

/** Una duda abierta, numerada: opciones como botones (la recomendada primero) y, si acepta texto, un input corto. */
export function TarjetaDuda({ duda, ocupado, onElegir }: {
  duda: Duda
  ocupado: boolean
  onElegir: (numero: number, opcion: string, valor?: string) => void
}) {
  const [texto, setTexto] = useState('')
  const opciones = [...duda.opciones].sort(
    (a, b) => Number(b.clave === duda.recomendada) - Number(a.clave === duda.recomendada),
  )
  return (
    <div className="dax-card p-3 space-y-2" data-duda={duda.numero}>
      <p className="text-sm text-dax-text"><span className="font-black">{duda.numero}.</span> {duda.texto}</p>
      <div className="flex flex-wrap gap-2">
        {opciones.map((o) => (
          <button key={o.clave} type="button" disabled={ocupado}
            onClick={() => onElegir(duda.numero, o.clave)}
            className={`${o.clave === duda.recomendada ? 'dax-btn-primary' : 'dax-btn-secondary'} text-sm max-md:min-h-[44px] disabled:opacity-40`}>
            {o.etiqueta}{o.clave === duda.recomendada && <span className="text-xs opacity-80"> · Recomendado</span>}
          </button>
        ))}
      </div>
      {duda.acepta_texto && (
        <form className="flex gap-2" onSubmit={(e) => {
          e.preventDefault()
          const v = texto.trim()
          if (!v) return
          onElegir(duda.numero, '', v)
          setTexto('')
        }}>
          <input className="dax-input flex-1 min-w-0 text-sm" aria-label={`Respuesta a la duda ${duda.numero}`}
            placeholder="O escribe tu respuesta" value={texto} onChange={(e) => setTexto(e.target.value)} />
          <button type="submit" disabled={ocupado || !texto.trim()}
            className="dax-btn-secondary text-sm max-md:min-h-[44px] disabled:opacity-40">Responder</button>
        </form>
      )}
    </div>
  )
}
