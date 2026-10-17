// @vitest-environment jsdom
import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { render, screen, cleanup, fireEvent, waitFor, within } from '@testing-library/react'

const api = {
  getDepartments: vi.fn(async () => []),
  getBrands: vi.fn(async () => []),
  getById: vi.fn(),
  create: vi.fn(),
  update: vi.fn(),
  updateVariant: vi.fn(),
  skuSuggest: vi.fn(),
}
vi.mock('../../../api/products', () => ({ productsApi: api }))
vi.mock('../../../api/organization', () => ({
  organizationApi: { getBranches: vi.fn(async () => [{ id: 20, name: 'Roma', branch_type: 'STORE', is_headquarters: false }]) },
}))
vi.mock('../../../store/toastStore', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

const { FormularioProducto } = await import('../FormularioProducto')
const { useAuthStore } = await import('../../../store/authStore')
const { useEnabledModulesStore } = await import('../../../store/enabledModulesStore')

const admin = { id: 1, username: 'admin', role: 'ADMINISTRADOR', branch_id: null, branch_name: null }
const cajera = { id: 2, username: 'caja', role: 'CAJERO', branch_id: 20, branch_name: 'Roma' }

const producto = {
  id: 'p1', name: 'Tenis', sku: 'NK-TENIS-NEG-40', price: 4000, cost: 1500, unit: 'pza', is_active: true,
  gender: 'MUJER',
  variants: [
    { id: 'v1', sku: 'NK-TENIS-NEG-40', color: 'Negro', size: '40', price: 4000, cost: 1500, barcode: '111' },
    { id: 'v2', sku: 'NK-TENIS-NEG-41', color: 'Negro', size: '41', price: 4000, cost: 1500, barcode: '222' },
  ],
  prices: [],
  packaging_units: [{ id: 'pk1', name: 'Caja', barcode: null, units_per_package: 12, package_price: 40000 }],
}

beforeEach(() => {
  vi.clearAllMocks()
  useAuthStore.setState({ user: admin } as never)
  useEnabledModulesStore.setState({ enabledModules: ['core'], loaded: true, camposProducto: { visibles: [], ocultos: [] } } as never)
})
afterEach(cleanup)

const escribir = (etiqueta: RegExp | string, valor: string) =>
  fireEvent.change(screen.getByLabelText(etiqueta), { target: { value: valor } })

describe('FormularioProducto', () => {
  it('alta de admin: manda el payload único con la sucursal marcada', async () => {
    api.create.mockResolvedValue({ ...producto, id: 'nuevo' })
    const onDone = vi.fn()
    render(<MemoryRouter><FormularioProducto mode="create" presentacion="pagina" onDone={onDone} onCancel={() => {}} /></MemoryRouter>)
    await screen.findByText('Crear producto')
    escribir(/^Nombre/, 'Tenis'); escribir(/^SKU/, 'nk-tenis'); escribir(/^Precio/, '4000'); escribir(/^Costo/, '1500')
    fireEvent.click(within(screen.getByText('Roma').closest('tr') as HTMLElement).getAllByRole('checkbox')[0])
    fireEvent.click(screen.getByText('Crear producto'))
    await waitFor(() => expect(api.create).toHaveBeenCalled())
    const payload = api.create.mock.calls[0][0]
    expect(payload.sku).toBe('NK-TENIS')
    expect(payload.target_branch_ids).toEqual([20])
    expect(payload.color).toBeUndefined()
    expect(onDone).toHaveBeenCalledWith(expect.objectContaining({ id: 'nuevo' }))
  })

  it('precio 0 no se manda', async () => {
    render(<MemoryRouter><FormularioProducto mode="create" presentacion="pagina" onDone={() => {}} onCancel={() => {}} /></MemoryRouter>)
    await screen.findByText('Crear producto')
    escribir(/^Nombre/, 'Tenis'); escribir(/^SKU/, 'X'); escribir(/^Precio/, '0'); escribir(/^Costo/, '0')
    fireEvent.click(screen.getByText('Crear producto'))
    expect(await screen.findByText('Precio mayor a 0')).toBeTruthy()
    expect(api.create).not.toHaveBeenCalled()
  })

  it('cajera: la sucursal es la suya y no hay matriz de sucursales', async () => {
    useAuthStore.setState({ user: cajera } as never)
    api.create.mockResolvedValue({ ...producto, id: 'nuevo' })
    render(<MemoryRouter><FormularioProducto mode="create" presentacion="modal" onDone={() => {}} onCancel={() => {}} /></MemoryRouter>)
    await screen.findByText('Crear producto')
    expect(screen.queryByText('Activación por sucursal')).toBeNull()
    escribir(/^Nombre/, 'Tenis'); escribir(/^SKU/, 'X'); escribir(/^Precio/, '10'); escribir(/^Costo/, '1')
    escribir(/Stock inicial/, '2')
    fireEvent.click(screen.getByText('Crear producto'))
    await waitFor(() => expect(api.create).toHaveBeenCalled())
    const payload = api.create.mock.calls[0][0]
    expect(payload.branch_id).toBe(20)
    expect(payload.target_branch_ids).toBeUndefined()
  })

  it('edición: conserva los empaques cargados y muestra la ficha aunque el giro la oculte', async () => {
    useEnabledModulesStore.setState({ enabledModules: ['core', 'variants'], loaded: true,
      camposProducto: { visibles: [], ocultos: ['gender', 'model', 'material'] } } as never)
    api.getById.mockResolvedValue(producto)
    api.update.mockResolvedValue(producto)
    render(<MemoryRouter><FormularioProducto mode="edit" productId="p1" presentacion="pagina" onDone={() => {}} onCancel={() => {}} /></MemoryRouter>)
    await screen.findByText('Guardar cambios')
    expect(screen.getByText('Género')).toBeTruthy()      // trae MUJER: nada se apaga
    expect(screen.queryByText('Modelo')).toBeNull()      // vacío y oculto por el giro
    fireEvent.click(screen.getByText('Guardar cambios'))
    await waitFor(() => expect(api.update).toHaveBeenCalled())
    const [id, patch] = api.update.mock.calls[0]
    expect(id).toBe('p1')
    expect(patch.packaging_units).toEqual([{ name: 'Caja', barcode: null, units_per_package: 12, package_price: 40000 }])
    expect(patch.sku).toBe('NK-TENIS-NEG-40')
    expect(patch.gender).toBe('MUJER')
    expect(patch.precio_a_todas_las_tallas).toBe(true)
    expect(api.updateVariant).not.toHaveBeenCalled()
  })

  it('edición de una talla no principal: el SKU va a la talla', async () => {
    useEnabledModulesStore.setState({ enabledModules: ['core', 'variants'], loaded: true, camposProducto: { visibles: [], ocultos: [] } } as never)
    api.getById.mockResolvedValue(producto)
    api.update.mockResolvedValue(producto)
    api.updateVariant.mockResolvedValue(producto)
    render(<MemoryRouter><FormularioProducto mode="edit" productId="p1" variantId="v2" presentacion="modal" onDone={() => {}} onCancel={() => {}} /></MemoryRouter>)
    await screen.findByText('Guardar cambios')
    expect((screen.getByLabelText(/^SKU/) as HTMLInputElement).value).toBe('NK-TENIS-NEG-41')
    escribir(/^SKU/, 'NK-TENIS-NEG-41B')
    fireEvent.click(screen.getByText('Guardar cambios'))
    await waitFor(() => expect(api.updateVariant).toHaveBeenCalledWith('v2', { sku: 'NK-TENIS-NEG-41B' }))
    expect(api.update.mock.calls[0][1].sku).toBeUndefined()
    expect(api.update.mock.calls[0][1].precio_a_todas_las_tallas).toBe(false)
  })

  // Sin módulo variants no hay casilla visible: se manda false (no se aplanan precios).
  it('sin módulo variants no se aplanan precios', async () => {
    api.getById.mockResolvedValue(producto)
    api.update.mockResolvedValue(producto)
    render(<MemoryRouter><FormularioProducto mode="edit" productId="p1" presentacion="pagina" onDone={() => {}} onCancel={() => {}} /></MemoryRouter>)
    await screen.findByText('Guardar cambios')
    fireEvent.click(screen.getByText('Guardar cambios'))
    await waitFor(() => expect(api.update).toHaveBeenCalled())
    expect(api.update.mock.calls[0][1].precio_a_todas_las_tallas).toBe(false)
  })

  it('si el producto no carga, avisa y cancela', async () => {
    api.getById.mockRejectedValue(new Error('404'))
    const onCancel = vi.fn()
    render(<MemoryRouter><FormularioProducto mode="edit" productId="nada" presentacion="modal" onDone={() => {}} onCancel={onCancel} /></MemoryRouter>)
    await waitFor(() => expect(onCancel).toHaveBeenCalled())
  })
})
