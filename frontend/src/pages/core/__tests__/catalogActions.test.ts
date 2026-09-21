import { describe, it, expect } from 'vitest'
import { ACCIONES_CATALOGO, accionesDeProducto } from '../catalogActions'

describe('accionesDeProducto', () => {
  it('un producto aprobado y activo no ofrece aprobar ni rechazar', () => {
    const claves = accionesDeProducto({ approval_status: 'APPROVED', is_active: true })
    expect(claves).toEqual(['matriz', 'historial', 'editar', 'duplicar', 'archivar'])
  })

  it('un producto pendiente ofrece aprobar y rechazar, en ese orden', () => {
    const claves = accionesDeProducto({ approval_status: 'PENDING', is_active: true })
    expect(claves).toEqual(['matriz', 'aprobar', 'rechazar', 'historial', 'editar', 'duplicar', 'archivar'])
  })

  it('un producto archivado ofrece restaurar en lugar de archivar', () => {
    const claves = accionesDeProducto({ approval_status: 'REJECTED', is_active: false })
    expect(claves).toContain('restaurar')
    expect(claves).not.toContain('archivar')
  })

  it('sin estado de aprobación se comporta como aprobado', () => {
    expect(accionesDeProducto({ is_active: true })).not.toContain('aprobar')
  })

  it('toda clave devuelta tiene etiqueta e icono', () => {
    const todas = [
      ...accionesDeProducto({ approval_status: 'PENDING', is_active: true }),
      ...accionesDeProducto({ approval_status: 'APPROVED', is_active: false }),
    ]
    for (const clave of todas) {
      expect(ACCIONES_CATALOGO[clave].etiqueta.length).toBeGreaterThan(0)
      expect(ACCIONES_CATALOGO[clave].icono).toMatch(/^fa-/)
    }
  })
})
