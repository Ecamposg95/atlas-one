import { rutaInicioPorRol } from './rutaInicio'

/**
 * Pestañas de la barra inferior del armazón móvil. Vive fuera de
 * `MobileLayout.tsx` para poder probarse: vitest está configurado con
 * `include: ['src/**\/*.test.ts']`, solo .ts.
 */
export interface ItemNavMovil {
  label: string
  icon: string
  to: string
  end?: boolean
}

const PERFIL: ItemNavMovil = { label: 'Perfil', icon: 'fa-user', to: '/mobile/profile' }

/**
 * `modulos`: módulos habilitados de la organización, o `undefined` mientras
 * el store no ha cargado (misma regla que el cajón de escritorio: sin datos,
 * no se esconde nada). "Comanda" solo existe donde hay mesas (`tables`); una
 * boutique ve "Vender"/"Consultar" en su lugar.
 */
export function navMovilPorRol(rol?: string | null, preset?: string | null, modulos?: string[]): ItemNavMovil[] {
  const tieneMesas = modulos === undefined || modulos.includes('tables')
  const COMANDA: ItemNavMovil = { label: 'Comanda', icon: 'fa-utensils', to: '/mobile/comanda' }
  const CONSULTAR: ItemNavMovil = { label: 'Consultar', icon: 'fa-magnifying-glass', to: '/mobile/query' }
  switch (rol) {
    case 'VENDEDOR':
    case 'SOPORTE_OPERATIVO':
      return [
        { label: 'Inicio', icon: 'fa-house', to: '/mobile/dashboard' },
        { label: 'Cotizar', icon: 'fa-file-invoice', to: '/mobile/sales' },
        CONSULTAR,
        PERFIL,
      ]
    case 'CAJERO':
    case 'GERENTE':
      return [
        { label: 'Inicio', icon: 'fa-house', to: '/', end: true },
        tieneMesas ? COMANDA : { label: 'Vender', icon: 'fa-cash-register', to: '/pos' },
        CONSULTAR,
        PERFIL,
      ]
    case 'DUEÑO':
    case 'ADMINISTRADOR':
      // "Inicio" es el Inicio del dueño (SP6: cabe en teléfono y responde sus
      // preguntas; en presets ATLAS_ONE_* es /home). Abre el armazón de escritorio,
      // donde vive el cajón lateral, así que ya no hace falta una pestaña "Más"
      // con el mismo destino (dos pestañas iguales se marcaban activas a la vez).
      // /mobile/owner sigue existiendo por URL pero ya no es destino.
      return [
        { label: 'Inicio', icon: 'fa-house', to: rutaInicioPorRol(rol, false, preset) },
        tieneMesas ? COMANDA : CONSULTAR,
        PERFIL,
      ]
    case 'CLIENTE':
      return [{ label: 'Mi cuenta', icon: 'fa-id-card', to: '/portal' }]
    default:
      return [
        { label: 'Inicio', icon: 'fa-house', to: '/', end: true },
        PERFIL,
      ]
  }
}
