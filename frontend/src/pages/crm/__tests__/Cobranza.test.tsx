// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, screen, fireEvent, cleanup, within, waitFor, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const { cobranza, modo } = vi.hoisted(() => ({ cobranza: vi.fn(), modo: { telefono: false } }))
vi.mock('../../../api/customers', () => ({
  customersApi: {
    cobranza,
    getUnpaidDocuments: vi.fn().mockResolvedValue([]),
    getStatement: vi.fn().mockResolvedValue([]),
    getStatementPdf: vi.fn(),
  },
}))
vi.mock('../../../hooks/useIsMobile', () => ({ useEsTelefono: () => modo.telefono }))
// Con `activo` falso el hook real no pide nada: el mock lo imita para probar el gating por rol.
vi.mock('../../../hooks/useSucursalesVendibles', () => ({
  useSucursalesVendibles: (activo: boolean) => (activo ? [{ id: 1, name: 'Roma' }, { id: 2, name: 'Condesa' }] : []),
}))
vi.mock('../../../components/crm/AbonoModal', () => ({
  AbonoModal: ({ onDone }: { onDone?: () => void }) => <button type="button" data-testid="abono-modal" onClick={() => onDone?.()}>abonar</button>,
}))

import { Cobranza } from '../Cobranza'
import { useAuthStore } from '../../../store/authStore'

const DATOS = {
  resumen: { por_cobrar: 150, vencido_30: 70, clientes: 2, a_favor: 20 },
  total: 2,
  items: [
    { id: 1, name: 'Ana Pérez', phone: '55 1234 5678', balance: 70, cargo_mas_viejo: '2026-09-16T18:00:00Z', dias: 45,
      ultimo_abono: '2026-10-21T18:00:00Z', branch_id: 1, branch_name: 'Roma', tickets_abiertos: 1,
      antiguedad: { current: 0, '31_60': 70, '61_90': 0, '91_plus': 0 } },
    { id: 2, name: 'Beto', phone: null, balance: 80, cargo_mas_viejo: '2026-10-31T18:00:00Z', dias: 0,
      ultimo_abono: null, branch_id: 2, branch_name: 'Condesa', tickets_abiertos: 1,
      antiguedad: { current: 80, '31_60': 0, '61_90': 0, '91_plus': 0 } },
  ],
}
const pintar = () => render(<MemoryRouter><Cobranza /></MemoryRouter>)

beforeEach(() => {
  cobranza.mockReset().mockResolvedValue(DATOS)
  modo.telefono = false
  useAuthStore.setState({ user: { id: 1, role: 'ADMINISTRADOR' } as never, org: { id: 17, name: 'Eleven Fashion' } as never })
})
afterEach(cleanup)

describe('Cuentas por cobrar', () => {
  it('pinta las cifras, los renglones y la antigüedad', async () => {
    pintar()
    expect(await screen.findByText('Ana Pérez')).toBeTruthy()
    const kpis = screen.getByTestId('kpis-cobranza')
    expect(within(kpis).getByText('$150.00')).toBeTruthy()
    expect(within(kpis).getByText('$70.00')).toBeTruthy()
    expect(within(kpis).getByText('2')).toBeTruthy()
    expect(screen.getByText(/45 días/)).toBeTruthy()
    expect(screen.getAllByText(/31-60/).length).toBeGreaterThan(0)
  })

  it('WhatsApp abre el chat con el mensaje y se deshabilita sin teléfono (Review Focus 5)', async () => {
    const open = vi.spyOn(window, 'open').mockImplementation(() => null)
    pintar()
    await screen.findByText('Ana Pérez')
    const botones = screen.getAllByRole('button', { name: /WhatsApp/ }) as HTMLButtonElement[]
    expect(botones.length).toBe(2)
    const [ana, beto] = botones
    expect(beto.disabled).toBe(true)
    expect(beto.title).toBe('Sin teléfono')
    fireEvent.click(ana)
    const url = open.mock.calls[0][0] as string
    expect(url.startsWith('https://wa.me/525512345678?text=')).toBe(true)
    expect(decodeURIComponent(url.split('text=')[1])).toBe(
      'Hola Ana Pérez, te saludamos de Eleven Fashion. Tienes un saldo pendiente de $70.00. Puedes pasar a abonar cuando gustes. ¡Gracias!')
    open.mockRestore()
  })

  it('al abrir un renglón muestra el detalle y Registrar abono', async () => {
    pintar()
    fireEvent.click(await screen.findByText('Ana Pérez'))
    const dialogo = await screen.findByRole('dialog')
    fireEvent.click(within(dialogo).getByRole('button', { name: /Registrar abono/ }))
    expect(await screen.findByTestId('abono-modal')).toBeTruthy()
  })

  it('el selector de sucursal es del administrador; al gerente no se le enseña (el backend lo confina)', async () => {
    pintar()
    await screen.findByText('Ana Pérez')
    expect(screen.getByRole('combobox', { name: 'Sucursal' })).toBeTruthy()
    cleanup()
    useAuthStore.setState({ user: { id: 2, role: 'GERENTE' } as never })
    pintar()
    await screen.findByText('Ana Pérez')
    expect(screen.queryByRole('combobox', { name: 'Sucursal' })).toBeNull()
  })

  it('en teléfono usa tarjetas, no tabla', async () => {
    modo.telefono = true
    pintar()
    await screen.findByText('Ana Pérez')
    expect(document.querySelector('table')).toBeNull()
  })

  it('cambiar filtros vuelve a pedir con esos parámetros', async () => {
    pintar()
    await screen.findByText('Ana Pérez')
    fireEvent.change(screen.getByLabelText('Antigüedad'), { target: { value: '91_plus' } })
    expect(cobranza).toHaveBeenLastCalledWith(expect.objectContaining({ bucket: '91_plus' }))
    fireEvent.change(screen.getByLabelText('Orden'), { target: { value: 'antiguedad' } })
    expect(cobranza).toHaveBeenLastCalledWith(expect.objectContaining({ order: 'antiguedad' }))
  })

  // Ayudas para respuestas controladas a mano (carreras entre peticiones).
  const item = (id: number, name: string, balance: number) => ({
    ...DATOS.items[0], id, name, balance, phone: '55 1234 5678',
    antiguedad: { current: balance, '31_60': 0, '61_90': 0, '91_plus': 0 },
  })
  const respuesta = (items: ReturnType<typeof item>[], total = items.length) => ({
    resumen: { por_cobrar: 1, vencido_30: 0, clientes: items.length, a_favor: 0 }, total, items,
  })
  const diferidas = () => {
    const pend: ((v: unknown) => void)[] = []
    cobranza.mockClear()
    cobranza.mockImplementation(() => new Promise((res) => { pend.push(res) }))
    return pend
  }

  it('escribir y cambiar un filtro enseguida no dispara una petición con el filtro viejo', async () => {
    pintar()
    await screen.findByText('Ana Pérez')
    const pend = diferidas()
    fireEvent.change(screen.getByLabelText('Buscar'), { target: { value: 'zzz' } })
    fireEvent.change(screen.getByLabelText('Orden'), { target: { value: 'antiguedad' } })
    await act(async () => { await new Promise((r) => setTimeout(r, 450)) })
    expect(cobranza.mock.calls.length).toBeGreaterThan(0)
    for (const [params] of cobranza.mock.calls) {
      expect(params).toEqual(expect.objectContaining({ search: 'zzz', order: 'antiguedad' }))
    }
    await act(async () => { pend.forEach((r) => r(respuesta([item(9, 'Zeta', 5)]))) })
    expect(await screen.findByText('Zeta')).toBeTruthy()
  })

  it('una respuesta vieja que llega tarde no pisa a la más reciente', async () => {
    pintar()
    await screen.findByText('Ana Pérez')
    const pend = diferidas()
    fireEvent.change(screen.getByLabelText('Orden'), { target: { value: 'antiguedad' } })
    fireEvent.change(screen.getByLabelText('Antigüedad'), { target: { value: '91_plus' } })
    expect(pend.length).toBe(2)
    await act(async () => { pend[1](respuesta([item(8, 'Nueva', 5)])) })
    expect(await screen.findByText('Nueva')).toBeTruthy()
    await act(async () => { pend[0](respuesta([item(7, 'Vieja', 5)])) })
    expect(screen.queryByText('Vieja')).toBeNull()
    expect(screen.getByText('Nueva')).toBeTruthy()
  })

  it('tras abonar, el detalle se rehace con el saldo nuevo y WhatsApp lo usa', async () => {
    const open = vi.spyOn(window, 'open').mockImplementation(() => null)
    pintar()
    fireEvent.click(await screen.findByText('Ana Pérez'))
    const dialogo = await screen.findByRole('dialog')
    expect(dialogo.textContent).toContain('Debe $70.00')
    fireEvent.click(within(dialogo).getByRole('button', { name: /Registrar abono/ }))
    cobranza.mockResolvedValue(respuesta([{ ...DATOS.items[0], balance: 20 }]))
    fireEvent.click(await screen.findByTestId('abono-modal'))
    await waitFor(() => expect(screen.getByRole('dialog').textContent).toContain('Debe $20.00'))
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /WhatsApp/ }))
    expect(decodeURIComponent((open.mock.calls[0][0] as string).split('text=')[1])).toContain('saldo pendiente de $20.00')
    open.mockRestore()
  })

  it('si tras abonar el cliente ya no está en la lista, el detalle se cierra', async () => {
    pintar()
    fireEvent.click(await screen.findByText('Ana Pérez'))
    const dialogo = await screen.findByRole('dialog')
    fireEvent.click(within(dialogo).getByRole('button', { name: /Registrar abono/ }))
    cobranza.mockResolvedValue(respuesta([item(2, 'Beto', 80)]))
    fireEvent.click(await screen.findByTestId('abono-modal'))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  })

  it('si el cliente sale de la lista y reaparece tras otro filtro, el detalle no se reabre solo', async () => {
    pintar()
    fireEvent.click(await screen.findByText('Ana Pérez'))
    await screen.findByRole('dialog')
    cobranza.mockResolvedValue(respuesta([item(2, 'Beto', 80)]))
    fireEvent.change(screen.getByLabelText('Orden'), { target: { value: 'antiguedad' } })
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    cobranza.mockResolvedValue(DATOS)
    fireEvent.change(screen.getByLabelText('Antigüedad'), { target: { value: '31_60' } })
    await screen.findByText('Ana Pérez')
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('avisa cuando la lista está recortada y no cuando está completa', async () => {
    cobranza.mockResolvedValue({ ...DATOS, total: 350 })
    pintar()
    expect(await screen.findByText('Mostrando 2 de 350 clientes. Afina la búsqueda o el filtro para ver el resto.')).toBeTruthy()
    cleanup()
    cobranza.mockResolvedValue(DATOS)
    pintar()
    await screen.findByText('Ana Pérez')
    expect(screen.queryByText(/Mostrando/)).toBeNull()
  })
})
