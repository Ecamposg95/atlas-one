// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react'

const api = vi.hoisted(() => ({
  list: vi.fn(),
  getDepartments: vi.fn(async () => []),
  getBrands: vi.fn(async () => [{ id: 'b-1', name: 'Nike', logo_url: null }]),
  barcodesMissingCount: vi.fn(async () => 0),
  catalogKpis: vi.fn(async () => null),
  facets: vi.fn(async () => ({ sizes: ['M', 'G', '32'], colors: ['Blanco', 'Negro'] })),
  webPublish: vi.fn(async () => ({ processed: 1 })),
  downloadTemplate: vi.fn(async () => undefined),
}))
vi.mock('../../../api/products', () => ({ productsApi: api }))
vi.mock('../../../components/ui/ConfirmDialog', () => ({ confirm: vi.fn(async () => true) }))
vi.mock('../../../components/catalog/CatalogKpis', () => ({ CatalogKpis: () => <div data-testid="kpis" /> }))
vi.mock('../../../components/products/FormularioProducto', () => ({ FormularioProducto: () => <div /> }))

import { Products } from '../Products'
import { useAuthStore } from '../../../store/authStore'
import { useEnabledModulesStore } from '../../../store/enabledModulesStore'
import { useBranchCountStore } from '../../../store/branchCountStore'

const prod = {
  id: 'p-1', sku: 'S1', name: 'Blusa', price: 10, stock: 1, is_active: true, approval_status: 'APPROVED',
  department: null, department_name: null, brand_id: null, brand_name: null, description: null,
  cost: 1, image_url: null, variants: [], branch_statuses: [],
}
const admin = { id: 1, username: 'admin', role: 'ADMINISTRADOR', branch_id: null, platform_role: 'NONE' }
const perfil = (perfilUi: 'basico' | 'completo', enabledModules: string[] = []) =>
  useEnabledModulesStore.setState({ loaded: true, perfilUi, enabledModules } as never)
const pintar = () => render(<MemoryRouter><Products /></MemoryRouter>)
const botonMas = () => screen.getByRole('button', { name: /Más filtros/ })
const ultimaLista = () => api.list.mock.calls.at(-1)![0] as Record<string, unknown>

beforeEach(() => {
  vi.clearAllMocks()
  api.list.mockResolvedValue({ items: [prod], total: 1 })
  useAuthStore.setState({ user: admin } as never)
  useBranchCountStore.setState({ count: 1 })
  perfil('completo')
})
afterEach(cleanup)

describe('Productos: «Más filtros»', () => {
  it('el panel está cerrado al entrar y no pide tallas ni colores', async () => {
    pintar()
    await screen.findByText('Blusa')
    expect(botonMas().getAttribute('aria-expanded')).toBe('false')
    expect(screen.queryByLabelText('Talla')).toBeNull()
    expect(api.facets).not.toHaveBeenCalled()
  })

  it('al abrirlo trae las opciones del catálogo y cada eje viaja al servidor', async () => {
    pintar()
    await screen.findByText('Blusa')
    fireEvent.click(botonMas())
    expect(botonMas().getAttribute('aria-expanded')).toBe('true')
    await waitFor(() => expect(api.facets).toHaveBeenCalledTimes(1))
    await screen.findByRole('option', { name: '32' })

    fireEvent.change(screen.getByLabelText('Talla'), { target: { value: 'M' } })
    await waitFor(() => expect(ultimaLista()).toMatchObject({ size: 'M', skip: 0 }))
    fireEvent.change(screen.getByLabelText('Color'), { target: { value: 'Negro' } })
    fireEvent.change(screen.getByLabelText('Género'), { target: { value: 'MUJER' } })
    fireEvent.click(screen.getByLabelText('Solo con existencia'))
    fireEvent.change(screen.getByLabelText('Dados de alta desde'), { target: { value: '2026-11-03' } })
    await waitFor(() => expect(ultimaLista()).toMatchObject({
      size: 'M', color: 'Negro', gender: 'MUJER', only_with_stock: true,
      created_after: new Date(2026, 10, 3).toISOString(),
    }))
    // Las cifras del catálogo usan los mismos filtros.
    await waitFor(() => expect(api.catalogKpis).toHaveBeenLastCalledWith(expect.objectContaining({
      size: 'M', color: 'Negro', gender: 'MUJER', only_with_stock: true,
    })))
    // El botón lleva la cuenta de lo puesto.
    expect(botonMas().textContent).toContain('(5)')

    fireEvent.click(screen.getByRole('button', { name: /Limpiar estos filtros/ }))
    await waitFor(() => {
      const p = ultimaLista()
      for (const k of ['size', 'color', 'gender', 'only_with_stock', 'created_after']) expect(p).not.toHaveProperty(k)
    })
    expect(botonMas().textContent).not.toContain('(')
  })

  it('«Publicar todo lo filtrado» se apaga con un filtro avanzado puesto', async () => {
    perfil('completo', ['tienda_en_linea'])
    pintar()
    await screen.findByText('Blusa')
    const publicar = () => screen.getByRole('button', { name: 'Publicar todo lo filtrado' }) as HTMLButtonElement
    expect(publicar().disabled).toBe(false)
    fireEvent.click(botonMas())
    fireEvent.click(screen.getByLabelText('Solo con existencia'))
    await waitFor(() => expect(publicar().disabled).toBe(true))
    expect(screen.getByText(/los de «Más filtros»/)).toBeTruthy()
  })

  it('la selección se limpia al cambiar un filtro avanzado', async () => {
    perfil('completo', ['tienda_en_linea'])
    pintar()
    await screen.findByText('Blusa')
    fireEvent.click(screen.getByLabelText('Seleccionar Blusa'))
    expect(screen.getByText('Publicar en tienda web (1)')).toBeTruthy()
    fireEvent.click(botonMas())
    fireEvent.change(screen.getByLabelText('Género'), { target: { value: 'HOMBRE' } })
    await waitFor(() => expect(screen.queryByText('Publicar en tienda web (1)')).toBeNull())
  })

  it('en modo básico también está, con la marca dentro del panel (la barra no la trae)', async () => {
    perfil('basico')
    pintar()
    await screen.findByText('Blusa')
    expect(screen.queryByLabelText('Marca')).toBeNull()
    fireEvent.click(botonMas())
    await waitFor(() => expect(api.getBrands).toHaveBeenCalled())
    await screen.findByRole('option', { name: 'Nike' })
    fireEvent.change(screen.getByLabelText('Marca'), { target: { value: 'b-1' } })
    await waitFor(() => expect(ultimaLista()).toMatchObject({ brand_id: 'b-1' }))
    expect(botonMas().textContent).toContain('(1)')
  })

  it('en el catálogo la marca sigue en la barra y no se repite en el panel', async () => {
    pintar()
    await screen.findByText('Blusa')
    fireEvent.click(botonMas())
    await screen.findByLabelText('Talla')
    expect(screen.getAllByLabelText('Marca')).toHaveLength(1)
  })
})
