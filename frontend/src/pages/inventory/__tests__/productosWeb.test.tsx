// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react'

const prods = [1, 2, 3].map((n) => ({
  id: `p-${n}`, sku: `S${n}`, name: `Prod ${n}`, price: 10, stock: 1, is_active: true,
  department: null, department_name: null, brand_id: null, brand_name: null, description: null,
  cost: 1, image_url: null, web_published: n === 1, variants: [], branch_statuses: [],
}))
const api = vi.hoisted(() => ({
  list: vi.fn(),
  getDepartments: vi.fn(async () => [{ id: 'd-1', name: 'Ropa' }]),
  getBrands: vi.fn(async () => [{ id: 'b-1', name: 'Nike', logo_url: null }]),
  barcodesMissingCount: vi.fn(async () => 0),
  catalogKpis: vi.fn(async () => null),
  webPublish: vi.fn(async () => ({ processed: 2 })),
}))
vi.mock('../../../api/products', () => ({ productsApi: api }))
vi.mock('../../../api/inventory', () => ({ inventoryApi: {} }))
vi.mock('../../../api/organization', () => ({ organizationApi: { getBranches: vi.fn(async () => []) } }))
vi.mock('../../../components/ui/ConfirmDialog', () => ({ confirm: vi.fn(async () => true) }))

import { Products } from '../Products'
import { confirm } from '../../../components/ui/ConfirmDialog'
import { useAuthStore } from '../../../store/authStore'
import { useEnabledModulesStore } from '../../../store/enabledModulesStore'
import { useBranchCountStore } from '../../../store/branchCountStore'

const admin = { id: 1, username: 'admin', role: 'ADMINISTRADOR', branch_id: null, branch_name: null }
const pintar = () => render(<MemoryRouter><Products /></MemoryRouter>)

beforeEach(() => {
  vi.clearAllMocks()
  api.list.mockResolvedValue({ items: prods, total: 3 })
  useBranchCountStore.setState({ count: 1 })
  useAuthStore.setState({ user: admin } as never)
})
afterEach(cleanup)

describe('Productos y tienda web', () => {
  it('sin módulo: no hay columna Web ni casillas', async () => {
    useEnabledModulesStore.setState({ loaded: true, perfilUi: 'completo', enabledModules: [] } as never)
    pintar()
    await screen.findByText('Prod 1')
    expect(screen.queryByText('Web')).toBeNull()
    expect(screen.queryByLabelText(/Seleccionar Prod/)).toBeNull()
  })

  it('con módulo y admin: seleccionar 2 filas publica esos ids', async () => {
    useEnabledModulesStore.setState({ loaded: true, perfilUi: 'completo', enabledModules: ['tienda_en_linea'] } as never)
    pintar()
    await screen.findByText('Prod 1')
    expect(screen.getByText('Web')).toBeTruthy()
    fireEvent.click(screen.getByLabelText('Seleccionar Prod 1'))
    fireEvent.click(screen.getByLabelText('Seleccionar Prod 3'))
    fireEvent.click(screen.getByText('Publicar en tienda web (2)'))
    await waitFor(() => expect(api.webPublish).toHaveBeenCalledWith({ ids: ['p-1', 'p-3'], published: true }))
  })

  it('«Publicar todo lo filtrado» manda el filtro activo y confirma con el total', async () => {
    useEnabledModulesStore.setState({ loaded: true, perfilUi: 'completo', enabledModules: ['tienda_en_linea'] } as never)
    pintar()
    await screen.findByText('Prod 1')
    fireEvent.change(screen.getByPlaceholderText('Buscar por nombre o SKU...'), { target: { value: 'nik' } })
    fireEvent.change(screen.getByLabelText('Marca'), { target: { value: 'b-1' } })
    fireEvent.click(screen.getByText('Publicar todo lo filtrado'))
    await waitFor(() => expect(api.webPublish).toHaveBeenCalledWith({
      filtro: { search: 'nik', brand_id: 'b-1' }, published: true,
    }))
    const arg = (confirm as unknown as ReturnType<typeof vi.fn>).mock.calls[0][0]
    expect(JSON.stringify(arg)).toContain('3')
  })
})
