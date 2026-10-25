// frontend/src/pages/reports/__tests__/Reportes.test.tsx
// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, cleanup, fireEvent, waitFor, within } from '@testing-library/react'

const { dashboard, commandCenterStats, exportCsv, getBranches } = vi.hoisted(() => ({
  dashboard: vi.fn(), commandCenterStats: vi.fn(), exportCsv: vi.fn(), getBranches: vi.fn(),
}))
vi.mock('../../../api/reports', () => ({ reportsApi: { dashboard, commandCenterStats, exportCsv } }))
vi.mock('../../../api/organization', () => ({ organizationApi: { getBranches } }))
// jsdom no tiene canvas: el kit se sustituye por stubs que exponen las series. El dibujo lo prueba el kit.
vi.mock('../../../components/graficas', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../components/graficas')>()),
  GraficaLinea: (p: { etiquetas: string[]; series: { nombre: string }[] }) => (
    <div data-testid="grafica-linea" data-etiquetas={p.etiquetas.join('|')} data-series={p.series.map((s) => s.nombre).join('|')} />
  ),
  GraficaBarras: (p: { etiquetas: string[]; valores: number[]; horizontal?: boolean }) => (
    <div data-testid={p.horizontal ? 'grafica-barras-h' : 'grafica-barras'} data-etiquetas={p.etiquetas.join('|')}
      data-valores={p.valores.map((v) => Math.round(v)).join('|')} />
  ),
  GraficaDona: (p: { partes: { nombre: string; valor: number }[] }) => (
    <div data-testid="grafica-dona" data-partes={p.partes.map((x) => `${x.nombre}=${x.valor}`).join('|')} />
  ),
}))

import { Reportes } from '../Reportes'
import { rangoPreset } from '../presetsReportes'

const r7 = rangoPreset('7d')
const DASH = {
  kpis: {
    sales: 9000, gross_sales: 9400, returns: 400, returns_count: 2, orders: 70, avg_ticket: 128.57, pending: 0, draft: 0,
    total_products: 10, transit_shipments: 0, prev_sales: 7500, prev_orders: 60, prev_avg_ticket: 125, prev_returns: 100,
    gross_profit: 3000, prev_gross_profit: 2000, sales_without_cost: 400,
  },
  charts: {
    trend: { labels: ['a', 'b', 'c', 'd', 'e', 'f', 'g'], data: [1, 2, 3, 4, 5, 6, 7] },
    trend_previous: { labels: ['a', 'b', 'c', 'd', 'e', 'f', 'g'], data: [1, 1, 1, 1, 1, 1, 1] },
    hourly: { labels: Array.from({ length: 24 }, (_, h) => `${h}:00`), data: Array.from({ length: 24 }, (_, h) => (h === 12 ? 7000 : 0)) },
    payments: { CARD: { total: 4000, count: 30 }, CASH: { total: 5000, count: 40 } },
    heatmap: [{ day: 1, hour: 12, amount: 500, tickets: 3 }],
  },
  top_products: [{ name: 'Blusa roja', qty: 14, total: 1400, trend: [] }, { name: 'Falda', qty: 7, total: 700, trend: [] }],
  low_stock: [], recent_sales: [],
}
const sucursalCc = (id: number, name: string, total_sales: number, is_hq = false) =>
  ({ id, name, status: 'ONLINE', total_sales, pending_cuts: 0, pending_users: [], critical_stock: 0, is_hq })
const CC = {
  global: { total_sales: 9000, total_tickets: 70, ticket_average: 128.57, items_per_ticket: 1, canceled_tickets: 0, overrides_total: 0, returns_total: 400, sales_growth: 20 },
  payment_methods: {}, hourly_distribution: [], alerts: [], top_products: [],
  branches: [sucursalCc(1, 'Roma', 6000), sucursalCc(2, 'Condesa', 3000), sucursalCc(9, 'Bodega', 0, true)],
}
const SUC = (id: number, name: string) => ({ id, name, branch_type: 'STORE', address: null, phone: null, is_headquarters: false, is_active: true, can_sell: true })
const variacionDe = (testId: string) => within(screen.getByTestId(testId)).queryByTestId('variacion')
const espera = () => new Promise((r) => setTimeout(r, 20))

beforeEach(() => {
  dashboard.mockReset().mockResolvedValue(DASH)
  commandCenterStats.mockReset().mockResolvedValue(CC)
  exportCsv.mockReset().mockResolvedValue(undefined)
  getBranches.mockReset().mockResolvedValue([SUC(1, 'Roma'), SUC(2, 'Condesa')])
})
afterEach(cleanup)

describe('Reportes', () => {
  it('arranca en 7 días y pide ese rango al dashboard sin sucursal', async () => {
    render(<Reportes />)
    await screen.findByTestId('kpi-venta')
    expect(dashboard).toHaveBeenCalledWith({ start_date: r7.inicio, end_date: r7.fin })
    expect(screen.getByRole('button', { name: '7 días' }).getAttribute('aria-pressed')).toBe('true')
    expect(screen.getByRole('button', { name: 'Hoy' }).getAttribute('aria-pressed')).toBe('false')
  })

  it('cifras con variación contra el periodo anterior; devoluciones al alza en rojo', async () => {
    render(<Reportes />)
    const venta = await screen.findByTestId('kpi-venta')
    expect(venta.textContent).toContain('$9,000.00')
    expect(variacionDe('kpi-venta')?.textContent).toBe('▲ 20 % vs periodo anterior')
    expect(variacionDe('kpi-tickets')?.textContent).toBe('▲ 17 % vs periodo anterior')
    expect(variacionDe('kpi-promedio')?.textContent).toBe('▲ 3 % vs periodo anterior')
    const dev = variacionDe('kpi-devoluciones')
    expect(dev?.textContent).toBe('▲ 300 % vs periodo anterior')
    expect(dev?.className).toContain('text-dax-danger')
    expect(screen.getByTestId('kpi-devoluciones').textContent).toContain('2 devoluciones')
  })

  it('utilidad bruta con el detalle de lo que tiene costo', async () => {
    render(<Reportes />)
    const u = await screen.findByTestId('kpi-utilidad')
    expect(u.textContent).toContain('$3,000.00')
    expect(u.textContent).toContain('sobre $9,000.00 con costo · $400.00 sin costo')
    expect(variacionDe('kpi-utilidad')?.textContent).toBe('▲ 50 % vs periodo anterior')
  })

  it('oculta la utilidad bruta sin costo o sin permiso', async () => {
    dashboard.mockResolvedValue({ ...DASH, kpis: { ...DASH.kpis, gross_profit: null, prev_gross_profit: null, sales_without_cost: null } })
    render(<Reportes />)
    await screen.findByTestId('kpi-venta')
    expect(screen.queryByTestId('kpi-utilidad')).toBeNull()
    cleanup()
    dashboard.mockResolvedValue({ ...DASH, kpis: { ...DASH.kpis, gross_profit: 0, sales_without_cost: 9400 } })   // nada de lo vendido tiene costo
    render(<Reportes />)
    await screen.findByTestId('kpi-venta')
    expect(screen.queryByTestId('kpi-utilidad')).toBeNull()
  })

  it('"Este mes" manda del 1 a hoy', async () => {
    render(<Reportes />)
    await screen.findByTestId('kpi-venta')
    fireEvent.click(screen.getByRole('button', { name: 'Este mes' }))
    const mes = rangoPreset('mes')
    await waitFor(() => expect(dashboard).toHaveBeenLastCalledWith({ start_date: mes.inicio, end_date: mes.fin }))
    expect(mes.inicio.endsWith('-01')).toBe(true)
  })

  it('tendencia con el periodo anterior y etiquetas en español armadas del rango', async () => {
    render(<Reportes />)
    const l = await screen.findByTestId('grafica-linea')
    expect(l.getAttribute('data-series')).toBe('Este periodo|Periodo anterior')
    const etiquetas = l.getAttribute('data-etiquetas')?.split('|') ?? []
    expect(etiquetas).toHaveLength(7)
    expect(etiquetas).not.toEqual(['a', 'b', 'c', 'd', 'e', 'f', 'g'])
  })

  it('ventas por hora promedia por día del periodo y recorta la ventana', async () => {
    render(<Reportes />)
    const b = await screen.findByTestId('grafica-barras')
    const etiquetas = b.getAttribute('data-etiquetas')?.split('|') ?? []
    const valores = b.getAttribute('data-valores')?.split('|') ?? []
    expect(etiquetas[0]).toBe('9:00')
    expect(etiquetas[etiquetas.length - 1]).toBe('21:00')
    expect(valores[etiquetas.indexOf('12:00')]).toBe('1000')   // 7000 / 7 días
    expect(screen.getByText('Promedio por hora en 7 días')).toBeTruthy()
  })

  it('métodos: efectivo primero con sus cobros, y la dona con las partes', async () => {
    render(<Reportes />)
    const dona = await screen.findByTestId('grafica-dona')
    expect(dona.getAttribute('data-partes')).toBe('Efectivo=5000|Tarjeta=4000')
    const metodos = screen.getAllByTestId('metodo').map((li) => li.textContent)
    expect(metodos[0]).toContain('Efectivo')
    expect(metodos[0]).toContain('40 cobros')
    expect(metodos[0]).toContain('$5,000.00')
  })

  it('lo más vendido: producto, piezas e importe', async () => {
    render(<Reportes />)
    const top = await screen.findByTestId('top')
    expect(top.textContent).toContain('Blusa roja')
    expect(top.textContent).toContain('14 piezas')
    expect(top.textContent).toContain('$1,400.00')
  })

  it('con selector y dos sucursales: selector, sección sin la bodega, y filtra al elegir', async () => {
    render(<Reportes conSucursales />)
    await screen.findByTestId('kpi-venta')
    expect(commandCenterStats).toHaveBeenCalledWith({ start_date: r7.inicio, end_date: r7.fin })
    const selector = await screen.findByLabelText('Sucursal')
    const suc = await screen.findByTestId('sucursales')
    expect(within(suc).getByTestId('grafica-barras-h').getAttribute('data-etiquetas')).toBe('Roma|Condesa')
    expect(suc.textContent).not.toContain('Bodega')
    fireEvent.change(selector, { target: { value: '2' } })
    await waitFor(() => expect(dashboard).toHaveBeenLastCalledWith({ start_date: r7.inicio, end_date: r7.fin, branch_id: 2 }))
  })

  it('con selector pero una sola sucursal no hay selector ni sección', async () => {
    getBranches.mockResolvedValue([SUC(1, 'Roma')])
    commandCenterStats.mockResolvedValue({ ...CC, branches: [CC.branches[0], CC.branches[2]] })
    render(<Reportes conSucursales />)
    await screen.findByTestId('kpi-venta')
    await espera()
    expect(screen.queryByLabelText('Sucursal')).toBeNull()
    expect(screen.queryByTestId('sucursales')).toBeNull()
  })

  it('sin selector no pide sucursales ni el centro de mando', async () => {
    render(<Reportes />)
    await screen.findByTestId('kpi-venta')
    expect(getBranches).not.toHaveBeenCalled()
    expect(commandCenterStats).not.toHaveBeenCalled()
    expect(screen.queryByLabelText('Sucursal')).toBeNull()
    expect(screen.queryByTestId('sucursales')).toBeNull()
  })

  it('Exportar CSV manda el rango vigente', async () => {
    render(<Reportes />)
    await screen.findByTestId('kpi-venta')
    fireEvent.click(screen.getByRole('button', { name: /Exportar CSV/ }))
    await waitFor(() => expect(exportCsv).toHaveBeenCalledWith({ start_date: r7.inicio, end_date: r7.fin, branch_id: undefined }))
  })

  it('un rango invertido no llama al servidor y avisa', async () => {
    render(<Reportes />)
    await screen.findByTestId('kpi-venta')
    fireEvent.change(screen.getByLabelText('Desde'), { target: { value: '2026-10-20' } })
    fireEvent.change(screen.getByLabelText('Hasta'), { target: { value: '2026-10-19' } })
    fireEvent.click(screen.getByRole('button', { name: 'Aplicar' }))
    expect(screen.getByRole('alert').textContent).toContain('La fecha final no puede ser anterior a la inicial')
    expect(dashboard).toHaveBeenCalledTimes(1)
  })

  it('si el dashboard falla, enseña el detalle del servidor', async () => {
    dashboard.mockRejectedValue({ response: { data: { detail: 'end_date no puede ser anterior a start_date' } } })
    render(<Reportes />)
    expect((await screen.findByRole('alert')).textContent).toContain('end_date no puede ser anterior a start_date')
  })
})
