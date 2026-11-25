import { useCallback, useEffect, useState } from 'react'

/** Cómo se ve la pantalla de Productos: rejilla de tarjetas o la lista de siempre. */
export type VistaProductos = 'tarjetas' | 'lista'

/** Por omisión, tarjetas: para todos los roles. */
export const VISTA_POR_OMISION: VistaProductos = 'tarjetas'

/** La elección es de cada persona: en una caja compartida no se pisan entre sí. */
export function claveVista(userId: number | string | null | undefined): string {
  return `atlas:productos:vista:${userId ?? 'anonimo'}`
}

/** Lo guardado para ese usuario; cualquier otra cosa (o sin almacenamiento) es la omisión. */
export function leerVista(userId: number | string | null | undefined): VistaProductos {
  try {
    const v = localStorage.getItem(claveVista(userId))
    return v === 'lista' || v === 'tarjetas' ? v : VISTA_POR_OMISION
  } catch {
    return VISTA_POR_OMISION
  }
}

export function guardarVista(userId: number | string | null | undefined, vista: VistaProductos): void {
  try {
    localStorage.setItem(claveVista(userId), vista)
  } catch {
    /* sin almacenamiento (ventana privada, cuota): la elección vale solo esta visita */
  }
}

/** Vista elegida por el usuario y cómo cambiarla (se recuerda en este navegador). */
export function useVistaProductos(userId: number | string | null | undefined): [VistaProductos, (v: VistaProductos) => void] {
  const [vista, setVista] = useState<VistaProductos>(() => leerVista(userId))
  // Si cambia la sesión sin desmontar la pantalla, manda lo que eligió el nuevo usuario.
  useEffect(() => { setVista(leerVista(userId)) }, [userId])
  const elegir = useCallback((v: VistaProductos) => {
    setVista(v)
    guardarVista(userId, v)
  }, [userId])
  return [vista, elegir]
}
