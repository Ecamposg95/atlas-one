// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react'

const { ficha, campos, crearSeguimiento, cerrarSeguimiento, create, update } = vi.hoisted(() => ({
  ficha: vi.fn(), campos: vi.fn(), crearSeguimiento: vi.fn(), cerrarSeguimiento: vi.fn(),
  create: vi.fn(), update: vi.fn(),
}))
vi.mock('../../../api/customers', async (orig) => ({
  ...(await orig<typeof import('../../../api/customers')>()),
  customersApi: { ficha, campos, crearSeguimiento, cerrarSeguimiento, create, update },
}))

import { FichaCliente } from '../FichaCliente'
import { CustomerFormModal } from '../CustomerFormModal'
import { estadoDeFecha, valorDeCampo } from '../crmUtil'

const CLIENTE = {
  id: 7, name: 'Lupita', phone: '5511112222', email: null, tax_id: null, address: null,
  current_balance: 0, credit_limit: 0, tipo: 'MAYOREO', company: 'Boutique Sol', birthday: '1990-05-17',
  campos: { talla: 'M' },
}
const FICHA = {
  limitado: false, customer: CLIENTE, saldo: 0, credito_disponible: 0,
  resumen: { total_comprado: 400, tickets: 2, ticket_promedio: 200, primera_compra: null, ultima_compra: '2026-11-20T18:00:00', dias_sin_comprar: 4, devoluciones: 0 },
  compras: [{ id: 'a', series: 'A', folio: 12, created_at: '2026-11-20T18:00:00', total: 300, status: 'PAID' }],
  productos: [{ descripcion: 'Blusa', piezas: 2, importe: 400 }],
  vales: [{ code: 'ABCD2345', balance: 50, created_at: '2026-11-21T10:00:00' }], vales_saldo: 50,
  seguimiento: [{ id: 3, customer_id: 7, customer_name: 'Lupita', customer_phone: null, tipo: 'WHATSAPP', nota: 'Avisar', due_date: '2020-01-01', status: 'PENDIENTE', resultado: null, assigned_user_id: 1, done_at: null }],
  campos: [{ id: 1, key: 'talla', label: 'Talla', tipo: 'LISTA', opciones: ['CH', 'M'], orden: 1 }],
}

beforeEach(() => { vi.clearAllMocks(); campos.mockResolvedValue(FICHA.campos) })
afterEach(cleanup)

describe('ficha 360', () => {
  it('la gerencia ve acumulados, campos propios, vales y seguimiento', async () => {
    ficha.mockResolvedValue(FICHA)
    render(<FichaCliente customerId={7} />)
    const f = await screen.findByTestId('ficha-cliente')
    expect(f.textContent).toContain('Mayoreo')
    expect(f.textContent).toContain('Boutique Sol')
    expect(f.textContent).toContain('Total comprado')
    expect(f.textContent).toContain('Talla')
    expect(f.textContent).toContain('ABCD2345')
    expect(f.textContent).toContain('Blusa')
    expect(f.textContent).toContain('Vencido')
  })

  it('la caja no ve acumulados ni lo que más compra', async () => {
    ficha.mockResolvedValue({ ...FICHA, limitado: true, resumen: null, productos: [] })
    render(<FichaCliente customerId={7} />)
    const f = await screen.findByTestId('ficha-cliente')
    expect(f.textContent).not.toContain('Total comprado')
    expect(f.textContent).not.toContain('Lo que más compra')
    expect(f.textContent).toContain('Compras recientes en tu sucursal')
  })

  it('agenda un seguimiento y marca otro como hecho', async () => {
    ficha.mockResolvedValue(FICHA)
    crearSeguimiento.mockResolvedValue({})
    cerrarSeguimiento.mockResolvedValue({})
    render(<FichaCliente customerId={7} />)
    await screen.findByTestId('ficha-cliente')
    fireEvent.change(screen.getByLabelText('Nota del seguimiento'), { target: { value: 'Llegó su talla' } })
    fireEvent.click(screen.getByRole('button', { name: /Agendar/ }))
    await waitFor(() => expect(crearSeguimiento).toHaveBeenCalled())
    expect(crearSeguimiento.mock.calls[0][0]).toMatchObject({ customer_id: 7, tipo: 'LLAMADA', nota: 'Llegó su talla' })
    fireEvent.click(screen.getByRole('button', { name: /Marcar hecho/ }))
    await waitFor(() => expect(cerrarSeguimiento).toHaveBeenCalledWith(3))
  })
})

describe('formulario de cliente', () => {
  it('la caja solo captura contacto y manda solo eso', async () => {
    create.mockResolvedValue({ ...CLIENTE, id: 9 })
    render(<CustomerFormModal customer={null} deCaja onClose={() => {}} onSaved={() => {}} />)
    expect(screen.queryByText('Tipo de cliente')).toBeNull()
    expect(screen.queryByText(/crédito habilitada/)).toBeNull()
    fireEvent.change(screen.getByPlaceholderText('Nombre o razón social'), { target: { value: 'Ana' } })
    fireEvent.click(screen.getByRole('button', { name: /Guardar/ }))
    await waitFor(() => expect(create).toHaveBeenCalled())
    expect(Object.keys(create.mock.calls[0][0]).sort()).toEqual(['email', 'name', 'notes', 'phone'])
    expect(campos).not.toHaveBeenCalled()
  })

  it('la gerencia edita tipo y campos propios', async () => {
    update.mockResolvedValue(CLIENTE)
    render(<CustomerFormModal customer={CLIENTE as never} onClose={() => {}} onSaved={() => {}} />)
    await screen.findByTestId('campos-propios')
    fireEvent.change(screen.getByLabelText('Talla'), { target: { value: 'CH' } })
    fireEvent.click(screen.getByRole('button', { name: /Guardar/ }))
    await waitFor(() => expect(update).toHaveBeenCalled())
    expect(update.mock.calls[0][1]).toMatchObject({ tipo: 'MAYOREO', company: 'Boutique Sol', campos: { talla: 'CH' } })
  })
})

describe('crmUtil', () => {
  it('clasifica la fecha del seguimiento', () => {
    expect(estadoDeFecha('2026-11-23', '2026-11-24')).toBe('vencido')
    expect(estadoDeFecha('2026-11-24', '2026-11-24')).toBe('hoy')
    expect(estadoDeFecha('2026-11-25', '2026-11-24')).toBe('proximo')
  })
  it('pinta el valor de un campo propio', () => {
    expect(valorDeCampo('SI_NO', true)).toBe('Sí')
    expect(valorDeCampo('TEXTO', '')).toBe('—')
  })
})
