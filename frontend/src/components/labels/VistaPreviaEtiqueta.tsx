import { useState } from 'react'

import type { LabelPreview } from '../../api/labels'
import { EtiquetaSVG } from './EtiquetaSVG'

/**
 * Panel de vista previa: la etiqueta dibujada y, en la otra pestaña, el ZPL
 * crudo que se le manda a la Zebra.
 *
 * El ZPL no es adorno de programador: cuando una etiqueta sale mal en papel,
 * es lo único que se puede pegar en un correo para que alguien lo reproduzca.
 */

interface Props {
  preview: LabelPreview | null
  cargando: boolean
  error: string | null
  /** Qué variante se está viendo, para el encabezado. */
  titulo?: string
}

export function VistaPreviaEtiqueta({ preview, cargando, error, titulo }: Props) {
  const [pestana, setPestana] = useState<'etiqueta' | 'zpl'>('etiqueta')

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <h3 className="text-sm font-black text-white">Vista previa</h3>
          {titulo && <p className="text-[11px] text-slate-500 truncate">{titulo}</p>}
        </div>
        <div className="flex rounded-lg border border-slate-700/60 overflow-hidden shrink-0">
          {(['etiqueta', 'zpl'] as const).map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => setPestana(p)}
              className={`px-3 py-1 text-[11px] font-bold uppercase tracking-wider transition-colors ${
                pestana === p ? 'bg-slate-700 text-white' : 'text-slate-400 hover:text-white'
              }`}
            >
              {p === 'etiqueta' ? 'Etiqueta' : 'ZPL'}
            </button>
          ))}
        </div>
      </div>

      {cargando && (
        <div className="flex items-center gap-2 text-xs text-slate-400 py-8 justify-center">
          <i className="fa fa-spinner fa-spin" /> Armando la etiqueta…
        </div>
      )}

      {!cargando && error && (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-200">
          <i className="fa-solid fa-triangle-exclamation mr-2" />
          {error}
        </div>
      )}

      {!cargando && !error && !preview && (
        <p className="text-xs text-slate-500 py-8 text-center">
          Toca un renglón de la tabla para ver cómo queda su etiqueta.
        </p>
      )}

      {!cargando && !error && preview && (
        <>
          {preview.warning && (
            <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-2 text-[11px] text-amber-200">
              <i className="fa-solid fa-triangle-exclamation mr-1.5" />
              {preview.warning}
            </div>
          )}

          {pestana === 'etiqueta' ? (
            <div className="flex flex-col items-center gap-2">
              <EtiquetaSVG preview={preview} />
              <p className="text-[10px] text-slate-500">
                {preview.width} × {preview.height} dots · 51 × 25 mm a 203 dpi · {preview.kind}
              </p>
            </div>
          ) : (
            <pre className="max-h-80 overflow-auto rounded-lg border border-slate-700/50 bg-slate-950/60 p-3 text-[11px] leading-relaxed font-mono text-slate-300 whitespace-pre">
              {preview.zpl}
            </pre>
          )}
        </>
      )}
    </div>
  )
}
