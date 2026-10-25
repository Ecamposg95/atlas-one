// frontend/src/pages/inventory/__tests__/ProductsCatalogo.test.tsx
// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react'

const api = vi.hoisted(() => ({
  list: vi.fn(),
  getDepartments: vi.fn(async () => []),
  getBrands: vi.fn(async () => [{ id: 'b1', name: 'Kaws', logo_url: null }]),
  barcodesMissingCount: vi.fn(async () => 0),
  catalogKpis: vi.fn(),
  approve: vi.fn(async () => ({ status: 'approved', product_id: 'p1' })),
  reject: vi.fn(async () => ({ status: 'rejected', product_id: 'p1' })),
  duplicate: vi.fn(),
  archive: vi.fn(async () => undefined),
  restore: vi.fn(async () => ({ status: 'ok', product_id: 'p2', message: 'Restaurado' })),
  downloadTemplate: vi.fn(async () => undefined),
}))
vi.mock('../../../api/products', () => ({ productsApi: api }))
vi.mock('../../../components/branch/ProductsBranchView', () => ({ ProductsBranchView: () => <div data-testid="vista-sucursal" /> }))
vi.mock('../../../components/catalog/CatalogKpis', () => ({
  CatalogKpis: ({ data }: { data: unknown }) => <div data-testid="kpis-catalogo" data-cargado={data ? '1' : '0'} />,
}))
vi.mock('../../../components/catalog/ProductBranchMatrix', () => ({ ProductBranchMatrix: () => <div data-testid="matriz" /> }))
vi.mock('../../../components/catalog/ProductAuditDrawer', () => ({ ProductAuditDrawer: () => <div data-testid="historial" /> }))
vi.mock('../../../components/ui/ConfirmDialog', () => ({ confirm: vi.fn(async () => true) }))
vi.mock('../../../components/products/FormularioProducto', () => ({ FormularioProducto: () => <div data-testid="formulario" /> }))

import { Products } from '../Products'
import { useAuthStore } from '../../../store/authStore'
import { useEnabledModulesStore } from '../../../store/enabledModulesStore'
import { useBranchCountStore } from '../../../store/branchCountStore'

const KPIS = { total_skus: 2, active_pos: 1, pending_approval: 1, no_branch: 0, critical_stock: 0, zero_stock: 0, threshold: 3 }
const producto = (id: string, name: string, extra: Record<string, unknown>) => ({
  id, sku: id.toUpperCase(), name, description: null, brand_id: null, brand_name: null, department: null, department_name: null,
  unit: null, cost: 10, price: 100, stock: 1, stock_total: 1, image_url: null, is_active: true, approval_status: 'APPROVED',
  variants: [], branch_statuses: [], ...extra,
})
const PENDIENTE = producto('p1', 'Blusa nueva', { approval_status: 'PENDING' })
const ARCHIVADO = producto('p2', 'Falda vieja', { is_active: false })
const admin = { id: 1, username: 'admin', role: 'ADMINISTRADOR', branch_id: null, platform_role: 'NONE' }
const perfil = (perfilUi: 'basico' | 'completo') => useEnabledModulesStore.setState({ loaded: true, perfilUi } as never)
const pintar = () => render(<MemoryRouter><Products /></MemoryRouter>)

beforeEach(() => {
  vi.clearAllMocks()
  api.list.mockResolvedValue({ items: [PENDIENTE, ARCHIVADO], total: 2, page: 0, pages: 1 })
  api.catalogKpis.mockResolvedValue(KPIS)
  useAuthStore.setState({ user: admin } as never)
  useBranchCountStore.setState({ count: 1 })
  perfil('completo')
})
afterEach(cleanup)

describe('Productos: catálogo fusionado (HQ en perfil completo)', () => {
  it('pinta las cifras, el filtro de aprobación, Incluir archivados y Exportar; la lista se pide con los filtros', async () => {
    pintar()
    await screen.findByText('Blusa nueva')
    expect(screen.getByTestId('kpis-catalogo')).toBeTruthy()
    await waitFor(() => expect(api.catalogKpis).toHaveBeenCalled())
    expect(screen.getByRole('group', { name: 'Aprobación' })).toBeTruthy()
    expect(screen.getByLabelText('Exportar catálogo')).toBeTruthy()
    fireEvent.click(screen.getByLabelText('Incluir archivados'))
    await waitFor(() => expect(api.list).toHaveBeenLastCalledWith(expect.objectContaining({ include_inactive: true })))
    fireEvent.click(screen.getByRole('button', { name: 'Pendientes' }))
    await waitFor(() => expect(api.list).toHaveBeenLastCalledWith(expect.objectContaining({ approval_status: 'PENDING' })))
    fireEvent.change(screen.getByLabelText('Marca'), { target: { value: 'b1' } })
    await waitFor(() => expect(api.list).toHaveBeenLastCalledWith(expect.objectContaining({ brand_id: 'b1' })))
  })

  it('un pendiente ofrece Aprobar y Rechazar; un archivado, Restaurar; con una sola tienda no hay Matriz', async () => {
    pintar()
    await screen.findByText('Blusa nueva')
    expect(screen.getByText('Pendiente')).toBeTruthy()
    expect(screen.getByText('Archivado')).toBeTruthy()
    expect(screen.getAllByText('Sin sucursal')).toHaveLength(2)   // ambos productos tienen branch_statuses vacío
    expect(screen.getByLabelText('Aprobar — Blusa nueva')).toBeTruthy()
    expect(screen.getByLabelText('Rechazar — Blusa nueva')).toBeTruthy()
    expect(screen.getByLabelText('Restaurar — Falda vieja')).toBeTruthy()
    expect(screen.queryByLabelText('Archivar — Falda vieja')).toBeNull()
    expect(screen.queryByLabelText(/Matriz de sucursales/)).toBeNull()
    fireEvent.click(screen.getByLabelText('Aprobar — Blusa nueva'))
    await waitFor(() => expect(api.approve).toHaveBeenCalledWith('p1'))
    fireEvent.click(screen.getByLabelText('Archivar — Blusa nueva'))
    await waitFor(() => expect(api.archive).toHaveBeenCalledWith('p1'))
  })

  it('con varias sucursales aparece la Matriz de sucursales y abre su modal', async () => {
    useBranchCountStore.setState({ count: 2 })
    pintar()
    await screen.findByText('Blusa nueva')
    fireEvent.click(screen.getByLabelText('Matriz de sucursales — Blusa nueva'))
    expect(await screen.findByTestId('matriz')).toBeTruthy()
  })

  it('en básico la dueña no ve cifras, aprobación ni archivados, y no se consultan', async () => {
    perfil('basico')
    pintar()
    await screen.findByText('Blusa nueva')
    expect(screen.queryByTestId('kpis-catalogo')).toBeNull()
    expect(screen.queryByRole('group', { name: 'Aprobación' })).toBeNull()
    expect(screen.queryByLabelText('Incluir archivados')).toBeNull()
    expect(screen.queryByLabelText('Aprobar — Blusa nueva')).toBeNull()
    expect(screen.getAllByLabelText('Editar producto').length).toBe(2)   // una por fila: solo Editar
    expect(api.catalogKpis).not.toHaveBeenCalled()
    expect(api.getBrands).not.toHaveBeenCalled()
  })

  it('la gerente ve la vista de sucursal, sin acciones de catálogo', async () => {
    useAuthStore.setState({ user: { ...admin, role: 'GERENTE', branch_id: 20 } } as never)
    pintar()
    expect(await screen.findByTestId('vista-sucursal')).toBeTruthy()
    expect(api.catalogKpis).not.toHaveBeenCalled()
  })
})
