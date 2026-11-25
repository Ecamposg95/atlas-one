import { create } from 'zustand'

/**
 * Estado del panel del agente: un solo panel para toda la aplicación.
 * Cualquier pantalla lo abre con `abrirAgente('texto')` (Consultar manda lo
 * que la persona escribió en el buscador).
 */
interface AgenteStore {
  abierto: boolean
  /** Texto con el que abre la caja de mensaje. */
  borrador: string
  /** Conversación en curso; se conserva al cerrar el panel. */
  conversacionId: string | null
  abrir: (borrador?: string) => void
  cerrar: () => void
  fijarConversacion: (id: string | null) => void
  reset: () => void
}

export const useAgenteStore = create<AgenteStore>((set) => ({
  abierto: false,
  borrador: '',
  conversacionId: null,
  abrir: (borrador = '') => set({ abierto: true, borrador }),
  cerrar: () => set({ abierto: false, borrador: '' }),
  fijarConversacion: (conversacionId) => set({ conversacionId }),
  reset: () => set({ abierto: false, borrador: '', conversacionId: null }),
}))

export const abrirAgente = (borrador?: string): void => useAgenteStore.getState().abrir(borrador)
