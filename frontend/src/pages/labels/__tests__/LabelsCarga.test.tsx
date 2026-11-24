// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, screen, cleanup, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const { candidates } = vi.hoisted(() => ({ candidates: vi.fn() }))
vi.mock('../../../api/labels', () => ({
  labelsApi: { candidates, preview: vi.fn(), createJob: vi.fn(), testLabel: vi.fn() },
}))
vi.mock('../../../api/products', () => ({
  productsApi: { getDepartments: vi.fn().mockResolvedValue([]), getBrands: vi.fn().mockResolvedValue([]) },
}))
vi.mock('../../../api/printer', () => ({
  AgentUnreachableError: class extends Error {},
  printerApi: { pingAgent: vi.fn().mockResolvedValue(false), getLocalPrinters: vi.fn().mockResolvedValue([]), printViaAgent: vi.fn() },
}))
vi.mock('../../../hooks/useIsMobile', () => ({ useEsTelefono: () => false }))

import { Labels } from '../Labels'

const FILA = {
  variant_id: 'v1', product_id: 'p1', sku: 'MU-001', barcode: '2017000000013',
  product_name: 'Chamarra', sale_name: 'Marca Uno · Chamarra', brand: 'Marca Uno',
  department: '', gender: '', size: 'M', color: 'Negro', price: 100,
  stock: 5, copies_default: 5, piezas_carga: 3, printable: true, reason: null, created_at: null,
}

const pintar = (url: string) => render(<MemoryRouter initialEntries={[url]}><Labels /></MemoryRouter>)

beforeEach(() => {
  candidates.mockReset().mockResolvedValue({ items: [FILA], total: 1 })
  localStorage.clear()
})
afterEach(cleanup)

describe('Etiquetas por carga', () => {
  it('con ?carga=… pide candidates con carga_id y muestra el chip Carga', async () => {
    pintar('/labels?carga=abc&folio=7')
    await waitFor(() => expect(candidates).toHaveBeenCalled())
    expect(candidates.mock.calls[0][0]).toMatchObject({ carga_id: 'abc' })
    expect(screen.getByTestId('chip-carga').textContent).toContain('Carga #7')
  })

  it('quitar el chip vuelve a pedir sin carga_id', async () => {
    pintar('/labels?carga=abc&folio=7')
    await waitFor(() => expect(candidates).toHaveBeenCalledTimes(1))
    fireEvent.click(screen.getByLabelText('Quitar filtro de carga'))
    await waitFor(() => expect(candidates).toHaveBeenCalledTimes(2))
    expect(candidates.mock.calls[1][0].carga_id).toBeUndefined()
    expect(screen.queryByTestId('chip-carga')).toBeNull()
  })

  it('copias por omisión = piezas_carga', async () => {
    pintar('/labels?carga=abc')
    await screen.findByText('MU-001')
    const campo = screen.getAllByRole('spinbutton').find((i) => (i as HTMLInputElement).value === '3')
    expect(campo).toBeTruthy()
  })
})
