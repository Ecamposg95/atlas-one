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
const { organizationApi } = await import('../../../api/organization')

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
  useEnabledModulesStore.setState({ enabledModules: ['core'], loaded: true, perfilUi: 'completo', camposProducto: { visibles: [], ocultos: [] } } as never)
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
    fireEvent.change(screen.getAllByLabelText(/^Precio/)[0], { target: { value: '4500' } })   // la bandera solo viaja si el precio cambió
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
    expect(api.update.mock.calls[0][1].precio_a_todas_las_tallas).toBeUndefined()
  })

  it('talla no principal: el aviso nombra la talla y la principal', async () => {
    useEnabledModulesStore.setState({ enabledModules: ['core', 'variants'], loaded: true, camposProducto: { visibles: [], ocultos: [] } } as never)
    api.getById.mockResolvedValue(producto)
    render(<MemoryRouter><FormularioProducto mode="edit" productId="p1" variantId="v2" presentacion="modal" onDone={() => {}} onCancel={() => {}} /></MemoryRouter>)
    const aviso = await screen.findByText(/SKU y código de aquí son los de la talla Negro \/ 41/)
    expect(aviso.textContent).toContain('talla principal Negro / 40')
  })

  it('solo cambia el nombre: no manda la bandera de precio a todas las tallas', async () => {
    useEnabledModulesStore.setState({ enabledModules: ['core', 'variants'], loaded: true, camposProducto: { visibles: [], ocultos: [] } } as never)
    api.getById.mockResolvedValue(producto)
    api.update.mockResolvedValue(producto)
    render(<MemoryRouter><FormularioProducto mode="edit" productId="p1" presentacion="pagina" onDone={() => {}} onCancel={() => {}} /></MemoryRouter>)
    await screen.findByText('Guardar cambios')
    fireEvent.change(screen.getAllByLabelText(/^Nombre/)[0], { target: { value: 'Tenis Air' } })
    fireEvent.click(screen.getByText('Guardar cambios'))
    await waitFor(() => expect(api.update).toHaveBeenCalled())
    expect(api.update.mock.calls[0][1].precio_a_todas_las_tallas).toBeUndefined()
  })

  // Sin módulo variants no hay casilla visible: no se aplanan precios.
  it('sin módulo variants no se aplanan precios', async () => {
    api.getById.mockResolvedValue(producto)
    api.update.mockResolvedValue(producto)
    render(<MemoryRouter><FormularioProducto mode="edit" productId="p1" presentacion="pagina" onDone={() => {}} onCancel={() => {}} /></MemoryRouter>)
    await screen.findByText('Guardar cambios')
    fireEvent.click(screen.getByText('Guardar cambios'))
    await waitFor(() => expect(api.update).toHaveBeenCalled())
    expect(api.update.mock.calls[0][1].precio_a_todas_las_tallas).toBeUndefined()
  })

  it('si el producto no carga, avisa y cancela', async () => {
    api.getById.mockRejectedValue(new Error('404'))
    const onCancel = vi.fn()
    render(<MemoryRouter><FormularioProducto mode="edit" productId="nada" presentacion="modal" onDone={() => {}} onCancel={onCancel} /></MemoryRouter>)
    await waitFor(() => expect(onCancel).toHaveBeenCalled())
  })
})

// Lo que manda el servidor a una FREE (Tarea 2): ficha + OCULTOS_BASICO.
const OCULTOS_BASICO = ['gender', 'model', 'material', 'brand_id', 'description', 'unit', 'image_url', 'tax_rate', 'packaging_units', 'variants']
const enBasico = () => useEnabledModulesStore.setState({
  enabledModules: ['core', 'variants'], loaded: true, perfilUi: 'basico',
  camposProducto: { visibles: [], ocultos: OCULTOS_BASICO },
} as never)

describe('FormularioProducto en modo básico', () => {
  it('alta corta de la dueña con una sucursal: sin matriz, la sucursal va sola (Review Focus #3)', async () => {
    enBasico()
    api.create.mockResolvedValue({ ...producto, id: 'nuevo' })
    render(<MemoryRouter><FormularioProducto mode="create" presentacion="pagina" onDone={() => {}} onCancel={() => {}} /></MemoryRouter>)
    await screen.findByText('Crear producto')
    for (const oculto of ['Marca', 'Unidad', 'Descripción', 'URL de imagen', 'Tasa IVA (%)', 'Empaques / Cajas', 'Activación por sucursal']) {
      expect(screen.queryByText(oculto)).toBeNull()
    }
    expect(screen.getByText('Precio por cantidad')).toBeTruthy()
    expect(screen.getByText('Departamento')).toBeTruthy()
    escribir(/^Nombre/, 'Blusa'); escribir(/^SKU/, 'blu'); escribir(/^Precio/, '120'); escribir(/^Costo/, '60')
    escribir(/Stock inicial/, '3')
    fireEvent.click(screen.getByText('Crear producto'))
    await waitFor(() => expect(api.create).toHaveBeenCalled())
    const payload = api.create.mock.calls[0][0]
    expect(payload.target_branch_ids).toEqual([20])
    expect(payload.branch_id).toBe(20)
    expect(payload.initial_stock).toBe(3)
  })

  it('con dos sucursales la matriz sigue y nada se marca solo (Review Focus #3)', async () => {
    enBasico()
    vi.mocked(organizationApi.getBranches).mockResolvedValueOnce([
      { id: 20, name: 'Roma', branch_type: 'STORE', is_headquarters: false },
      { id: 21, name: 'Condesa', branch_type: 'STORE', is_headquarters: false },
    ] as never)
    render(<MemoryRouter><FormularioProducto mode="create" presentacion="pagina" onDone={() => {}} onCancel={() => {}} /></MemoryRouter>)
    await screen.findByText('Crear producto')
    expect(screen.getByText('Activación por sucursal')).toBeTruthy()
    escribir(/^Nombre/, 'Blusa'); escribir(/^SKU/, 'blu'); escribir(/^Precio/, '120'); escribir(/^Costo/, '60')
    fireEvent.click(screen.getByText('Crear producto'))
    expect(await screen.findByText('Activa al menos una sucursal')).toBeTruthy()
    expect(api.create).not.toHaveBeenCalled()
  })

  it('edición: un producto con marca y descripción las sigue mostrando (Review Focus #2)', async () => {
    enBasico()
    api.getBrands.mockResolvedValueOnce([{ id: 'b1', name: 'Nike' }] as never)
    api.getById.mockResolvedValue({
      ...producto, brand_id: 'b1', description: 'Algodón peinado',
      variants: [producto.variants[0]], packaging_units: [],
    })
    render(<MemoryRouter><FormularioProducto mode="edit" productId="p1" presentacion="pagina" onDone={() => {}} onCancel={() => {}} /></MemoryRouter>)
    await screen.findByText('Guardar cambios')
    expect(screen.getByText('Marca')).toBeTruthy()
    expect((screen.getByLabelText('Descripción') as HTMLTextAreaElement).value).toBe('Algodón peinado')
    expect(screen.queryByText('Unidad')).toBeNull()          // trae 'pza', el valor por defecto
    expect(screen.queryByText('Empaques / Cajas')).toBeNull() // sin empaques
  })

  it('edición: los empaques que ya existen se ven aunque básico los esconda', async () => {
    enBasico()
    api.getById.mockResolvedValue({ ...producto, variants: [producto.variants[0]] })
    render(<MemoryRouter><FormularioProducto mode="edit" productId="p1" presentacion="pagina" onDone={() => {}} onCancel={() => {}} /></MemoryRouter>)
    await screen.findByText('Guardar cambios')
    expect(screen.getByText('Empaques / Cajas')).toBeTruthy()
  })
})
