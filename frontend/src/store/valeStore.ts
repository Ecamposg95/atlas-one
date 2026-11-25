import { create } from 'zustand'

/**
 * Vale de tienda cargado en el cobro. Lo pone la devolución con «cambio de
 * producto» (o la caja al teclear un código) y lo consume la siguiente venta
 * del POS. Vive en memoria: si se recarga la página, el vale sigue existiendo
 * en el servidor y se vuelve a cargar por su código.
 */
export interface ValeEnCobro {
  code: string
  balance: number
}

interface ValeState {
  vale: ValeEnCobro | null
  usar: (vale: ValeEnCobro) => void
  quitar: () => void
}

export const useValeStore = create<ValeState>((set) => ({
  vale: null,
  usar: (vale) => set({ vale }),
  quitar: () => set({ vale: null }),
}))

const centavos = (n: number) => Math.round(n * 100) / 100

/** Cuánto del total cubre el vale y cuánto queda por cobrar por otro medio. */
export function repartoConVale(total: number, vale: ValeEnCobro | null): { aplica: number; porCobrar: number } {
  const aplica = vale ? centavos(Math.max(Math.min(vale.balance, total), 0)) : 0
  return { aplica, porCobrar: centavos(total - aplica) }
}
