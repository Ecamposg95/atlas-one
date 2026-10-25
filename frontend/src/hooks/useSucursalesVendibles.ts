// frontend/src/hooks/useSucursalesVendibles.ts
import { useEffect, useState } from 'react'
import { organizationApi, type Branch } from '../api/organization'

/**
 * Sucursales activas que venden, para el selector de las pantallas fusionadas
 * (Ventas, Devoluciones). Misma regla que Inicio y Reportes: una bodega no es
 * "una tienda" para filtrar. Solo pide `/branches/` cuando `activo` (rol de
 * oficina); si la lista falla, no hay selector y la pantalla sigue.
 */
export function useSucursalesVendibles(activo: boolean): Branch[] {
  const [sucursales, setSucursales] = useState<Branch[]>([])
  useEffect(() => {
    if (!activo) return
    let vigente = true
    organizationApi.getBranches()
      .then((bs) => { if (vigente) setSucursales(bs.filter((b) => b.is_active !== false && b.can_sell !== false)) })
      .catch(() => { /* sin lista no hay selector */ })
    return () => { vigente = false }
  }, [activo])
  return sucursales
}
