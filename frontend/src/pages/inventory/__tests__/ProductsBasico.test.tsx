// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { render, screen, cleanup, waitFor } from '@testing-library/react'

const api = vi.hoisted(() => ({
  list: vi.fn(async () => ({ items: [], total: 0 })),
  getDepartments: vi.fn(async () => []),
  barcodesMissingCount: vi.fn(async () => 4),
  getCatalogKpis: vi.fn(async () => null),
}))
vi.mock('../../../api/products', () => ({ productsApi: api }))
vi.mock('../../../api/inventory', () => ({ inventoryApi: {} }))
vi.mock('../../../api/organization', () => ({ organizationApi: { getBranches: vi.fn(async () => []) } }))

import { Products } from '../Products'
import { useAuthStore } from '../../../store/authStore'
import { useEnabledModulesStore } from '../../../store/enabledModulesStore'
import { useBranchCountStore } from '../../../store/branchCountStore'

const admin = { id: 1, username: 'admin', role: 'ADMINISTRADOR', branch_id: null, branch_name: null }
const cajera = { id: 2, username: 'caja', role: 'CAJERO', branch_id: 20, branch_name: 'Roma' }
const perfil = (perfilUi: 'basico' | 'completo') =>
  useEnabledModulesStore.setState({ loaded: true, perfilUi } as never)
const pintar = () => render(<MemoryRouter><Products /></MemoryRouter>)

beforeEach(() => {
  vi.clearAllMocks()
  useBranchCountStore.setState({ count: 1 })
})
afterEach(cleanup)

describe('Productos HQ', () => {
  it('completo: importar, etiquetas CSV, generar códigos y vista de rejilla', async () => {
    useAuthStore.setState({ user: admin } as never); perfil('completo')
    pintar()
    expect(await screen.findByLabelText('Generar códigos de barras faltantes (4)')).toBeTruthy()
    expect(screen.getByLabelText('Importar productos')).toBeTruthy()
    expect(screen.getByLabelText('Descargar etiquetas CSV')).toBeTruthy()
    expect(screen.getByLabelText('Vista cuadrícula')).toBeTruthy()
  })

  it('básico: solo Nuevo producto (no se montan los demás)', async () => {
    useAuthStore.setState({ user: admin } as never); perfil('basico')
    pintar()
    expect(await screen.findByLabelText('Nuevo producto')).toBeTruthy()
    await waitFor(() => expect(api.barcodesMissingCount).toHaveBeenCalled())
    expect(screen.queryByLabelText('Importar productos')).toBeNull()
    expect(screen.queryByLabelText('Descargar etiquetas CSV')).toBeNull()
    expect(screen.queryByLabelText(/Generar códigos/)).toBeNull()
    expect(screen.queryByLabelText('Vista cuadrícula')).toBeNull()
  })
})

describe('Productos de sucursal (cajera)', () => {
  it('completo: Plantilla e Importar Excel', async () => {
    useAuthStore.setState({ user: cajera } as never); perfil('completo')
    pintar()
    expect(await screen.findByText('Importar Excel')).toBeTruthy()
    expect(screen.getByText('Plantilla')).toBeTruthy()
  })

  it('básico: sin plantilla ni importador; Nuevo producto sigue', async () => {
    useAuthStore.setState({ user: cajera } as never); perfil('basico')
    pintar()
    expect(await screen.findByText('Nuevo producto')).toBeTruthy()
    expect(screen.queryByText('Importar Excel')).toBeNull()
    expect(screen.queryByText('Plantilla')).toBeNull()
  })
})
