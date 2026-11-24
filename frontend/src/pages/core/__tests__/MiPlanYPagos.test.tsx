// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { render, screen, cleanup, fireEvent } from '@testing-library/react'

const { mia, esTelefono, rol } = vi.hoisted(() => ({ mia: vi.fn(), esTelefono: { valor: false }, rol: { valor: 'ADMINISTRADOR' } }))
vi.mock('../../../api/suscripciones', async (original) => ({
  ...(await original<typeof import('../../../api/suscripciones')>()),
  suscripcionesApi: { mia },
}))
vi.mock('../../../hooks/useIsMobile', () => ({ useEsTelefono: () => esTelefono.valor, useIsMobile: () => esTelefono.valor }))
// La pestaña vive en el centro de ajustes: lo demás se sustituye para no cargar media aplicación.
vi.mock('../../../store/authStore', () => ({ useAuthStore: (sel: (s: unknown) => unknown) => sel({ user: { role: rol.valor } }) }))
vi.mock('../../../hooks/useCanalTienda', () => ({ useCanalTienda: () => ({ puedePublicar: false }) }))
vi.mock('../Organization', () => ({ Organization: () => <div>empresa</div> }))
vi.mock('../Sucursales', () => ({ Sucursales: () => <div>sucursales</div> }))
vi.mock('../TiendaEnLinea', () => ({ TiendaEnLinea: () => <div>tienda</div> }))
vi.mock('../../pos/PrinterSettings', () => ({ PrinterSettings: () => <div>impresoras</div> }))
vi.mock('../../pos/PrinterSettingsCajera', () => ({ PrinterSettingsCajera: () => <div>impresora de caja</div> }))

import { MiPlanYPagos } from '../MiPlanYPagos'
import { Configuracion } from '../../pos/Configuracion'

const CARGOS = [
  {
    id: 2, periodo_desde: '2026-12-15', periodo_hasta: '2027-01-14', importe: '499.00', pagado: '0.00', saldo: '499.00',
    vence_el: '2026-12-15', estado: 'pendiente', vencido: false, pagado_at: null, cancelado_at: null, motivo_cancelacion: null, pagos: [],
  },
  {
    id: 1, periodo_desde: '2026-11-15', periodo_hasta: '2026-12-14', importe: '499.00', pagado: '499.00', saldo: '0.00',
    vence_el: '2026-11-15', estado: 'pagado', vencido: false, pagado_at: '2026-11-16T10:00:00Z', cancelado_at: null, motivo_cancelacion: null,
    pagos: [{ id: 9, importe: '499.00', fecha_pago: '2026-11-16', metodo: 'transferencia', referencia: 'SPEI 123', notas: null, registrado_por: null, created_at: null }],
  },
]
const DATOS = {
  plan: { clave: 'START', nombre: 'ONE START', precio_lista_mxn: '499', max_usuarios: 3, max_sucursales_venta: 1 },
  uso: { usuarios_activos: 3, sucursales_venta: 1 },
  suscripcion: {
    id: 1, organization_id: 7, plan: 'START', plan_nombre: 'ONE START', precio_mxn: '450.00', precio_lista_mxn: '499',
    periodicidad: 'mensual', dia_corte: 15, fecha_inicio: '2026-11-15', proxima_renovacion: '2026-12-15',
    estado: 'por_vencer', estado_manual: false, notas: null, rfc: 'XAXX010101000', razon_social: 'Tienda SA', correo_facturacion: null,
  },
  cargos: CARGOS,
}

beforeEach(() => { mia.mockReset().mockResolvedValue(DATOS); esTelefono.valor = false; rol.valor = 'ADMINISTRADOR' })
afterEach(cleanup)

describe('Mi plan y pagos', () => {
  it('pinta plan, precio pactado, renovación, estado y uso contra topes', async () => {
    render(<MiPlanYPagos />)
    const raiz = await screen.findByTestId('mi-plan-y-pagos')
    expect(raiz.textContent).toContain('ONE START')
    expect(raiz.textContent).toContain('$450.00')
    expect(raiz.textContent).toContain('15 dic 2026')
    expect(screen.getByText('Por vencer')).toBeTruthy()
    expect(raiz.textContent).toContain('3 de 3')
    expect(raiz.textContent).toContain('1 de 1')
    expect(raiz.textContent).toContain('XAXX010101000')
  })

  it('escritorio: historial en tabla con los pagos de cada cargo', async () => {
    render(<MiPlanYPagos />)
    await screen.findByTestId('mi-plan-y-pagos')
    expect(document.querySelectorAll('table tbody tr')).toHaveLength(2)
    expect(screen.getByText('Pagado', { selector: 'span' })).toBeTruthy()
    expect(document.querySelector('table')!.textContent).toContain('SPEI 123')
    expect(document.querySelector('table')!.textContent).toContain('Transferencia')
  })

  it('teléfono: tarjetas en vez de tabla', async () => {
    esTelefono.valor = true
    render(<MiPlanYPagos />)
    await screen.findByTestId('mi-plan-y-pagos')
    expect(document.querySelector('table')).toBeNull()
    expect(screen.getByText('15 nov 2026 – 14 dic 2026')).toBeTruthy()
  })

  it('es de solo lectura: ni botones ni campos', async () => {
    render(<MiPlanYPagos />)
    await screen.findByTestId('mi-plan-y-pagos')
    expect(document.querySelectorAll('button, input, select, textarea')).toHaveLength(0)
  })

  it('cargo vencido se marca y la suscripción vencida avisa', async () => {
    mia.mockResolvedValue({
      ...DATOS,
      suscripcion: { ...DATOS.suscripcion, estado: 'vencida' },
      cargos: [{ ...CARGOS[0], vencido: true }],
    })
    render(<MiPlanYPagos />)
    await screen.findByTestId('mi-plan-y-pagos')
    expect(screen.getByText('Vencido')).toBeTruthy()
    expect(screen.getByText(/Tienes un pago vencido/)).toBeTruthy()
  })

  it('sin suscripción registrada: muestra el plan de lista y lo explica', async () => {
    mia.mockResolvedValue({ ...DATOS, suscripcion: null, cargos: [] })
    render(<MiPlanYPagos />)
    const raiz = await screen.findByTestId('mi-plan-y-pagos')
    expect(raiz.textContent).toContain('$499.00')
    expect(screen.getByText(/Todavía no hay una suscripción registrada/)).toBeTruthy()
    expect(screen.getByText('Aún no hay cargos.')).toBeTruthy()
  })

  it('si el servidor lo niega, muestra el motivo', async () => {
    mia.mockRejectedValue({ response: { data: { detail: 'Solo administradores y dueños pueden ver el plan y los pagos.' } } })
    render(<MiPlanYPagos />)
    expect((await screen.findByRole('alert')).textContent).toContain('Solo administradores y dueños')
  })
})

describe('Configuración: pestaña "Mi plan y pagos"', () => {
  const pintar = (ruta: string) => render(<MemoryRouter initialEntries={[ruta]}><Configuracion /></MemoryRouter>)

  it.each(['ADMINISTRADOR', 'DUEÑO'])('%s la ve y ?tab=plan la abre', async (r) => {
    rol.valor = r
    pintar('/configuracion?tab=plan')
    expect(screen.getByRole('tab', { name: /Mi plan y pagos/ }).getAttribute('aria-selected')).toBe('true')
    expect(await screen.findByTestId('mi-plan-y-pagos')).toBeTruthy()
  })

  it('se llega desde la pestaña', async () => {
    pintar('/configuracion')
    expect(mia).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('tab', { name: /Mi plan y pagos/ }))
    expect(await screen.findByTestId('mi-plan-y-pagos')).toBeTruthy()
  })

  it.each(['GERENTE', 'CAJERO'])('%s no la ve ni pide los datos', (r) => {
    rol.valor = r
    pintar('/configuracion?tab=plan')
    expect(screen.queryByRole('tab', { name: /Mi plan y pagos/ })).toBeNull()
    expect(mia).not.toHaveBeenCalled()
  })
})
