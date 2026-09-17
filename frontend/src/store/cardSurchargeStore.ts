import { create } from 'zustand'

import { organizationApi } from '../api/organization'
import { surchargeCacheOnError } from '../pages/pos/cardSurcharge'

/**
 * Caché del porcentaje de comisión por pago con tarjeta de la organización.
 *
 * Lo llena `GET /api/organization/card-surcharge` — endpoint propio y barato,
 * por el mismo motivo que el del tipo de cambio: quien lo consume es la cajera,
 * que no es admin y no debe leer la configuración fiscal completa para cobrar.
 *
 * `pct === 0` significa "no cobrar ni mostrar nada": es el estado de toda
 * organización que no la configuró. **Falla cerrado a propósito** mientras no
 * se haya podido cargar NUNCA: si el store no sabe cuánto es, el POS cobra
 * solo la mercancía y el backend responde 422 con el importe correcto en
 * español — preferible a inventar un cargo que el cliente no debe.
 *
 * Pero un error DESPUÉS de una carga buena conserva el último valor conocido
 * (`surchargeCacheOnError`): `getCardSurcharge` también lanza cuando se cae la
 * red, y borrar el porcentaje justo ahí dejaba al POS cobrando de menos en el
 * único momento en que además encola las ventas — que el backend rechazaba con
 * 422 al reconectar y la cola descartaba.
 */
const REFRESCO_MS = 30 * 60 * 1000 // configuración estática; no cambia sola

interface CardSurchargeStore {
  pct: number
  loadedAt: number | null
  loading: boolean
  load: (force?: boolean) => Promise<void>
  reset: () => void
}

export const useCardSurchargeStore = create<CardSurchargeStore>((set, get) => ({
  pct: 0,
  loadedAt: null,
  loading: false,

  load: async (force = false) => {
    const { loading, loadedAt } = get()
    if (loading) return
    if (!force && loadedAt !== null && Date.now() - loadedAt < REFRESCO_MS) return
    set({ loading: true })
    try {
      const info = await organizationApi.getCardSurcharge()
      const pct = Number(info?.pct)
      set({
        pct: Number.isFinite(pct) && pct > 0 ? pct : 0,
        loadedAt: Date.now(),
        loading: false,
      })
    } catch {
      const { pct, loadedAt: previo } = get()
      set({ ...surchargeCacheOnError({ pct, loadedAt: previo }, Date.now()), loading: false })
    }
  },

  reset: () => set({ pct: 0, loadedAt: null, loading: false }),
}))
