// @vitest-environment jsdom
import { describe, it, expect, afterEach, beforeEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import { PresetHome } from '../PresetHome'
import { useAuthStore } from '../../../store/authStore'
import { useEnabledModulesStore } from '../../../store/enabledModulesStore'
import type { Organization, User } from '../../../types/auth'

const ana = {
  id: 1, username: 'ana', email: null, full_name: 'Ana López', role: 'ADMINISTRADOR',
  platform_role: 'NONE', branch_id: null, organization_id: 1, is_active: true,
} as User
const tienda = { id: 1, name: 'Tienda Demo', industry_type: 'ATLAS_ONE_RETAIL', hq_branch_id: null } as Organization
const FREE = { clave: 'FREE', nombre: 'ONE FREE' }
const ULTRA = { clave: 'ULTRA_PLUS', nombre: 'ULTRA+' }

function pintar(plan: typeof FREE | null, enabledModules: string[]) {
  useEnabledModulesStore.setState({ loaded: true, loading: false, preset: 'ATLAS_ONE_RETAIL', enabledModules, plan, capacidades: [] })
  return render(<MemoryRouter><PresetHome /></MemoryRouter>)
}

beforeEach(() => {
  useAuthStore.setState({ user: ana, org: tienda, token: 't', isAuthenticated: true, hydrated: true })
})
afterEach(cleanup)

describe('PresetHome en FREE (retail)', () => {
  it('esconde los widgets de módulos no activos y los resume en una sola tarjeta', () => {
    pintar(FREE, ['core', 'pos', 'inventory', 'reports'])
    expect(screen.getByText('Inventario')).toBeTruthy()
    expect(screen.queryByText('Cotizaciones')).toBeNull()
    const tarjeta = screen.getByTestId('tarjeta-plan')
    expect(tarjeta.textContent).toContain('ONE FREE')
    expect(tarjeta.textContent).toContain('Cotizaciones')
    expect(screen.getAllByTestId('tarjeta-plan')).toHaveLength(1)
  })

  it('con todos los módulos activos no hay tarjeta de plan', () => {
    pintar(FREE, ['core', 'inventory', 'purchasing', 'promotions', 'quotes', 'reports'])
    expect(screen.queryByTestId('tarjeta-plan')).toBeNull()
    expect(screen.getByText('Cotizaciones')).toBeTruthy()
  })

  it('con todo fuera de plan queda la tarjeta sola, nunca una rejilla vacía', () => {
    pintar(FREE, ['core'])
    expect(screen.getByTestId('tarjeta-plan')).toBeTruthy()
    expect(screen.getByText('Sucursales')).toBeTruthy() // sin módulo: siempre
  })
})

describe('PresetHome fuera de FREE', () => {
  it('ULTRA+ ve todos los widgets y ninguna tarjeta', () => {
    pintar(ULTRA, ['core'])
    expect(screen.getByText('Cotizaciones')).toBeTruthy()
    expect(screen.queryByTestId('tarjeta-plan')).toBeNull()
  })
  it('sin plan cargado no se esconde nada', () => {
    pintar(null, ['core'])
    expect(screen.getByText('Compras')).toBeTruthy()
  })
})
