import client from './client'

export interface SucursalCanal { id: number; name: string; can_sell: boolean }
export interface ConfigCanal {
  activo: boolean
  /** null = todas las que venden. */
  sucursales_web: number[] | null
  sucursales: SucursalCanal[]
}

export const canalApi = {
  getConfig: async (): Promise<ConfigCanal> => {
    const { data } = await client.get<ConfigCanal>('/canal/config')
    return data
  },
  putConfig: async (sucursales_web: number[] | null): Promise<ConfigCanal> => {
    const { data } = await client.put<ConfigCanal>('/canal/config', { sucursales_web })
    return data
  },
}
