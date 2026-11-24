import client from './client'

/**
 * Agente de Atlas ONE (`/api/ai/conversaciones`, fase A1: consultas por rol).
 * Lo que cada rol puede preguntar lo decide el servidor (`app/modules/ai/matriz.py`).
 */

/** Tabla pequeña que arma el servidor con el resultado de una consulta. */
export interface TablaAgente {
  titulo: string
  columnas: string[]
  filas: (string | number | boolean | null)[][]
  /** Filas que no cupieron. */
  mas: number
}

export interface MensajeAgente {
  id: string
  rol: 'user' | 'assistant'
  contenido: string | null
  tablas: TablaAgente[]
  created_at: string
}

export interface ConversacionAgente {
  id: string
  titulo: string | null
  created_at: string
  updated_at: string
}

export interface ConversacionDetalle extends ConversacionAgente {
  mensajes: MensajeAgente[]
}

export const aiApi = {
  crear: async (): Promise<ConversacionAgente> =>
    (await client.post<ConversacionAgente>('/ai/conversaciones', {})).data,
  listar: async (): Promise<ConversacionAgente[]> =>
    (await client.get<ConversacionAgente[]>('/ai/conversaciones')).data,
  leer: async (id: string): Promise<ConversacionDetalle> =>
    (await client.get<ConversacionDetalle>(`/ai/conversaciones/${id}`)).data,
  enviar: async (id: string, texto: string): Promise<MensajeAgente> =>
    (await client.post<{ mensaje: MensajeAgente }>(`/ai/conversaciones/${id}/mensajes`, { texto })).data.mensaje,
  borrar: async (id: string): Promise<void> => {
    await client.delete(`/ai/conversaciones/${id}`)
  },
}
