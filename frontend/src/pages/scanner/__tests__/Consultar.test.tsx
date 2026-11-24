// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react'

const api = vi.hoisted(() => ({
  search: vi.fn(), scanExact: vi.fn(), getById: vi.fn(), update: vi.fn(), updateVariant: vi.fn(), adjustStock: vi.fn(),
}))
vi.mock('../../../api/products', () => ({ productsApi: api }))
vi.mock('../../../api/organization', () => ({ organizationApi: { getBranches: vi.fn(async () => []) } }))

import { StoreScanner } from '../StoreScanner'
import { useAuthStore } from '../../../store/authStore'

const PLAYERA = {
  id: 'p-1', name: 'Playera', sale_name: 'Playera', sku: 'PLY', barcode: '750', price: 1500, stock_total: 4,
  variants: [], prices: [], image_url: null,
}
const como = (role: string) =>
  useAuthStore.setState({ user: { id: 1, username: 'u', role, branch_id: 7, branch_name: 'Roma' } } as never)
const teclear = (texto: string) =>
  fireEvent.change(screen.getByPlaceholderText('Nombre, SKU o código'), { target: { value: texto } })

beforeEach(() => {
  vi.clearAllMocks()
  api.search.mockResolvedValue({ items: [PLAYERA], total: 1, page: 0, pages: 1 })
  api.scanExact.mockResolvedValue([])
  api.getById.mockResolvedValue(PLAYERA)
})
afterEach(cleanup)

describe('Consultar: buscador de precios y escáner en una pantalla', () => {
  it('teclear busca por nombre y lista precio y existencia', async () => {
    como('VENDEDOR')
    render(<StoreScanner />)
    teclear('playera')
    expect(await screen.findByText('Existencia: 4', {}, { timeout: 2000 })).toBeTruthy()
    expect(api.search).toHaveBeenCalledWith('playera', 0, 20)
    expect(api.scanExact).not.toHaveBeenCalled()
  })

  it('el vendedor abre la ficha de solo lectura: sin precio editable ni conteo', async () => {
    como('VENDEDOR')
    render(<StoreScanner />)
    teclear('playera')
    fireEvent.click(await screen.findByText('Existencia: 4', {}, { timeout: 2000 }))
    expect(await screen.findByText('Precio')).toBeTruthy()
    expect(api.getById).not.toHaveBeenCalled()
    expect(screen.queryByRole('spinbutton')).toBeNull()
    expect(screen.queryByText(/Guardar/)).toBeNull()
  })

  it('la cajera abre el producto completo y puede corregirlo', async () => {
    como('CAJERO')
    render(<StoreScanner />)
    teclear('playera')
    fireEvent.click(await screen.findByText('Existencia: 4', {}, { timeout: 2000 }))
    await waitFor(() => expect(api.getById).toHaveBeenCalledWith('p-1'))
    expect((await screen.findAllByText(/Guardar/)).length).toBeGreaterThan(0)
  })

  it('código exacto sin producto: la cajera puede ligarlo; el vendedor solo ve el aviso', async () => {
    api.search.mockResolvedValue({ items: [], total: 0, page: 0, pages: 1 })
    como('VENDEDOR')
    const { unmount } = render(<StoreScanner />)
    teclear('999')
    fireEvent.click(screen.getByText('Buscar'))
    expect(await screen.findByText(/No hay ningún producto con el código/)).toBeTruthy()
    expect(screen.queryByText('¿Se lo asignamos a un producto?')).toBeNull()
    unmount()

    como('CAJERO')
    render(<StoreScanner />)
    teclear('999')
    fireEvent.click(screen.getByText('Buscar'))
    expect(await screen.findByText('¿Se lo asignamos a un producto?')).toBeTruthy()
  })
})
