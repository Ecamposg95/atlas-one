// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, screen, fireEvent, cleanup, within } from '@testing-library/react'
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
vi.mock('../../../hooks/useSucursalesVendibles', () => ({ useSucursalesVendibles: () => [] }))
vi.mock('../../../components/crm/AbonoModal', () => ({ AbonoModal: () => <div data-testid="abono-modal" /> }))

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
})
