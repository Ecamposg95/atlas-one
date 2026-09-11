import client from './client'
import type { AttentionToday, OrgOverview } from '../types/platformOverview'

/** Tablero de plataforma (solo SUPERADMIN/SUPPORT).
 *  `date` = YYYY-MM-DD en hora del negocio; sin ella, hoy. */
export const platformOverviewApi = {
  /** El día de UNA organización, por sucursal. */
  orgOverview: async (orgId: number, date?: string): Promise<OrgOverview> => {
    const params = date ? { date } : undefined
    const { data } = await client.get<OrgOverview>(
      `/platform/organizations/${orgId}/overview`,
      { params },
    )
    return data
  },

  /** Los pendientes del día de TODAS las organizaciones. */
  attentionToday: async (date?: string): Promise<AttentionToday> => {
    const params = date ? { date } : undefined
    const { data } = await client.get<AttentionToday>('/platform/attention-today', { params })
    return data
  },
}
