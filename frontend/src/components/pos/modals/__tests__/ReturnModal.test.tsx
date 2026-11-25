// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react'

const { list, create, piezas, autorizar, getDevolucionBase64, printViaAgent } = vi.hoisted(() => ({
  list: vi.fn(), create: vi.fn(), piezas: vi.fn(), autorizar: vi.fn(),
  getDevolucionBase64: vi.fn(), printViaAgent: vi.fn(),
}))
vi.mock('../../../../hooks/useIsMobile', () => ({ useEsTelefono: () => false }))
vi.mock('../../../../api/sales', () => ({ salesApi: { list } }))
vi.mock('../../../../api/printer', () => ({ printerApi: { getDevolucionBase64, printViaAgent } }))
vi.mock('../../../../api/returns', () => ({
  returnsApi: { create, piezas, autorizar },
  returnLabel: (r: { id: string }) => `DEV-${r.id.slice(-6).toUpperCase()}`,
  MOTIVOS_DEVOLUCION: [
    { code: 'DEFECTO', label: 'Defecto', regresa_a_stock: false },
    { code: 'TALLA', label: 'Talla o medida', regresa_a_stock: true },
  ],
}))

import { ReturnModal } from '../ReturnModal'
import { useAuthStore } from '../../../../store/authStore'
import { useEnabledModulesStore } from '../../../../store/enabledModulesStore'
import { usePOSStore } from '../../../../store/posStore'

const usuario = (role: string) =>
  useAuthStore.setState({ user: { id: 1, username: 'u', role, branch_id: 1, platform_role: 'NONE' } } as never)

const VENTA = {
  id: 'venta-1', series: 'A', folio: 41, status: 'PAID', total_amount: 250, created_at: '2026-10-20T15:00:00Z',
  payments: [{ method: 'CARD', amount: 250 }],
  lines: [{ variant_id: 'v1', description: 'Blusa', sku: 'BLU', quantity: 2, unit_price: '150' }],
}
const MOTIVOS = [
  { code: 'DEFECTO', label: 'Defecto', regresa_a_stock: false },
  { code: 'TALLA', label: 'Talla o medida', regresa_a_stock: true },
]
const INFO = {
  piezas: [{ variant_id: 'v1', descripcion: 'Blusa', sku: 'BLU', vendido: 2, devuelto: 1, en_tramite: 0, disponible: 1, precio_pagado: '125.00' }],
  metodos: ['CARD'], pendiente: null, motivos: MOTIVOS, monto_libre: '200', es_caja: true,
}

beforeEach(() => {
  list.mockReset().mockResolvedValue({ items: [] })
  create.mockReset()
  piezas.mockReset().mockResolvedValue(INFO)
  autorizar.mockReset()
  getDevolucionBase64.mockReset().mockResolvedValue('QUJD')
  printViaAgent.mockReset().mockResolvedValue(undefined)
  useEnabledModulesStore.setState({ diasVentasCaja: 30 })
  usePOSStore.setState({ printerName: 'EPSON' } as never)
})
afterEach(() => { cleanup(); useEnabledModulesStore.getState().reset() })

async function buscarFolio() {
  render(<ReturnModal onClose={() => {}} onSuccess={() => {}} />)
  fireEvent.click(screen.getByRole('button', { name: /Por folio/ }))
  fireEvent.change(screen.getByPlaceholderText(/Folio del ticket/), { target: { value: 'A-1' } })
  fireEvent.keyDown(screen.getByPlaceholderText(/Folio del ticket/), { key: 'Enter' })
}

/** Abre el ticket, devuelve la pieza que queda y elige el motivo. */
async function llenar(onSuccess = () => {}) {
  render(<ReturnModal onClose={() => {}} onSuccess={onSuccess} initialSale={VENTA as never} />)
  fireEvent.click(await screen.findByText('Todas (1)'))
  fireEvent.change(screen.getByLabelText('Motivo'), { target: { value: 'TALLA' } })
}

describe('ReturnModal', () => {
  it('la cajera, ante un folio no encontrado, ve el plazo de su tienda', async () => {
    usuario('CAJERO')
    await buscarFolio()
    expect(await screen.findByText(/Solo aparecen ventas de tu sucursal de los últimos 30 días/)).toBeTruthy()
  })

  it('con plazo 0 el aviso sigue siendo "solo ventas de hoy"', async () => {
    usuario('CAJERO')
    useEnabledModulesStore.setState({ diasVentasCaja: 0 })
    await buscarFolio()
    expect(await screen.findByText('Ticket no encontrado. Solo aparecen ventas de hoy; para días anteriores pide al gerente.')).toBeTruthy()
  })

  it('el gerente sigue viendo solo "Ticket no encontrado"', async () => {
    usuario('GERENTE')
    await buscarFolio()
    expect(await screen.findByText('Ticket no encontrado')).toBeTruthy()
  })

  it('ofrece solo lo que queda por devolver, al precio pagado y por el método del ticket', async () => {
    usuario('CAJERO')
    await llenar()
    expect(screen.getByText('Ya se devolvieron 1; quedan 1')).toBeTruthy()
    const metodo = screen.getByText('Tarjeta').closest('select') as HTMLSelectElement
    expect(Array.from(metodo.options).map((o) => o.value)).toEqual(['CARD'])
    expect(screen.getByText('Dentro de tu monto: se aprueba al registrar.')).toBeTruthy()
    create.mockResolvedValue({ id: 'dev-000001', status: 'APPROVED', total_refunded: 125 })
    fireEvent.click(screen.getByRole('button', { name: /Registrar/ }))
    await waitFor(() => expect(create).toHaveBeenCalled())
    expect(create.mock.calls[0][0]).toMatchObject({
      sale_id: 'venta-1', reason_code: 'TALLA', refund_method: 'CARD',
      items: [{ variant_id: 'v1', quantity: 1, refund_amount: 125, is_inventory_reentry: true }],
    })
  })

  it('un defecto manda las piezas a merma por omisión', async () => {
    usuario('CAJERO')
    render(<ReturnModal onClose={() => {}} onSuccess={() => {}} initialSale={VENTA as never} />)
    await screen.findByText('Todas (1)')
    fireEvent.change(screen.getByLabelText('Motivo'), { target: { value: 'DEFECTO' } })
    expect(screen.getByRole('button', { name: 'Merma' })).toBeTruthy()
  })

  it('sin motivo no deja registrar', async () => {
    usuario('CAJERO')
    render(<ReturnModal onClose={() => {}} onSuccess={() => {}} initialSale={VENTA as never} />)
    fireEvent.click(await screen.findByText('Todas (1)'))
    expect((screen.getByRole('button', { name: /Registrar/ }) as HTMLButtonElement).disabled).toBe(true)
  })

  it('aprobada: muestra el comprobante y lo imprime', async () => {
    usuario('CAJERO')
    const onSuccess = vi.fn()
    await llenar(onSuccess)
    create.mockResolvedValue({ id: 'dev-000001', status: 'APPROVED', total_refunded: 125 })
    fireEvent.click(screen.getByRole('button', { name: /Registrar/ }))
    expect(await screen.findByText(/Devolución aprobada/)).toBeTruthy()
    expect(onSuccess).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: /Comprobante/ }))
    await waitFor(() => expect(printViaAgent).toHaveBeenCalledWith('EPSON', 'QUJD'))
    expect(getDevolucionBase64).toHaveBeenCalledWith('dev-000001')
    fireEvent.click(screen.getByRole('button', { name: 'Listo' }))
    expect(onSuccess).toHaveBeenCalled()
  })

  it('pendiente: pide el PIN del gerente; uno malo deja reintentar y el bueno la aprueba', async () => {
    usuario('CAJERO')
    await llenar()
    create.mockResolvedValue({ id: 'dev-000002', status: 'PENDING', total_refunded: 125 })
    fireEvent.click(screen.getByRole('button', { name: /Registrar/ }))
    const pin = await screen.findByLabelText('PIN del gerente')
    autorizar.mockRejectedValueOnce({ response: { status: 403, data: { detail: { code: 'PIN_INCORRECTO', message: 'PIN incorrecto' } } } })
    fireEvent.change(pin, { target: { value: '0000' } })
    fireEvent.click(screen.getByRole('button', { name: 'Autorizar' }))
    expect(await screen.findByText('PIN incorrecto')).toBeTruthy()
    autorizar.mockResolvedValueOnce({ id: 'dev-000002', status: 'APPROVED', total_refunded: 125 })
    fireEvent.change(screen.getByLabelText('PIN del gerente'), { target: { value: '1234' } })
    fireEvent.click(screen.getByRole('button', { name: 'Autorizar' }))
    expect(await screen.findByText(/Devolución aprobada/)).toBeTruthy()
    expect(autorizar).toHaveBeenLastCalledWith('dev-000002', '1234')
  })

  it('el gerente registra y cierra como siempre (aprueba desde Devoluciones)', async () => {
    usuario('GERENTE')
    piezas.mockResolvedValue({ ...INFO, es_caja: false, monto_libre: null })
    const onSuccess = vi.fn()
    await llenar(onSuccess)
    create.mockResolvedValue({ id: 'dev-000003', status: 'PENDING', total_refunded: 125 })
    fireEvent.click(screen.getByRole('button', { name: /Registrar/ }))
    await waitFor(() => expect(onSuccess).toHaveBeenCalled())
  })

  it('un ticket con devolución pendiente ofrece autorizarla en vez de registrar otra', async () => {
    usuario('CAJERO')
    piezas.mockResolvedValue({ ...INFO, pendiente: { id: 'dev-000009', total: '125' } })
    render(<ReturnModal onClose={() => {}} onSuccess={() => {}} initialSale={VENTA as never} />)
    fireEvent.click(await screen.findByRole('button', { name: /Autorizar con PIN del gerente/ }))
    expect(screen.getByLabelText('PIN del gerente')).toBeTruthy()
    expect(screen.queryByRole('button', { name: /Registrar/ })).toBeNull()
  })

  it('fuera de plazo: muestra el motivo del servidor y no ofrece piezas', async () => {
    usuario('CAJERO')
    const detail = 'Esta venta tiene más de 30 días: ya pasó el plazo de devolución en caja. Pide al gerente.'
    piezas.mockRejectedValue({ response: { status: 403, data: { detail } } })
    render(<ReturnModal onClose={() => {}} onSuccess={() => {}} initialSale={VENTA as never} />)
    expect(await screen.findByText(detail)).toBeTruthy()
    expect(screen.queryByText(/Todas \(/)).toBeNull()
  })

  it('un 403 del backend al registrar muestra su detail tal cual', async () => {
    usuario('CAJERO')
    const detail = 'Solo puedes devolver ventas de hoy. Pide al gerente.'
    create.mockRejectedValue({ response: { status: 403, data: { detail } } })
    await llenar()
    fireEvent.click(screen.getByRole('button', { name: /Registrar/ }))
    expect(await screen.findByText(detail)).toBeTruthy()
  })
})
