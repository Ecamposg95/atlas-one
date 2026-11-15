// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { render, screen, cleanup, fireEvent, waitFor, within } from '@testing-library/react'

const api = vi.hoisted(() => ({
  getBrands: vi.fn(async () => [{ id: 'b-1', name: 'Nike', logo_url: null, is_premium: false }]),
  updateBrand: vi.fn(async () => ({})),
  createBrand: vi.fn(async () => ({})),
  deleteBrand: vi.fn(),
  getDepartments: vi.fn(async () => [
    { id: 'd-1', name: 'Ropa', parent_id: null },
    { id: 'd-2', name: 'Playeras', parent_id: 'd-1' },
    { id: 'd-3', name: 'Calzado', parent_id: null },
  ]),
  createDepartment: vi.fn(async () => ({})),
  updateDepartment: vi.fn(async () => ({})),
  deleteDepartment: vi.fn(),
}))
const canal = vi.hoisted(() => ({
  getConfig: vi.fn(async () => ({
    activo: true, sucursales_web: [1],
    sucursales: [{ id: 1, name: 'Roma', can_sell: true }, { id: 2, name: 'Centro', can_sell: true }, { id: 3, name: 'Bodega', can_sell: false }],
  })),
  putConfig: vi.fn(async () => ({})),
}))
vi.mock('../../../api/products', () => ({ productsApi: api }))
vi.mock('../../../api/canal', () => ({ canalApi: canal }))
vi.mock('../../pos/PrinterSettings', () => ({ PrinterSettings: () => <div>PANTALLA IMPRESORA</div> }))
vi.mock('../../pos/PrinterSettingsCajera', () => ({ PrinterSettingsCajera: () => <div>IMPRESORA CAJERA</div> }))

import { Brands } from '../Brands'
import { Departments } from '../Departments'
import { Configuracion } from '../../pos/Configuracion'
import { useAuthStore } from '../../../store/authStore'
import { useEnabledModulesStore } from '../../../store/enabledModulesStore'

const como = (role: string, modulos: string[]) => {
  useAuthStore.setState({ user: { id: 1, username: 'u', role, branch_id: null, branch_name: null } } as never)
  useEnabledModulesStore.setState({ enabledModules: modulos } as never)
}
beforeEach(() => vi.clearAllMocks())
afterEach(cleanup)

describe('Marcas', () => {
  it('«Marca premium» solo con el módulo, y viaja is_premium', async () => {
    como('ADMINISTRADOR', [])
    render(<MemoryRouter><Brands /></MemoryRouter>)
    fireEvent.click(await screen.findByLabelText('Editar Nike'))
    expect(screen.queryByLabelText('Marca premium')).toBeNull()
    cleanup()
    como('ADMINISTRADOR', ['tienda_en_linea'])
    render(<MemoryRouter><Brands /></MemoryRouter>)
    fireEvent.click(await screen.findByLabelText('Editar Nike'))
    fireEvent.click(screen.getByLabelText('Marca premium'))
    fireEvent.click(screen.getByText('Guardar'))
    await waitFor(() => expect(api.updateBrand).toHaveBeenCalledWith('b-1', expect.objectContaining({ is_premium: true })))
  })
})

describe('Departamentos', () => {
  it('«Departamento padre» lista solo raíces (con módulo)', async () => {
    como('ADMINISTRADOR', ['tienda_en_linea'])
    render(<MemoryRouter><Departments /></MemoryRouter>)
    fireEvent.click(await screen.findByText('Nuevo'))
    const sel = screen.getByLabelText('Departamento padre') as HTMLSelectElement
    const textos = Array.from(sel.options).map((o) => o.text)
    expect(textos).toEqual(['Ninguno (raíz)', 'Ropa', 'Calzado'])
  })

  it('sin módulo no aparece el selector', async () => {
    como('ADMINISTRADOR', [])
    render(<MemoryRouter><Departments /></MemoryRouter>)
    fireEvent.click(await screen.findByText('Nuevo'))
    expect(screen.queryByLabelText('Departamento padre')).toBeNull()
  })
})

describe('Configuración', () => {
  it('sin canal: igual que hoy, sin pestañas', async () => {
    como('ADMINISTRADOR', [])
    render(<Configuracion />)
    expect(screen.getByText('PANTALLA IMPRESORA')).toBeTruthy()
    expect(screen.queryByText('Tienda en línea')).toBeNull()
  })

  it('cajera con canal: no ve la pestaña', () => {
    como('CAJERO', ['tienda_en_linea'])
    render(<Configuracion />)
    expect(screen.getByText('IMPRESORA CAJERA')).toBeTruthy()
    expect(screen.queryByText('Tienda en línea')).toBeNull()
  })

  it('admin con canal: pestaña con casillas por sucursal que vende; guardar manda los ids', async () => {
    como('ADMINISTRADOR', ['tienda_en_linea'])
    render(<Configuracion />)
    fireEvent.click(screen.getByText('Tienda en línea'))
    expect(await screen.findByLabelText('Roma')).toBeTruthy()
    expect(screen.queryByLabelText('Bodega')).toBeNull()
    fireEvent.click(screen.getByLabelText('Centro'))
    fireEvent.click(screen.getByText('Guardar'))
    await waitFor(() => expect(canal.putConfig).toHaveBeenCalledWith([1, 2]))
  })

  it('«Todas las que venden» manda null', async () => {
    como('ADMINISTRADOR', ['tienda_en_linea'])
    render(<Configuracion />)
    fireEvent.click(screen.getByText('Tienda en línea'))
    await screen.findByLabelText('Roma')
    fireEvent.click(screen.getByLabelText('Todas las que venden'))
    fireEvent.click(screen.getByText('Guardar'))
    await waitFor(() => expect(canal.putConfig).toHaveBeenCalledWith(null))
    void within
  })
})
