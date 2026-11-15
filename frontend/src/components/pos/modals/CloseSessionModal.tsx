import { useState } from 'react'
import { formatCurrency } from '../../../utils/currency'
import { closeVerdict } from '../../../theme/verdict'

/** Lo que el POS devuelve tras cerrar: la sesión cerrada (basta `difference`), o null si falló. */
export type ClosedSessionResult = { difference: string | number | null } | null

interface Props {
  onClose: () => void
  onConfirm: (closingAmount: number, notes: string) => Promise<ClosedSessionResult>
}

interface Resultado {
  counted: number
  /** contado − esperado, tal como lo calculó el backend; null si no vino. */
  diff: number | null
}

/**
 * Cierre de turno desde el POS — CONTEO CIEGO real.
 *
 * Paso captura: el cajero solo ve su campo de conteo; ni el esperado ni la
 * diferencia (ver utils/blindCash). Paso resultado: tras confirmar, el turno ya
 * está cerrado y se muestra Esperado / Contado / Diferencia con la `difference`
 * que devolvió el backend. Ya no se puede corregir el conteo hasta que cuadre.
 */
export function CloseSessionModal({ onClose, onConfirm }: Props) {
  const [closingAmount, setClosingAmount] = useState('')
  const [notes, setNotes] = useState('')
  const [loading, setLoading] = useState(false)
  const [resultado, setResultado] = useState<Resultado | null>(null)

  const closingNum = parseFloat(closingAmount) || 0

  const submit = async () => {
    setLoading(true)
    try {
      const closed = await onConfirm(closingNum, notes)
      // null = el cierre falló: el turno sigue abierto y el modal se queda en captura.
      if (closed) {
        const d = closed.difference != null ? Number(closed.difference) : NaN
        setResultado({ counted: closingNum, diff: Number.isFinite(d) ? d : null })
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 backdrop-blur-sm"
      style={{ background: 'var(--dax-modal-backdrop)' }}
      // Con el turno ya cerrado el fondo no cierra (solo "Listo"), y con el
      // cierre en vuelo tampoco: se perdería el resultado.
      onClick={resultado || loading ? undefined : onClose}
    >
      <div className="dax-card dax-modal p-6 pb-0 w-full max-w-sm" onClick={(e) => e.stopPropagation()}>
        {resultado ? (
          <ResultadoCierre resultado={resultado} onListo={onClose} />
        ) : (
          <>
            <div className="text-center mb-5">
              <div className="w-14 h-14 rounded-full bg-amber-500/20 flex items-center justify-center mx-auto mb-3">
                <i className="fa-solid fa-lock text-amber-400 text-2xl" />
              </div>
              <h3 className="text-xl font-black text-white">Cerrar Turno</h3>
              <p className="text-slate-500 text-xs mt-1">Cuenta el efectivo y registra lo que hay en caja</p>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1">
                  Efectivo real en caja
                </label>
                <input
                  type="number"
                  value={closingAmount}
                  onChange={(e) => setClosingAmount(e.target.value)}
                  className="dax-input text-xl font-black text-center tabular-nums"
                  placeholder="0.00"
                  inputMode="decimal"
                  min="0"
                  step="0.01"
                  autoFocus
                />
                <p className="text-[11px] text-slate-500 mt-1">
                  Conteo ciego · el esperado y la diferencia se muestran al cerrar
                </p>
              </div>

              <div>
                <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1">
                  Notas (opcional)
                </label>
                <input
                  type="text"
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  className="dax-input text-sm"
                  placeholder="Ej: Turno sin novedad..."
                />
              </div>

              <div className="dax-modal-footer flex gap-2 pb-6">
                <button onClick={onClose} disabled={loading} className="dax-btn-secondary flex-1 min-h-[44px]">Cancelar</button>
                <button
                  onClick={submit}
                  disabled={loading || !closingAmount}
                  className="flex-1 justify-center bg-amber-600 hover:bg-amber-500 text-white font-bold py-2 min-h-[44px] px-4 rounded-xl text-sm transition disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2"
                >
                  {loading
                    ? <i className="fa-solid fa-spinner fa-spin" />
                    : <><i className="fa-solid fa-lock" /> Cerrar Turno</>
                  }
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

function ResultadoCierre({ resultado, onListo }: { resultado: Resultado; onListo: () => void }) {
  const { counted, diff } = resultado
  // Veredicto del `difference` que ya calculó el backend; solo presentación.
  const verdict = diff != null ? closeVerdict(diff) : null
  const expected = diff != null ? counted - diff : null

  return (
    <div className="space-y-4">
      <div className="text-center">
        <h3 className="text-xl font-black text-white">Turno cerrado</h3>
      </div>

      {verdict && diff != null && (
        <div className={`anim-pop ${verdict.className} p-3 text-center text-sm font-bold`} role="status">
          {verdict.kind === 'ok'
            ? verdict.label
            : `${verdict.label}: ${formatCurrency(Math.abs(diff))}`}
        </div>
      )}

      <div className="space-y-2 text-sm">
        <div className="flex justify-between">
          <span className="text-slate-500">Esperado en caja</span>
          <span className="tabular-nums">{expected != null ? formatCurrency(expected) : '—'}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-slate-500">Contado</span>
          <span className="tabular-nums">{formatCurrency(counted)}</span>
        </div>
        <div className="flex justify-between font-bold border-t border-slate-700/50 pt-2">
          <span>Diferencia</span>
          <span className="tabular-nums">
            {diff != null ? `${diff > 0 ? '+' : ''}${formatCurrency(diff)}` : '—'}
          </span>
        </div>
      </div>

      <div className="dax-modal-footer flex gap-2 pb-6">
        <button onClick={onListo} className="dax-btn-primary flex-1 justify-center min-h-[44px]" autoFocus>
          Listo
        </button>
      </div>
    </div>
  )
}
