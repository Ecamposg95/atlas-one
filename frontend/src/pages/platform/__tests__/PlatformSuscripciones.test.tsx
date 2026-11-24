// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { render, screen, cleanup, fireEvent, waitFor, within } from '@testing-library/react'

const { api, rol, exito, fallo } = vi.hoisted(() => ({
  api: { listar: vi.fn(), detalle: vi.fn(), guardar: vi.fn(), generarCargo: vi.fn(), registrarPago: vi.fn(), cancelarCargo: vi.fn() },
  rol: { valor: 'SUPERADMIN' }, exito: vi.fn(), fallo: vi.fn(),
}))
vi.mock('../../../api/suscripciones', async (original) => ({
  ...(await original<typeof import('../../../api/suscripciones')>()),
  suscripcionesApi: api,
}))
vi.mock('../../../store/authStore', () => ({ useAuthStore: (sel: (s: unknown) => unknown) => sel({ user: { platform_role: rol.valor } }) }))
vi.mock('../../../store/toastStore', () => ({ toast: { success: exito, error: fallo, info: vi.fn(), warning: vi.fn() } }))

import { PlatformSuscripciones } from '../PlatformSuscripciones'
import { SeccionSuscripcion } from '../org/SeccionSuscripcion'
import { NAV_PLATFORM } from '../platformNav'

const LISTA = {
  totales: {
    cartera_vencida: '499.00', por_vencer: '800.00', ingreso_mensual_recurrente: '1800.00',
    por_estado: { al_corriente: 1, por_vencer: 1, vencida: 1, suspendida: 0, cortesia: 0 }, sin_suscripcion: 4,
  },
  items: [
    { organization_id: 7, organizacion: 'La Coqueta', plan: 'START', plan_nombre: 'ONE START', precio_mxn: '499.00', periodicidad: 'mensual',
      proxima_renovacion: '2026-11-15', estado: 'vencida', saldo_vencido: '499.00', saldo_por_vencer: '0.00' },
    { organization_id: 8, organizacion: 'Novedades', plan: 'PRO', plan_nombre: 'ONE PRO', precio_mxn: '12000.00', periodicidad: 'anual',
      proxima_renovacion: '2027-01-10', estado: 'al_corriente', saldo_vencido: '0.00', saldo_por_vencer: '800.00' },
  ],
}
const CARGO = {
  id: 31, periodo_desde: '2026-11-15', periodo_hasta: '2026-12-14', importe: '499.00', pagado: '100.00', saldo: '399.00',
  vence_el: '2026-11-15', estado: 'pendiente', vencido: true, pagado_at: null, cancelado_at: null, motivo_cancelacion: null,
  pagos: [{ id: 1, importe: '100.00', fecha_pago: '2026-11-20', metodo: 'efectivo', referencia: null, notas: null, registrado_por: 'ecg', created_at: null }],
}
const SUS = {
  id: 1, organization_id: 7, plan: 'START', plan_nombre: 'ONE START', precio_mxn: '499.00', precio_lista_mxn: '499',
  periodicidad: 'mensual', dia_corte: 15, fecha_inicio: '2026-11-15', proxima_renovacion: '2026-11-15',
  estado: 'vencida', estado_manual: false, notas: 'trato de palabra', rfc: null, razon_social: null, correo_facturacion: null,
}
const DETALLE = { organization_id: 7, organizacion: 'La Coqueta', plan_organizacion: 'START', suscripcion: SUS, cargos: [CARGO] }
const PLANES = [
  { clave: 'FREE', nombre: 'ONE FREE', precio_mxn: 0 }, { clave: 'START', nombre: 'ONE START', precio_mxn: 499 },
  { clave: 'PRO', nombre: 'ONE PRO', precio_mxn: 999 },
] as never

beforeEach(() => {
  rol.valor = 'SUPERADMIN'
  exito.mockReset(); fallo.mockReset()
  api.listar.mockReset().mockResolvedValue(LISTA)
  api.detalle.mockReset().mockResolvedValue(DETALLE)
  api.guardar.mockReset().mockResolvedValue(DETALLE)
  api.generarCargo.mockReset().mockResolvedValue({ creado: true, cargo: CARGO })
  api.registrarPago.mockReset().mockResolvedValue({ ...DETALLE, cargos: [{ ...CARGO, estado: 'pagado', vencido: false, saldo: '0.00' }] })
  api.cancelarCargo.mockReset().mockResolvedValue(DETALLE)
})
afterEach(cleanup)

describe('Plataforma · Suscripciones', () => {
  const pintar = () => render(<MemoryRouter><PlatformSuscripciones /></MemoryRouter>)

  it('está en la navegación de plataforma', () => {
    expect(NAV_PLATFORM.map((i) => i.to)).toContain('/platform/suscripciones')
  })

  it('totales arriba y una fila por suscripción', async () => {
    pintar()
    await screen.findByText('La Coqueta')
    expect(screen.getByText('Ingreso mensual recurrente').parentElement!.parentElement!.textContent).toContain('$1,800.00')
    expect(screen.getByText('Cartera vencida').parentElement!.parentElement!.textContent).toContain('$499.00')
    expect(screen.getByText('Sin suscripción').parentElement!.parentElement!.textContent).toContain('4')
    expect(screen.getByText('Novedades')).toBeTruthy()
    expect(screen.getByText(/\$12,000\.00 \/año/)).toBeTruthy()
    expect(api.listar).toHaveBeenCalledWith(undefined)
  })

  it('el filtro por estado vuelve a pedir la lista con ese estado', async () => {
    pintar()
    await screen.findByText('La Coqueta')
    const filtros = within(screen.getByRole('group', { name: 'Filtrar por estado' }))
    expect(filtros.getByRole('button', { name: 'Vencida · 1' })).toBeTruthy()
    fireEvent.click(filtros.getByRole('button', { name: 'Vencida · 1' }))
    await waitFor(() => expect(api.listar).toHaveBeenLastCalledWith({ estado: 'vencida' }))
    expect(filtros.getByRole('button', { name: 'Vencida · 1' }).getAttribute('aria-pressed')).toBe('true')
    fireEvent.click(filtros.getByRole('button', { name: 'Todas' }))
    await waitFor(() => expect(api.listar).toHaveBeenLastCalledWith(undefined))
  })
})

describe('Ficha de organización · sección Suscripción', () => {
  const pintar = () => render(<SeccionSuscripcion orgId={7} plans={PLANES} />)

  it('muestra la suscripción, sus cargos y los pagos', async () => {
    pintar()
    const fila = await screen.findByTestId('cargo-31')
    expect(screen.getByTestId('seccion-suscripcion').textContent).toContain('trato de palabra')
    expect(fila.textContent).toContain('Vencido')
    expect(fila.textContent).toContain('$399.00')
    expect(fila.textContent).toContain('Efectivo')
    expect(fila.textContent).toContain('ecg')
  })

  it('"Registrar pago" abre el formulario con el saldo y manda el pago', async () => {
    pintar()
    const fila = await screen.findByTestId('cargo-31')
    fireEvent.click(within(fila).getByRole('button', { name: 'Registrar pago' }))
    const dialogo = within(await screen.findByRole('dialog'))
    expect((dialogo.getByLabelText('Importe del pago') as HTMLInputElement).value).toBe('399')
    fireEvent.change(dialogo.getByLabelText('Método de pago'), { target: { value: 'deposito' } })
    fireEvent.change(dialogo.getByLabelText('Referencia'), { target: { value: 'Ficha 88' } })
    fireEvent.click(dialogo.getByRole('button', { name: 'Registrar pago' }))
    await waitFor(() => expect(api.registrarPago).toHaveBeenCalledWith(31, expect.objectContaining({
      importe: '399', metodo: 'deposito', referencia: 'Ficha 88',
    })))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(exito).toHaveBeenCalledWith('Pago registrado')
    expect(screen.getByTestId('cargo-31').textContent).toContain('Pagado')
  })

  it('un cargo con pagos no ofrece Cancelar', async () => {
    pintar()
    const fila = await screen.findByTestId('cargo-31')
    expect(within(fila).queryByRole('button', { name: 'Cancelar' })).toBeNull()
  })

  it('si el servidor rechaza el pago, el formulario sigue abierto con el motivo', async () => {
    api.registrarPago.mockRejectedValue({ response: { data: { detail: 'El pago ($500.00) es mayor al saldo del cargo ($399.00).' } } })
    pintar()
    fireEvent.click(within(await screen.findByTestId('cargo-31')).getByRole('button', { name: 'Registrar pago' }))
    fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Registrar pago' }))
    await waitFor(() => expect(fallo).toHaveBeenCalledWith(expect.stringContaining('mayor al saldo')))
    expect(screen.getByRole('dialog')).toBeTruthy()
  })

  it('sin suscripción ofrece darla de alta con el precio de lista del plan', async () => {
    api.detalle.mockResolvedValue({ ...DETALLE, suscripcion: null, cargos: [], plan_organizacion: 'PRO' })
    pintar()
    fireEvent.click(await screen.findByRole('button', { name: /Dar de alta/ }))
    const dialogo = within(await screen.findByRole('dialog'))
    expect((dialogo.getByLabelText('Plan') as HTMLSelectElement).value).toBe('PRO')
    expect((dialogo.getByLabelText('Precio pactado') as HTMLInputElement).value).toBe('999')
    fireEvent.click(dialogo.getByRole('button', { name: 'Guardar' }))
    await waitFor(() => expect(api.guardar).toHaveBeenCalledWith(7, expect.objectContaining({ plan: 'PRO', precio_mxn: '999', periodicidad: 'mensual' })))
    // Sin estado manual, el estado no viaja: lo calcula el servidor.
    expect(api.guardar.mock.calls[0][1]).not.toHaveProperty('estado')
  })

  it('SUPPORT la ve en solo lectura', async () => {
    rol.valor = 'SUPPORT'
    pintar()
    await screen.findByTestId('cargo-31')
    expect(screen.queryByRole('button')).toBeNull()
  })
})
