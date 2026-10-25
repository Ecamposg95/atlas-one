// frontend/src/pages/inventory/conteos/__tests__/Conteos.test.tsx
// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { render, screen, cleanup, fireEvent } from '@testing-library/react'

const { listar, getBranches, getDepartments, navigate } = vi.hoisted(() => ({
  listar: vi.fn(), getBranches: vi.fn(), getDepartments: vi.fn(), navigate: vi.fn(),
}))
vi.mock('../../../../api/conteos', () => ({ conteosApi: { listar } }))
vi.mock('../../../../api/organization', () => ({ organizationApi: { getBranches } }))
vi.mock('../../../../api/products', () => ({ productsApi: { getDepartments } }))
vi.mock('react-router-dom', async (original) => ({
  ...(await original<typeof import('react-router-dom')>()),
  useNavigate: () => navigate,
}))

import { Conteos } from '../Conteos'
import { useAuthStore } from '../../../../store/authStore'

const avance = { esperadas_variantes: 4, esperadas_piezas: '10', contadas_variantes: 2, contadas_piezas: '5', desconocidos: 0 }
const conteo = (id: number, status: 'ABIERTO' | 'CERRADO' | 'CANCELADO', departamento: string) => ({
  id, branch_id: 1, branch_name: 'Roma', department_id: `d${id}`, department_name: departamento, status,
  notes: null, created_by: 'ana', created_at: '2026-10-24T10:00:00Z', closed_at: null, aplicado_at: null, aplicado_por: null, avance,
})
const CONTEOS = [conteo(1, 'ABIERTO', 'Playeras'), conteo(2, 'CERRADO', 'Tenis'), conteo(3, 'CANCELADO', 'Gorras')]

/** jsdom no trae matchMedia: `telefono` decide si `(max-width: 767px)` coincide (useEsTelefono). */
const anchoDePantalla = (telefono: boolean) => {
  window.matchMedia = ((query: string) => ({
    matches: telefono && query === '(max-width: 767px)', media: query, onchange: null,
    addEventListener: () => {}, removeEventListener: () => {}, addListener: () => {}, removeListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia
}
const pintar = () => render(<MemoryRouter><Conteos /></MemoryRouter>)

beforeEach(() => {
  useAuthStore.setState({ user: { id: 1, username: 'u', role: 'ADMINISTRADOR', branch_id: 1 } } as never)
  listar.mockReset().mockResolvedValue(CONTEOS)
  getBranches.mockReset().mockResolvedValue([])
  getDepartments.mockReset().mockResolvedValue([])
  navigate.mockReset()
})
afterEach(cleanup)

describe('Conteos (lista) con un conteo cancelado', () => {
  it('escritorio: pinta "Cancelado" en gris y tocarlo no navega; abierto y cerrado siguen igual', async () => {
    anchoDePantalla(false)
    pintar()
    const cancelado = await screen.findByText('Cancelado')
    expect(cancelado.className).toContain('text-dax-faint')
    expect(screen.getByText('Abierto').className).toContain('text-emerald-400')
    expect(screen.getByText('Cerrado').className).toContain('text-slate-400')

    const fila = cancelado.closest('tr')!
    expect(fila.className).not.toContain('cursor-pointer')
    // Sin avance: lo contado se descartó. Los demás siguen con su "x / y piezas · z%".
    expect(fila.textContent).toContain('—')
    expect(fila.textContent).not.toContain('piezas')
    expect(screen.getByText('Playeras').closest('tr')!.textContent).toContain('5 / 10 piezas · 50%')
    fireEvent.click(fila)
    fireEvent.click(screen.getByText('Gorras'))
    expect(navigate).not.toHaveBeenCalled()

    fireEvent.click(screen.getByText('Playeras'))
    expect(navigate).toHaveBeenLastCalledWith('/inventory/conteos/1')
    fireEvent.click(screen.getByText('Tenis'))
    expect(navigate).toHaveBeenLastCalledWith('/inventory/conteos/2/reporte')
    expect(navigate).toHaveBeenCalledTimes(2)
  })

  it('teléfono: la tarjeta del cancelado no es un botón y no navega', async () => {
    anchoDePantalla(true)
    pintar()
    const cancelado = await screen.findByText('Cancelado')
    expect(cancelado.closest('button')).toBeNull()
    fireEvent.click(screen.getByText('Gorras'))
    expect(navigate).not.toHaveBeenCalled()

    const tarjeta = cancelado.closest('article')!
    expect(tarjeta.textContent).toContain('—')
    expect(tarjeta.textContent).not.toContain('piezas')

    const abierto = screen.getByText('Abierto').closest('button')!
    expect(abierto.textContent).toContain('5 / 10 piezas · 50%')
    fireEvent.click(abierto)
    expect(navigate).toHaveBeenCalledWith('/inventory/conteos/1')
  })
})
