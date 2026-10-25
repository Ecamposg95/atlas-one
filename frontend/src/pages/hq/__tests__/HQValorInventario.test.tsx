// frontend/src/pages/hq/__tests__/HQValorInventario.test.tsx
// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { render, screen, cleanup, fireEvent, within, waitFor } from '@testing-library/react'

const { valorInventario, getBranches } = vi.hoisted(() => ({ valorInventario: vi.fn(), getBranches: vi.fn() }))
vi.mock('../../../api/reports', () => ({ reportsApi: { valorInventario } }))
vi.mock('../../../api/organization', () => ({ organizationApi: { getBranches } }))

import { HQValorInventario } from '../HQValorInventario'
import { useAuthStore } from '../../../store/authStore'

const TOTALES = { piezas: 19, skus: 3, valor_venta: 10200, valor_costo: 2000, piezas_sin_costo: 14, skus_sin_costo: 2 }
const DEPTOS = [
  { clave: 'd1', nombre: 'Bolsas', piezas: 5, skus: 1, valor_venta: 5000, valor_costo: 2000, piezas_sin_costo: 0 },
  { clave: 'd2', nombre: 'Zapatos', piezas: 4, skus: 1, valor_venta: 3200, valor_costo: 0, piezas_sin_costo: 4 },
  { clave: '', nombre: 'Sin departamento', piezas: 10, skus: 1, valor_venta: 2000, valor_costo: 0, piezas_sin_costo: 10 },
]
const MARCAS = [
  { clave: '', nombre: 'Sin marca', piezas: 14, skus: 2, valor_venta: 5200, valor_costo: 0, piezas_sin_costo: 14 },
  { clave: 'm1', nombre: 'Gucci', piezas: 5, skus: 1, valor_venta: 5000, valor_costo: 2000, piezas_sin_costo: 0 },
]
const SUCURSALES = [
  { clave: '1', nombre: 'Roma', piezas: 7, skus: 2, valor_venta: 6200, valor_costo: 1200, piezas_sin_costo: 4 },
  { clave: '2', nombre: 'Condesa', piezas: 12, skus: 2, valor_venta: 4000, valor_costo: 800, piezas_sin_costo: 10 },
]
let veCosto = true
const sinCosto = <T extends { valor_costo: number | null }>(g: T): T => (veCosto ? g : { ...g, valor_costo: null })

// El mock responde según `agrupar` y acota las marcas cuando llega `department_id`.
const responder = async (p: { agrupar?: string; department_id?: string; branch_id?: number }) => {
  const base = { branch_id: p.branch_id ?? null, department_id: p.department_id ?? null, ve_costo: veCosto }
  if (p.agrupar === 'departamento') return { ...base, agrupar: 'departamento', totales: sinCosto(TOTALES), grupos: DEPTOS.map(sinCosto) }
  if (p.agrupar === 'marca' && p.department_id) {
    return { ...base, agrupar: 'marca', totales: sinCosto({ ...TOTALES, piezas: 5, skus: 1, valor_venta: 5000, piezas_sin_costo: 0, skus_sin_costo: 0 }), grupos: [sinCosto(MARCAS[1])] }
  }
  if (p.agrupar === 'marca') return { ...base, agrupar: 'marca', totales: sinCosto(TOTALES), grupos: MARCAS.map(sinCosto) }
  return { ...base, agrupar: 'sucursal', totales: sinCosto(TOTALES), grupos: SUCURSALES.map(sinCosto) }
}

const SUCURSAL = { id: 1, name: 'Roma', branch_type: 'STORE', is_active: true, can_sell: true }
const usuario = (role: string) => useAuthStore.setState({ user: { id: 1, username: 'u', role, branch_id: 1 } } as never)
const pintar = () => render(<MemoryRouter><HQValorInventario /></MemoryRouter>)

beforeEach(() => {
  veCosto = true
  usuario('ADMINISTRADOR')
  valorInventario.mockReset().mockImplementation(responder)
  getBranches.mockReset().mockResolvedValue([SUCURSAL])
})
afterEach(cleanup)

describe('HQValorInventario — distribución del valor', () => {
  it('reparte el valor por departamento y por marca con su porcentaje', async () => {
    pintar()
    const deptos = await screen.findByTestId('distribucion-departamento')
    await within(deptos).findByText('Bolsas')
    expect(within(deptos).getByText('49.0%')).toBeTruthy()        // 5000 / 10200
    expect(within(deptos).getByText('Sin departamento')).toBeTruthy()
    const marcas = screen.getByTestId('distribucion-marca')
    await within(marcas).findByText('Gucci')
    expect(within(marcas).getByText('51.0%')).toBeTruthy()        // Sin marca 5200 / 10200
    expect(screen.getAllByText('$10,200.00').length).toBeGreaterThan(0)   // tarjeta de totales y pie de cada panel
    expect(screen.getByLabelText('Sucursal')).toBeTruthy()          // el admin sí elige sucursal
  })

  it('elegir un departamento acota las marcas a ese departamento y se puede quitar', async () => {
    pintar()
    const deptos = await screen.findByTestId('distribucion-departamento')
    fireEvent.click(await within(deptos).findByRole('button', { name: 'Bolsas' }))
    await waitFor(() => expect(valorInventario).toHaveBeenCalledWith(expect.objectContaining({ agrupar: 'marca', department_id: 'd1' })))
    const marcas = screen.getByTestId('distribucion-marca')
    await within(marcas).findByText(/Marcas en/)
    expect(within(marcas).getByText('Bolsas')).toBeTruthy()
    expect(within(marcas).getByText(/% dentro del departamento/)).toBeTruthy()   // base del porcentaje
    await waitFor(() => expect(within(marcas).queryByText('Sin marca')).toBeNull())
    fireEvent.click(within(marcas).getByRole('button', { name: 'Quitar' }))
    await within(marcas).findByText('Sin marca')
  })

  it('"Sin departamento" no se puede elegir: no tiene id que filtrar', async () => {
    pintar()
    const deptos = await screen.findByTestId('distribucion-departamento')
    await within(deptos).findByText('Sin departamento')
    expect(within(deptos).getByRole('button', { name: 'Zapatos' })).toBeTruthy()
    expect(within(deptos).queryByRole('button', { name: 'Sin departamento' })).toBeNull()
  })

  it('el panel por sucursal solo aparece con más de una sucursal que vende', async () => {
    pintar()
    await screen.findByTestId('distribucion-departamento')
    expect(screen.queryByTestId('distribucion-sucursal')).toBeNull()
    cleanup()
    getBranches.mockResolvedValue([SUCURSAL, { ...SUCURSAL, id: 2, name: 'Condesa' }])
    pintar()
    const suc = await screen.findByTestId('distribucion-sucursal')
    await within(suc).findByText('Condesa')
    expect(valorInventario).toHaveBeenCalledWith(expect.objectContaining({ agrupar: 'sucursal' }))
  })

  it('el gerente no ve selector de sucursal ni columnas de costo', async () => {
    veCosto = false
    usuario('GERENTE')
    pintar()
    const deptos = await screen.findByTestId('distribucion-departamento')
    await within(deptos).findByText('Bolsas')
    expect(screen.queryByLabelText('Sucursal')).toBeNull()
    expect(screen.getByRole('button', { name: 'Actualizar' })).toBeTruthy()   // conserva el botón sin el selector
    const cabeceras = within(deptos).getAllByRole('columnheader').map((th) => th.textContent)
    expect(cabeceras).not.toContain('Valor a costo')
    expect(cabeceras).toContain('% del valor')
  })
})
