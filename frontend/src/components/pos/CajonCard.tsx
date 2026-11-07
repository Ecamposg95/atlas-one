import { useState } from 'react'
import { printerApi } from '../../api/printer'
import { toast } from '../../store/toastStore'
import { motivoSinCajon } from '../../utils/cajon'
import { DaxCard } from '../ui/DaxCard'

interface Props {
  /** La impresora a la que está conectado el cajón (RJ-11). */
  impresora: string | null
  /** `null` mientras se comprueba el agente. */
  agenteEnLinea: boolean | null
  /** `open_drawer_on_print` de la sucursal; `null` si todavía no se sabe. */
  abreAlCobrar: boolean | null
  /** Solo para quien administra la sucursal: sin él, el ajuste se muestra y no se edita. */
  onCambiarAbreAlCobrar?: (valor: boolean) => Promise<void>
}

/** Cajón de dinero: abrirlo ahora y, para quien administra, si abre solo al cobrar. */
export function CajonCard({ impresora, agenteEnLinea, abreAlCobrar, onCambiarAbreAlCobrar }: Props) {
  const [abriendo, setAbriendo] = useState(false)
  const [guardando, setGuardando] = useState(false)
  const motivo = motivoSinCajon(impresora, agenteEnLinea)

  const abrir = async () => {
    if (!impresora) return
    setAbriendo(true)
    try {
      await printerApi.abrirCajonManual(impresora)
      toast.success('Cajón abierto')
    } catch (e: unknown) {
      toast.error(`No se pudo abrir el cajón: ${(e as Error).message}`)
    } finally { setAbriendo(false) }
  }

  const cambiar = async (valor: boolean) => {
    if (!onCambiarAbreAlCobrar) return
    setGuardando(true)
    try { await onCambiarAbreAlCobrar(valor) } finally { setGuardando(false) }
  }

  return (
    <DaxCard>
      <div className="p-4 space-y-3">
        <h2 className="text-sm font-black" style={{ color: 'var(--dax-text)' }}>
          <i className="fa-solid fa-cash-register mr-2" aria-hidden="true" />Cajón de dinero
        </h2>
        {onCambiarAbreAlCobrar ? (
          <label className="flex items-start gap-3 cursor-pointer">
            <input
              type="checkbox"
              className="mt-0.5"
              checked={abreAlCobrar ?? false}
              disabled={abreAlCobrar === null || guardando}
              onChange={(e) => cambiar(e.target.checked)}
            />
            <span className="text-sm leading-tight" style={{ color: 'var(--dax-text)' }}>
              Abrir cajón al cobrar en efectivo
              <span className="block text-[11px] mt-0.5" style={{ color: 'var(--dax-text-muted)' }}>
                También al cerrar turno. El cajón debe estar conectado a la impresora.
              </span>
            </span>
          </label>
        ) : (
          <p className="text-xs" style={{ color: 'var(--dax-text-muted)' }}>
            {abreAlCobrar === false
              ? 'En esta sucursal no se abre solo al cobrar.'
              : 'Se abre solo al cobrar en efectivo y al cerrar turno.'}
          </p>
        )}
        <button
          type="button"
          onClick={abrir}
          disabled={abriendo || motivo !== null}
          className="dax-btn-secondary text-xs w-full min-h-[44px] disabled:opacity-40"
        >
          {abriendo
            ? <i className="fa-solid fa-spinner fa-spin" aria-hidden="true" />
            : <><i className="fa-solid fa-inbox" aria-hidden="true" /> Abrir cajón ahora</>}
        </button>
        {motivo && <p className="text-xs" style={{ color: 'var(--dax-text-muted)' }}>{motivo}</p>}
      </div>
    </DaxCard>
  )
}
