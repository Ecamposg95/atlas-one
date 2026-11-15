// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react'

const api = vi.hoisted(() => ({
  listImages: vi.fn(), addImage: vi.fn(async () => ({})), orderImages: vi.fn(async () => []), removeImage: vi.fn(async () => []),
}))
vi.mock('../../../api/products', () => ({ productsApi: api }))
import { GaleriaProducto } from '../GaleriaProducto'

beforeEach(() => vi.clearAllMocks())
afterEach(cleanup)

describe('GaleriaProducto', () => {
  it('lista vacía con image_url heredada: la muestra como principal actual', async () => {
    api.listImages.mockResolvedValue([])
    render(<GaleriaProducto productId="p" imagenHeredada="/img/viejo.jpg" />)
    expect(await screen.findByAltText('Foto principal actual')).toBeTruthy()
  })

  it('subir una foto vuelve a pedir la lista', async () => {
    api.listImages.mockResolvedValue([])
    render(<GaleriaProducto productId="p" />)
    await waitFor(() => expect(api.listImages).toHaveBeenCalledTimes(1))
    const f = new File(['x'], 'a.png', { type: 'image/png' })
    fireEvent.change(screen.getByLabelText('Agregar foto a la galería'), { target: { files: [f] } })
    await waitFor(() => expect(api.addImage).toHaveBeenCalledWith('p', f))
    await waitFor(() => expect(api.listImages).toHaveBeenCalledTimes(2))
  })
})
