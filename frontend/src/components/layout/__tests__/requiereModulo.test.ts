import { describe, it, expect } from 'vitest'
import { moduloPermiteRuta } from '../RequireRole'

describe('moduloPermiteRuta', () => {
  it('la cajera de una tienda sin Clientes no entra a /customers (Kaory, 2026-11-27)', () => {
    expect(moduloPermiteRuta('CAJERO', 'crm', ['core', 'pos'])).toBe(false)
    expect(moduloPermiteRuta('VENDEDOR', 'crm', ['core', 'pos'])).toBe(false)
    expect(moduloPermiteRuta('GERENTE', 'labels', ['core', 'pos'])).toBe(false)
  })
  it('con el módulo encendido entra', () => {
    expect(moduloPermiteRuta('CAJERO', 'crm', ['core', 'crm'])).toBe(true)
  })
  it('administrador y dueño pasan siempre, como en require_module', () => {
    expect(moduloPermiteRuta('ADMINISTRADOR', 'crm', ['core'])).toBe(true)
    expect(moduloPermiteRuta('DUEÑO', 'crm', ['core'])).toBe(true)
  })
  it('sin módulos cargados no decide (fail-open)', () => {
    expect(moduloPermiteRuta('CAJERO', 'crm', [])).toBe(true)
  })
})
