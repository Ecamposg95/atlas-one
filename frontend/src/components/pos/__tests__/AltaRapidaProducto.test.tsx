// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react'

const api = vi.hoisted(() => ({
  getDepartments: vi.fn(async () => [{ id: 'd1', name: 'Blusas' }]),
  getBrands: vi.fn(async () => [{ id: 'b1', name: 'Nike' }]),
  create: vi.fn(),
}))
vi.mock('../../../api/products', () => ({ productsApi: api }))
vi.mock('../../../api/organization', () => ({ organizationApi: { getBranches: vi.fn(async () => []) } }))
vi.mock('../../../store/toastStore', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

const { default: AltaRapidaProducto } = await import('../AltaRapidaProducto')
const { useAuthStore } = await import('../../../store/authStore')
const { useEnabledModulesStore } = await import('../../../store/enabledModulesStore')

const cajera = { id: 2, username: 'caja', role: 'CAJERO', branch_id: 20, branch_name: 'Roma' }
const escribir = (etiqueta: RegExp, valor: string) =>
  fireEvent.change(screen.getByLabelText(etiqueta), { target: { value: valor } })

beforeEach(() => {
  vi.clearAllMocks()
  useAuthStore.setState({ user: cajera } as never)
  useEnabledModulesStore.setState({
    enabledModules: ['core', 'pos'], loaded: true, perfilUi: 'basico',
    camposProducto: { visibles: [], ocultos: ['gender', 'model', 'material', 'brand_id', 'description', 'unit', 'image_url', 'tax_rate', 'packaging_units', 'variants'] },
  } as never)
})
afterEach(cleanup)

describe('Alta rápida desde el POS en básico (Review Focus #5)', () => {
  it('formulario corto y ProductCreate válido con la sucursal de la cajera', async () => {
    api.create.mockResolvedValue({ id: 'nuevo', name: 'Blusa', sku: 'BLU', price: 120 })
    const onCreado = vi.fn()
    render(<MemoryRouter><AltaRapidaProducto onClose={() => {}} onCreado={onCreado} /></MemoryRouter>)
    await screen.findByText('Crear producto')
    expect(screen.getByText('Nuevo producto')).toBeTruthy()          // título del Modal
    for (const oculto of ['Marca', 'Unidad', 'Descripción', 'URL de imagen', 'Empaques / Cajas']) {
      expect(screen.queryByText(oculto)).toBeNull()
    }
    escribir(/^Nombre/, 'Blusa'); escribir(/^SKU/, 'blu'); escribir(/^Precio/, '120'); escribir(/^Costo/, '60')
    escribir(/Stock inicial/, '2')
    fireEvent.click(screen.getByText('Crear producto'))
    await waitFor(() => expect(onCreado).toHaveBeenCalled())
    const payload = api.create.mock.calls[0][0]
    expect(payload).toEqual(expect.objectContaining({ name: 'Blusa', sku: 'BLU', branch_id: 20, initial_stock: 2 }))
    expect(Number(payload.price)).toBe(120)
    expect(Number(payload.cost)).toBe(60)
    expect(payload.target_branch_ids).toBeUndefined()
    expect(payload.brand_id ?? null).toBeNull()
  })
})
