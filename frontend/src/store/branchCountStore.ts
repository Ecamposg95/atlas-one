import { create } from 'zustand'
import { organizationApi } from '../api/organization'

interface BranchCountStore {
  /** Sucursales de la organización. `null` = todavía no se sabe. */
  count: number | null
  loading: boolean
  load: () => Promise<void>
  reset: () => void
}

/**
 * Cuántas sucursales tiene la organización activa.
 *
 * Lo único que necesita la interfaz de este dato es saber si hay UNA sola: en
 * una tienda única, "HQ", "Global" y "Casa Matriz" nombran el mismo lugar que
 * "mi tienda", y esas etiquetas solo confunden a la dueña. Se consulta una vez
 * por sesión y falla en silencio (sin dato, se conservan los rótulos de
 * siempre, que es el comportamiento histórico).
 */
export const useBranchCountStore = create<BranchCountStore>((set, get) => ({
  count: null,
  loading: false,

  load: async () => {
    if (get().loading || get().count !== null) return
    set({ loading: true })
    try {
      const sucursales = await organizationApi.getBranches()
      set({ count: sucursales.length, loading: false })
    } catch {
      set({ count: null, loading: false })
    }
  },

  reset: () => set({ count: null, loading: false }),
}))

/** `true` solo cuando se sabe con certeza que la org tiene una sola sucursal. */
export function esTiendaUnica(count: number | null): boolean {
  return count === 1
}
