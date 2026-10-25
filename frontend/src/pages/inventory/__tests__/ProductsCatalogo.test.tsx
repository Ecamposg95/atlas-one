// frontend/src/pages/inventory/__tests__/ProductsCatalogo.test.tsx
// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { MemoryRouter, useNavigate } from 'react-router-dom'
import { render, screen, cleanup, fireEvent, waitFor, act } from '@testing-library/react'

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
  CatalogKpis: ({ data, loading }: { data: unknown; loading?: boolean }) =>
    <div data-testid="kpis-catalogo" data-cargado={data ? '1' : '0'} data-cargando={loading ? '1' : '0'} />,
}))
vi.mock('../../../components/catalog/ProductBranchMatrix', () => ({ ProductBranchMatrix: () => <div data-testid="matriz" /> }))
vi.mock('../../../components/catalog/ProductAuditDrawer', () => ({ ProductAuditDrawer: () => <div data-testid="historial" /> }))
vi.mock('../../../components/ui/ConfirmDialog', () => ({ confirm: vi.fn(async () => true) }))
vi.mock('../../../components/products/FormularioProducto', () => ({ FormularioProducto: () => <div data-testid="formulario" /> }))

import { Products } from '../Products'
import { useAuthStore } from '../../../store/authStore'
import { useEnabledModulesStore } from '../../../store/enabledModulesStore'
import { useBranchCountStore } from '../../../store/branchCountStore'
import { useToastStore } from '../../../store/toastStore'
import { confirm } from '../../../components/ui/ConfirmDialog'

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
// Un botón que navega: cambia `location.key` como al volver de /products/:id/edit.
function IrA() { const nav = useNavigate(); return <button type="button" onClick={() => nav('/products?vuelta=1')}>ir-a-otra-ruta</button> }
const mensajes = (tipo?: string) => useToastStore.getState().toasts.filter((t) => !tipo || t.type === tipo).map((t) => t.message)
const espera = (ms: number) => new Promise((r) => setTimeout(r, ms))

beforeEach(() => {
  vi.clearAllMocks()
  api.list.mockResolvedValue({ items: [PENDIENTE, ARCHIVADO], total: 2, page: 0, pages: 1 })
  api.catalogKpis.mockResolvedValue(KPIS)
  useToastStore.setState({ toasts: [] })
  vi.mocked(confirm).mockResolvedValue(true)
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

  it('un pendiente ofrece Aprobar y Rechazar; un archivado, Restaurar; la Matriz va siempre, también con una sola tienda', async () => {
    pintar()
    await screen.findByText('Blusa nueva')
    expect(screen.getByText('Pendiente')).toBeTruthy()
    expect(screen.getByText('Archivado')).toBeTruthy()
    expect(screen.getAllByText('Sin sucursal')).toHaveLength(2)   // ambos productos tienen branch_statuses vacío
    expect(screen.getByLabelText('Aprobar — Blusa nueva')).toBeTruthy()
    expect(screen.getByLabelText('Rechazar — Blusa nueva')).toBeTruthy()
    expect(screen.getByLabelText('Restaurar — Falda vieja')).toBeTruthy()
    expect(screen.queryByLabelText('Archivar — Falda vieja')).toBeNull()
    // Archivar apaga el producto en cada sucursal y restaurar no lo reenciende: la matriz es la vía.
    expect(screen.getByLabelText('Matriz de sucursales — Blusa nueva')).toBeTruthy()
    expect(screen.getByLabelText('Matriz de sucursales — Falda vieja')).toBeTruthy()
    fireEvent.click(screen.getByLabelText('Aprobar — Blusa nueva'))
    await waitFor(() => expect(api.approve).toHaveBeenCalledWith('p1'))
    fireEvent.click(screen.getByLabelText('Archivar — Blusa nueva'))
    await waitFor(() => expect(api.archive).toHaveBeenCalledWith('p1'))
  })

  it('restaurar muestra el mensaje del servidor y relee la lista', async () => {
    useToastStore.setState({ toasts: [] })
    pintar()
    await screen.findByText('Falda vieja')
    const antes = api.list.mock.calls.length
    fireEvent.click(screen.getByLabelText('Restaurar — Falda vieja'))
    await waitFor(() => expect(api.restore).toHaveBeenCalledWith('p2'))
    await waitFor(() => expect(useToastStore.getState().toasts.map((t) => t.message)).toContain('Restaurado'))
    await waitFor(() => expect(api.list.mock.calls.length).toBeGreaterThan(antes))
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

  it('hasta que el perfil carga HQ no pide nada (ni lista, ni marcas, ni cifras, ni contador); un básico nunca las pide', async () => {
    useEnabledModulesStore.setState({ loaded: false, perfilUi: 'completo' } as never)
    pintar()
    await espera(400)   // pasa el debounce de 300 ms
    expect(api.list).not.toHaveBeenCalled()
    expect(api.getBrands).not.toHaveBeenCalled()
    expect(api.catalogKpis).not.toHaveBeenCalled()
    expect(api.barcodesMissingCount).not.toHaveBeenCalled()
    expect(screen.queryByTestId('kpis-catalogo')).toBeNull()
    act(() => { useEnabledModulesStore.setState({ loaded: true, perfilUi: 'basico' } as never) })
    await screen.findByText('Blusa nueva')
    await espera(400)
    expect(api.list).toHaveBeenCalledTimes(1)
    expect(api.getBrands).not.toHaveBeenCalled()
    expect(api.catalogKpis).not.toHaveBeenCalled()
    expect(api.barcodesMissingCount).not.toHaveBeenCalled()
  })

  it('recarga dura (el perfil llega tarde): una sola petición de lista y de cifras, y las cifras salen en esqueleto, no en ceros', async () => {
    useEnabledModulesStore.setState({ loaded: false, perfilUi: 'completo' } as never)
    pintar()
    act(() => { useEnabledModulesStore.setState({ loaded: true, perfilUi: 'completo' } as never) })
    // Justo al llegar el perfil, antes de que salga la primera petición de cifras: esqueleto.
    expect(screen.getByTestId('kpis-catalogo').getAttribute('data-cargando')).toBe('1')
    await screen.findByText('Blusa nueva')
    await waitFor(() => expect(screen.getByTestId('kpis-catalogo').getAttribute('data-cargado')).toBe('1'))
    await espera(400)
    expect(api.list).toHaveBeenCalledTimes(1)
    expect(api.catalogKpis).toHaveBeenCalledTimes(1)
    expect(api.barcodesMissingCount).toHaveBeenCalledTimes(1)
    expect(screen.getByTestId('kpis-catalogo').getAttribute('data-cargando')).toBe('0')
  })

  it('al volver de otra ruta (location.key) se releen la lista Y las cifras', async () => {
    render(<MemoryRouter><Products /><IrA /></MemoryRouter>)
    await screen.findByText('Blusa nueva')
    await waitFor(() => expect(api.catalogKpis).toHaveBeenCalledTimes(1))
    const listas = api.list.mock.calls.length
    fireEvent.click(screen.getByText('ir-a-otra-ruta'))
    await waitFor(() => expect(api.list.mock.calls.length).toBe(listas + 1))
    await waitFor(() => expect(api.catalogKpis).toHaveBeenCalledTimes(2))
  })

  it('con el perfil completo ya cargado pide marcas y cifras una vez', async () => {
    pintar()
    await screen.findByText('Blusa nueva')
    await waitFor(() => expect(api.catalogKpis).toHaveBeenCalled())
    expect(api.getBrands).toHaveBeenCalledTimes(1)
    expect(api.catalogKpis).toHaveBeenCalledTimes(1)
  })

  describe('acciones del catálogo (argumentos, confirmación y errores)', () => {
    it('archivar pide confirmación de peligro y manda el id; si se cancela no hay llamada', async () => {
      pintar()
      await screen.findByText('Blusa nueva')
      vi.mocked(confirm).mockResolvedValueOnce(false)
      fireEvent.click(screen.getByLabelText('Archivar — Blusa nueva'))
      await waitFor(() => expect(confirm).toHaveBeenCalledTimes(1))
      expect(confirm).toHaveBeenCalledWith(expect.objectContaining({ title: 'Archivar producto', variant: 'danger', confirmText: 'Archivar' }))
      await espera(20)
      expect(api.archive).not.toHaveBeenCalled()
      fireEvent.click(screen.getByLabelText('Archivar — Blusa nueva'))
      await waitFor(() => expect(api.archive).toHaveBeenCalledWith('p1'))
      expect(confirm).toHaveBeenLastCalledWith(expect.objectContaining({ variant: 'danger' }))
      await waitFor(() => expect(mensajes('success')).toContain('Producto archivado.'))
    })

    it('rechazar confirma con peligro, manda el id y avisa; cancelar no llama', async () => {
      pintar()
      await screen.findByText('Blusa nueva')
      vi.mocked(confirm).mockResolvedValueOnce(false)
      fireEvent.click(screen.getByLabelText('Rechazar — Blusa nueva'))
      await waitFor(() => expect(confirm).toHaveBeenCalledTimes(1))
      await espera(20)
      expect(api.reject).not.toHaveBeenCalled()
      fireEvent.click(screen.getByLabelText('Rechazar — Blusa nueva'))
      await waitFor(() => expect(api.reject).toHaveBeenCalledWith('p1'))
      expect(confirm).toHaveBeenLastCalledWith(expect.objectContaining({ title: 'Rechazar producto', variant: 'danger' }))
      await waitFor(() => expect(mensajes('success')).toContain('Rechazado: Blusa nueva'))
    })

    it('duplicar confirma, manda el id y muestra el SKU de la copia; cancelar no llama', async () => {
      api.duplicate.mockResolvedValue({ sku: 'P1-COPIA' } as never)
      pintar()
      await screen.findByText('Blusa nueva')
      vi.mocked(confirm).mockResolvedValueOnce(false)
      fireEvent.click(screen.getByLabelText('Duplicar — Blusa nueva'))
      await waitFor(() => expect(confirm).toHaveBeenCalledTimes(1))
      await espera(20)
      expect(api.duplicate).not.toHaveBeenCalled()
      fireEvent.click(screen.getByLabelText('Duplicar — Blusa nueva'))
      await waitFor(() => expect(api.duplicate).toHaveBeenCalledWith('p1'))
      expect(confirm).toHaveBeenLastCalledWith(expect.objectContaining({ title: 'Duplicar producto', variant: 'info' }))
      await waitFor(() => expect(mensajes('success')).toContain('Copia creada: P1-COPIA'))
    })

    it.each([
      ['Aprobar', 'approve', 'Error al aprobar.'],
      ['Restaurar', 'restore', 'Error al restaurar.'],
    ] as const)('si %s falla muestra el detalle del servidor, o el respaldo, y no relee la lista', async (accion, metodo, respaldo) => {
      const producto = accion === 'Aprobar' ? 'Blusa nueva' : 'Falda vieja'
      api[metodo].mockReset().mockRejectedValueOnce({ response: { data: { detail: 'No tienes permiso' } } })
        .mockRejectedValueOnce(new Error('red'))
      pintar()
      await screen.findByText(producto)
      const listas = api.list.mock.calls.length
      fireEvent.click(screen.getByLabelText(`${accion} — ${producto}`))
      await waitFor(() => expect(mensajes('error')).toContain('No tienes permiso'))
      fireEvent.click(screen.getByLabelText(`${accion} — ${producto}`))
      await waitFor(() => expect(mensajes('error')).toContain(respaldo))
      expect(api.list.mock.calls.length).toBe(listas)
    })

    it('rechazar y duplicar: si fallan, el respaldo aparece y no se relee', async () => {
      api.reject.mockReset().mockRejectedValueOnce(new Error('red'))
      api.duplicate.mockReset().mockRejectedValueOnce(new Error('red'))
      pintar()
      await screen.findByText('Blusa nueva')
      fireEvent.click(screen.getByLabelText('Rechazar — Blusa nueva'))
      await waitFor(() => expect(mensajes('error')).toContain('Error al rechazar.'))
      fireEvent.click(screen.getByLabelText('Duplicar — Blusa nueva'))
      await waitFor(() => expect(mensajes('error')).toContain('Error al duplicar.'))
    })

    it('Exportar manda los filtros activos (y nada más); sin filtros, todo undefined', async () => {
      pintar()
      await screen.findByText('Blusa nueva')
      fireEvent.click(screen.getByLabelText('Exportar catálogo'))
      await waitFor(() => expect(api.downloadTemplate).toHaveBeenCalledTimes(1))
      expect(api.downloadTemplate).toHaveBeenLastCalledWith({
        search: undefined, department_id: undefined, brand_id: undefined, approval_status: undefined, include_inactive: undefined,
      })
      fireEvent.click(screen.getByLabelText('Incluir archivados'))
      fireEvent.click(screen.getByRole('button', { name: 'Pendientes' }))
      fireEvent.change(screen.getByLabelText('Marca'), { target: { value: 'b1' } })
      fireEvent.click(screen.getByLabelText('Exportar catálogo'))
      await waitFor(() => expect(api.downloadTemplate).toHaveBeenCalledTimes(2))
      expect(api.downloadTemplate).toHaveBeenLastCalledWith({
        search: undefined, department_id: undefined, brand_id: 'b1', approval_status: 'PENDING', include_inactive: true,
      })
      await waitFor(() => expect(mensajes('success')).toContain('Descarga iniciada.'))
    })

    it('si Exportar falla avisa con el detalle o con el respaldo', async () => {
      api.downloadTemplate.mockRejectedValueOnce({ response: { data: { detail: 'Sin permiso' } } } as never)
      pintar()
      await screen.findByText('Blusa nueva')
      fireEvent.click(screen.getByLabelText('Exportar catálogo'))
      await waitFor(() => expect(mensajes('error')).toContain('Sin permiso'))
    })
  })
})
