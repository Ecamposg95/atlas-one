// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react'

// Costo con una cifra inconfundible: si aparece en pantalla, la tarjeta lo filtró.
const BLUSA = {
  id: 'p-1', sku: 'BL-01', barcode: '7501234567890', name: 'Blusa lino', description: null, brand_id: null, brand_name: 'Kaws',
  department: null, department_name: 'Ropa', unit: null, cost: 987.65, price: 250, stock: 4, stock_total: 4,
  image_url: 'https://fotos.test/blusa.jpg', is_active: true, approval_status: 'APPROVED', variants: [], branch_statuses: [],
}
const FALDA = { ...BLUSA, id: 'p-2', sku: 'FA-02', barcode: null, name: 'Falda sin foto', cost: 432.1, price: 180, stock: 0, stock_total: 0, image_url: null }

const api = vi.hoisted(() => ({
  list: vi.fn(),
  getDepartments: vi.fn(async () => []),
  getBrands: vi.fn(async () => []),
  barcodesMissingCount: vi.fn(async () => 0),
  getCatalogKpis: vi.fn(async () => null),
  catalogKpis: vi.fn(async () => null),
}))
vi.mock('../../../api/products', () => ({ productsApi: api }))
vi.mock('../../../api/inventory', () => ({ inventoryApi: {} }))
vi.mock('../../../api/organization', () => ({ organizationApi: { getBranches: vi.fn(async () => []) } }))
vi.mock('../../../components/products/FormularioProducto', () => ({ FormularioProducto: () => <div data-testid="formulario" /> }))

import { Products } from '../Products'
import { claveVista } from '../useVistaProductos'
import { useAuthStore } from '../../../store/authStore'
import { useEnabledModulesStore } from '../../../store/enabledModulesStore'
import { useBranchCountStore } from '../../../store/branchCountStore'

const admin = { id: 1, username: 'admin', role: 'ADMINISTRADOR', branch_id: null, branch_name: null }
const cajera = { id: 2, username: 'caja', role: 'CAJERO', branch_id: 20, branch_name: 'Roma' }
const vendedor = { id: 3, username: 'piso', role: 'VENDEDOR', branch_id: 20, branch_name: 'Roma' }
const entrar = (user: unknown) => {
  useAuthStore.setState({ user } as never)
  return render(<MemoryRouter><Products /></MemoryRouter>)
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  api.list.mockResolvedValue({ items: [BLUSA, FALDA], total: 2 })
  useBranchCountStore.setState({ count: 1 })
  useEnabledModulesStore.setState({ loaded: true, perfilUi: 'completo', enabledModules: [] } as never)
})
afterEach(cleanup)

describe('Productos en tarjetas: cajera', () => {
  it('por omisión ve tarjetas con foto, nombre, código, precio y existencia; nunca el costo', async () => {
    const { container } = entrar(cajera)
    await screen.findByText('Blusa lino')
    expect(container.querySelectorAll('article')).toHaveLength(2)
    expect(screen.getByLabelText('Ver en tarjetas').getAttribute('aria-pressed')).toBe('true')

    const foto = container.querySelector('article img') as HTMLImageElement
    expect(foto.getAttribute('src')).toBe(BLUSA.image_url)
    expect(foto.getAttribute('loading')).toBe('lazy')
    expect(foto.className).toContain('object-cover')
    expect(screen.getAllByTestId('sin-foto')).toHaveLength(1)   // la falda: marcador del mismo alto

    const texto = container.textContent ?? ''
    expect(texto).toContain('BL-01')
    expect(texto).toContain('7501234567890')
    expect(texto).toContain('$250.00')
    expect(texto).not.toContain('987.65')
    expect(texto).not.toContain('432.1')
    expect(texto).not.toMatch(/costo/i)
  })

  it('conserva las acciones de la fila (ajustar stock y editar)', async () => {
    entrar(cajera)
    await screen.findByText('Blusa lino')
    expect(screen.getByLabelText('Ajustar stock — Blusa lino')).toBeTruthy()
    fireEvent.click(screen.getByLabelText('Editar — Blusa lino'))
    expect(await screen.findByTestId('formulario')).toBeTruthy()
  })

  it('el conmutador vuelve a la lista y lo recuerda solo para ella', async () => {
    const { container, unmount } = entrar(cajera)
    await screen.findByText('Blusa lino')
    fireEvent.click(screen.getByLabelText('Ver en lista'))
    expect(container.querySelectorAll('article')).toHaveLength(0)
    expect(container.querySelectorAll('li')).toHaveLength(2)
    expect(localStorage.getItem(claveVista(2))).toBe('lista')
    unmount()

    const otra = entrar(vendedor)
    await screen.findByText('Blusa lino')
    expect(otra.container.querySelectorAll('article')).toHaveLength(2)
  })
})

describe('Productos en tarjetas: vendedor', () => {
  it('tarjeta de consulta: sin costo ni acciones de edición', async () => {
    const { container } = entrar(vendedor)
    await screen.findByText('Blusa lino')
    expect(container.querySelectorAll('article')).toHaveLength(2)
    expect(container.textContent).not.toContain('987.65')
    expect(screen.queryByLabelText(/Ajustar stock/)).toBeNull()
    expect(screen.queryByLabelText(/Editar/)).toBeNull()
    expect(screen.queryByText('Nuevo producto')).toBeNull()
  })
})

describe('Productos en tarjetas: oficina', () => {
  it('tarjetas por omisión con las acciones de la fila; la lista sigue siendo la tabla', async () => {
    const { container } = entrar(admin)
    await screen.findByText('Blusa lino')
    expect(container.querySelectorAll('article')).toHaveLength(2)
    expect(container.querySelector('table')).toBeNull()
    expect(container.textContent).not.toContain('987.65')
    expect(screen.getAllByLabelText(/Editar/).length).toBeGreaterThan(0)

    fireEvent.click(screen.getByLabelText('Ver en lista'))
    await waitFor(() => expect(container.querySelector('table')).toBeTruthy())
    expect(localStorage.getItem(claveVista(1))).toBe('lista')
  })

  it('en escritorio la búsqueda toma el foco al entrar', async () => {
    entrar(admin)
    await screen.findByText('Blusa lino')
    expect(document.activeElement).toBe(screen.getByPlaceholderText('Buscar por nombre o SKU...'))
  })

  it('en teléfono o tablet no toma el foco (abriría el teclado)', async () => {
    const original = window.matchMedia
    window.matchMedia = ((q: string) => ({
      matches: /max-width/.test(q), media: q, addEventListener: () => {}, removeEventListener: () => {},
    })) as never
    try {
      entrar(admin)
      await screen.findByText('Blusa lino')
      expect(document.activeElement).toBe(document.body)
    } finally {
      window.matchMedia = original
    }
  })
})
