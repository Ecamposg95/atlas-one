import { create } from 'zustand'

import { organizationApi, type ExchangeRateInfo } from '../api/organization'

/**
 * Caché del tipo de cambio USD de la organización activa.
 *
 * Lo llena `GET /api/organization/exchange-rate` — endpoint propio y barato
 * porque quien lo consume es la cajera, que no es admin y no debe leer la
 * configuración fiscal completa solo para pintar un número.
 *
 * `rate === null` significa "no mostrar nada": es el estado de toda
 * organización que no configuró tipo de cambio (modo `off`) y también el de
 * una en modo `auto` que todavía no tiene FIX descargado. El POS no distingue
 * los dos casos, y ante un error de red se queda igual — sin equivalente y sin
 * mensaje de error.
 */
const REFRESCO_MS = 30 * 60 * 1000 // el FIX cambia una vez al día

interface ExchangeRateStore {
  rate: number | null
  info: ExchangeRateInfo | null
  loadedAt: number | null
  loading: boolean
  load: (force?: boolean) => Promise<void>
  reset: () => void
}

export const useExchangeRateStore = create<ExchangeRateStore>((set, get) => ({
  rate: null,
  info: null,
  loadedAt: null,
  loading: false,

  load: async (force = false) => {
    const { loading, loadedAt } = get()
    if (loading) return
    if (!force && loadedAt !== null && Date.now() - loadedAt < REFRESCO_MS) return
    set({ loading: true })
    try {
      const info = await organizationApi.getExchangeRate()
      const tasa = info?.rate == null ? NaN : Number(info.rate)
      set({
        rate: Number.isFinite(tasa) && tasa > 0 ? tasa : null,
        info: info ?? null,
        loadedAt: Date.now(),
        loading: false,
      })
    } catch {
      // Sin tipo de cambio simplemente no se muestra el equivalente. Nunca un
      // error en pantalla ni un cobro bloqueado.
      set({ rate: null, info: null, loadedAt: Date.now(), loading: false })
    }
  },

  reset: () => set({ rate: null, info: null, loadedAt: null, loading: false }),
}))
