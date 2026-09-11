import { useCallback, useEffect, useRef, useState } from 'react'
import { platformOverviewApi } from '../../../api/platformOverview'
import type { AttentionToday, OrgOverview } from '../../../types/platformOverview'

export const REFRESH_MS = 120_000

function useVisibleInterval(enabled: boolean, refresh: () => void) {
  useEffect(() => {
    if (!enabled) return
    const id = window.setInterval(() => {
      if (document.visibilityState === 'visible') refresh()
    }, REFRESH_MS)
    const onVisible = () => { if (document.visibilityState === 'visible') refresh() }
    document.addEventListener('visibilitychange', onVisible)
    return () => { window.clearInterval(id); document.removeEventListener('visibilitychange', onVisible) }
  }, [enabled, refresh])
}

/** Carga el día de una organización; refresca cada 2 min solo con la pestaña
 *  visible; al fallar conserva el último dato. */
export function useOrgOverview(orgId: number | null) {
  const enabled = orgId !== null
  const [data, setData] = useState<OrgOverview | null>(null)
  const [loading, setLoading] = useState<boolean>(enabled)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdatedAt, setLastUpdatedAt] = useState<number | null>(null)
  const inFlight = useRef(false)
  const hasData = useRef(false)
  // Organización que el último llamador de `refresh` realmente quiere ver —
  // puede adelantarse a la petición en curso si el superadmin cambia de
  // cliente mientras esa petición todavía vuela.
  const requestedOrgId = useRef<number | null>(orgId)
  // Si `refresh` se pidió mientras había una petición en curso, se guarda
  // aquí para relanzarla en cuanto esa petición termine — en vez de perderla.
  const pendingRefresh = useRef(false)

  const refresh = useCallback(async () => {
    if (orgId === null) return
    requestedOrgId.current = orgId
    if (inFlight.current) { pendingRefresh.current = true; return }
    inFlight.current = true
    if (!hasData.current) setLoading(true)
    try {
      // Bucle, no recursión: si mientras esta respuesta viaja llega un cambio
      // de organización, se relanza aquí mismo con la más reciente — nunca
      // con la que tenía cerrada esta función al entrar.
      // eslint-disable-next-line no-constant-condition
      while (true) {
        const requestOrgId: number | null = requestedOrgId.current
        pendingRefresh.current = false
        if (requestOrgId === null) break
        try {
          const next = await platformOverviewApi.orgOverview(requestOrgId)
          // Una organización más nueva llegó mientras esta petición volaba: la
          // respuesta ya no corresponde a lo que el superadmin está viendo.
          if (requestedOrgId.current === requestOrgId) {
            setData(next)
            setLastUpdatedAt(Date.now())
            setError(null)
            hasData.current = true
          }
        } catch (e: any) {
          if (requestedOrgId.current === requestOrgId) {
            setError(e?.response?.data?.detail ?? e?.message ?? 'No se pudo cargar el tablero')
          }
        }
        if (!pendingRefresh.current) break
      }
    } finally {
      inFlight.current = false
      setLoading(false)
    }
  }, [orgId])

  useEffect(() => { void refresh() }, [refresh])
  useVisibleInterval(enabled, refresh)

  return { data, loading, error, lastUpdatedAt, refresh }
}

/** La tira "Atención hoy": cruza TODAS las organizaciones, así que se carga
 *  igual en modo Global que en modo Organización. */
export function useAttentionToday() {
  const [data, setData] = useState<AttentionToday | null>(null)
  const [error, setError] = useState<string | null>(null)
  const inFlight = useRef(false)

  const refresh = useCallback(async () => {
    if (inFlight.current) return
    inFlight.current = true
    try {
      setData(await platformOverviewApi.attentionToday())
      setError(null)
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? e?.message ?? 'No se pudo cargar Atención hoy')
    } finally {
      inFlight.current = false
    }
  }, [])

  useEffect(() => { void refresh() }, [refresh])
  useVisibleInterval(true, refresh)

  return { data, error, refresh }
}
