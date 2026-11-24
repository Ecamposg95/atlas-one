import { describe, it, expect } from 'vitest'

import { agenteVisible, CLAVE_PREVIA, previaDelAgente, ROLES_CON_AGENTE } from '../agenteVisible'
import { NO_DISPONIBLES } from '../estadoModulos'

const base = { role: 'CAJERO', enabledModules: ['pos', 'ai'], noDisponibles: {}, previa: false }

describe('agenteVisible: quién ve el botón del agente', () => {
  it('hoy NO se ve: `ai` está en construcción (misma regla que el menú)', () => {
    expect(NO_DISPONIBLES.ai).toBe('en_construccion')
    for (const role of ROLES_CON_AGENTE) {
      expect(agenteVisible({ ...base, role, noDisponibles: NO_DISPONIBLES }), role).toBe(false)
    }
  })

  it('la vista previa lo enseña aunque siga en construcción', () => {
    expect(agenteVisible({ ...base, noDisponibles: NO_DISPONIBLES, previa: true })).toBe(true)
  })

  it('cuando `ai` se destape, lo ven los cinco roles con el módulo encendido', () => {
    for (const role of ['CAJERO', 'VENDEDOR', 'GERENTE', 'ADMINISTRADOR', 'DUEÑO']) {
      expect(agenteVisible({ ...base, role }), role).toBe(true)
    }
  })

  it('sin el módulo `ai` encendido no se ve, ni en vista previa', () => {
    expect(agenteVisible({ ...base, enabledModules: ['pos'] })).toBe(false)
    expect(agenteVisible({ ...base, enabledModules: ['pos'], previa: true })).toBe(false)
  })

  it('roles sin agente (y sesión sin rol) no lo ven, ni en vista previa', () => {
    for (const role of ['SOPORTE_OPERATIVO', 'CLIENTE', 'SUPERADMIN', '', null, undefined]) {
      expect(agenteVisible({ ...base, role, previa: true }), String(role)).toBe(false)
    }
  })
})

describe('previaDelAgente: cómo se enciende la vista previa', () => {
  const almacen = (valor: string | null) => ({ getItem: (k: string) => (k === CLAVE_PREVIA ? valor : null) })

  it('apagada por omisión', () => {
    expect(previaDelAgente({ DEV: true }, almacen(null))).toBe(false)
    expect(previaDelAgente({ DEV: false }, almacen(null))).toBe(false)
  })

  it('VITE_AGENTE_PREVIA=1 la enciende en cualquier build', () => {
    expect(previaDelAgente({ DEV: false, VITE_AGENTE_PREVIA: '1' }, null)).toBe(true)
    expect(previaDelAgente({ DEV: false, VITE_AGENTE_PREVIA: '0' }, null)).toBe(false)
  })

  it('localStorage solo cuenta en desarrollo: en producción no hay forma de encenderla a mano', () => {
    expect(previaDelAgente({ DEV: true }, almacen('1'))).toBe(true)
    expect(previaDelAgente({ DEV: false }, almacen('1'))).toBe(false)
  })

  it('un almacén que truena (modo privado) no rompe la pantalla', () => {
    expect(previaDelAgente({ DEV: true }, { getItem: () => { throw new Error('bloqueado') } })).toBe(false)
  })
})
