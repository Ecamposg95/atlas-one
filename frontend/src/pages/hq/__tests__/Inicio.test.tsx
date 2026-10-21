// frontend/src/pages/hq/__tests__/Inicio.test.tsx
// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { render, screen, cleanup } from '@testing-library/react'

const { inicio, valorInventario } = vi.hoisted(() => ({ inicio: vi.fn(), valorInventario: vi.fn() }))
vi.mock('../../../api/reports', () => ({ reportsApi: { inicio, valorInventario } }))

import { Inicio } from '../Inicio'
import { useEnabledModulesStore } from '../../../store/enabledModulesStore'

// La forma exacta de GET /reports/inicio sin `completo` (modo básico).
const DATOS = {
  branch_id: null,
  hoy: { desde: '2026-10-19', hasta: '2026-10-19', total: 1234.5, tickets: 12 },
  ayer: { desde: '2026-10-18', hasta: '2026-10-18', total: 800, tickets: 1 },
  semana: { desde: '2026-10-13', hasta: '2026-10-19', total: 9000, tickets: 70 },
  por_metodo_hoy: { CARD: 234.5, CASH: 1000 },
  top_semana: [{ nombre: 'Blusa roja', cantidad: 14, total: 1400 }],
  poca_existencia: { umbral: 3, productos: [{ variant_id: 'v1', nombre: 'Falda negra', sku: 'FAL-1', existencia: 1 }] },
  corte: { estado: 'abierto', cajera: 'Mirna', abierto_en: '2026-10-19T15:00:00+00:00', cerrado_en: null, efectivo_esperado: 1500, efectivo_contado: null },
  sin_movimiento: null, pendientes: null, sucursales: null, utilidad_bruta_hoy: null,
}
// Lo que trae `completo=true` para una org de paga con dos sucursales.
const COMPLETO = {
  ...DATOS,
  sin_movimiento: { dias: 30, productos: [{ variant_id: 'v9', nombre: 'Abrigo largo', sku: 'ABR-1', existencia: 3, importe_venta: 2700 }] },
  pendientes: {
    devoluciones: 2, turnos_abiertos: 1,
    diferencias_caja: [{ session_id: 7, sucursal: 'Roma', cajera: 'Lupita', cerrado_en: '2026-10-18T23:00:00+00:00', esperado: 500, contado: 480, diferencia: -20 }],
  },
  sucursales: [
    { branch_id: 1, nombre: 'Roma', ventas_hoy: 1000, tickets_hoy: 9, corte: DATOS.corte, poca_existencia: 2 },
    { branch_id: 2, nombre: 'Condesa', ventas_hoy: 234.5, tickets_hoy: 3, corte: { ...DATOS.corte, estado: 'sin_turno' }, poca_existencia: 0 },
  ],
  utilidad_bruta_hoy: 400,
}
const VALUACION = {
  agrupar: 'sucursal', branch_id: null, ve_costo: true, grupos: [],
  totales: { piezas: 10, skus: 2, valor_venta: 5000, valor_costo: 2000, piezas_sin_costo: 0, skus_sin_costo: 0 },
}
const pintar = () => render(<MemoryRouter><Inicio /></MemoryRouter>)
const perfil = (perfilUi: 'basico' | 'completo') => useEnabledModulesStore.setState({ loaded: true, perfilUi })

beforeEach(() => {
  perfil('basico')
  inicio.mockReset().mockResolvedValue(DATOS)
  valorInventario.mockReset().mockResolvedValue(VALUACION)
})
afterEach(() => { cleanup(); useEnabledModulesStore.getState().reset() })

describe('Inicio', () => {
  it('los enlaces de las tarjetas miden 44px en teléfono', async () => {
    pintar()
    await screen.findByTestId('cifra-hoy')
    for (const texto of ['Ver corte →', 'Ver existencias →', 'Ver desglose →']) {
      expect(screen.getByText(texto).className).toContain('max-md:min-h-[44px]')
    }
  })

  it('vendido hoy, ayer y en 7 días', async () => {
    pintar()
    const hoy = await screen.findByTestId('cifra-hoy')
    expect(hoy.textContent).toContain('$1,234.50')
    expect(hoy.textContent).toContain('12 ventas')
    expect(screen.getByTestId('cifra-ayer').textContent).toContain('1 venta')
    expect(screen.getByTestId('cifra-semana').textContent).toContain('$9,000.00')
  })

  it('cobros de hoy con efectivo primero', async () => {
    pintar()
    await screen.findByTestId('cifra-hoy')
    const metodos = screen.getAllByTestId('metodo').map((li) => li.textContent)
    expect(metodos[0]).toContain('Efectivo')
    expect(metodos[1]).toContain('Tarjeta')
  })

  it('caja, lo que se acaba, lo más vendido y el valor de la tienda', async () => {
    pintar()
    const corte = await screen.findByTestId('corte')
    expect(corte.textContent).toContain('Turno abierto')
    expect(corte.textContent).toContain('Mirna')
    expect(corte.textContent).toContain('$1,500.00')
    expect(screen.getByText('Falda negra')).toBeTruthy()
    expect(screen.getByText('1 pieza')).toBeTruthy()
    expect(screen.getByText('Blusa roja')).toBeTruthy()
    expect(await screen.findByTestId('valor-tienda')).toBeTruthy()
  })

  it('turno cerrado y sin turno', async () => {
    inicio.mockResolvedValue({ ...DATOS, corte: { ...DATOS.corte, estado: 'cerrado', cerrado_en: '2026-10-19T23:00:00+00:00', efectivo_esperado: null, efectivo_contado: 850 } })
    pintar()
    expect((await screen.findByTestId('corte')).textContent).toContain('$850.00')
    cleanup()
    inicio.mockResolvedValue({ ...DATOS, corte: { estado: 'sin_turno', cajera: null, abierto_en: null, cerrado_en: null, efectivo_esperado: null, efectivo_contado: null } })
    pintar()
    expect((await screen.findByTestId('corte')).textContent).toContain('Nadie ha abierto turno')
  })

  it('si el resumen falla, el mensaje del servidor y la tarjeta del valor siguen', async () => {
    inicio.mockRejectedValue({ response: { data: { detail: 'Solo administrador, dueño o gerente pueden ver el inicio' } } })
    pintar()
    expect(await screen.findByText('Solo administrador, dueño o gerente pueden ver el inicio')).toBeTruthy()
    expect(await screen.findByTestId('valor-tienda')).toBeTruthy()
  })

  it('en básico pide completo=false y no pinta No se mueve, Pendientes ni Sucursales', async () => {
    pintar()
    await screen.findByTestId('cifra-hoy')
    expect(inicio).toHaveBeenCalledWith({ completo: false })
    expect(screen.queryByText(/No se mueve/)).toBeNull()
    expect(screen.queryByText('Pendientes')).toBeNull()
    expect(screen.queryByTestId('sucursales')).toBeNull()
    expect(screen.queryByTestId('cifra-utilidad')).toBeNull()
  })

  it('en completo pide completo=true y pinta las tres secciones y la utilidad', async () => {
    perfil('completo')
    inicio.mockResolvedValue(COMPLETO)
    pintar()
    await screen.findByTestId('cifra-hoy')
    expect(inicio).toHaveBeenCalledWith({ completo: true })
    expect(screen.getByTestId('cifra-utilidad').textContent).toContain('$400.00')
    expect(screen.getByText(/No se mueve \(sin venta en 30 días\)/)).toBeTruthy()
    expect(screen.getByText('Abrigo largo').closest('a')?.getAttribute('href')).toBe('/hq/inventory?q=ABR-1&variant=v9')
    expect(screen.getByText('2 devoluciones por aprobar →').getAttribute('href')).toBe('/hq/returns')
    expect(screen.getByText(/1 turno abierto desde hace más de un día/)).toBeTruthy()
    expect(screen.getByText('Lupita')).toBeTruthy()
    const sucursales = screen.getByTestId('sucursales')
    expect(sucursales.textContent).toContain('Roma')
    expect(sucursales.textContent).toContain('2 productos se están acabando')
    expect(sucursales.querySelector('a')?.getAttribute('href')).toBe('/hq/branches/1')
  })

  it('completo con una sola sucursal y nada pendiente: sin sección de sucursales y "Nada pendiente"', async () => {
    perfil('completo')
    inicio.mockResolvedValue({ ...COMPLETO, sucursales: null, pendientes: { devoluciones: 0, turnos_abiertos: 0, diferencias_caja: [] } })
    pintar()
    await screen.findByTestId('cifra-hoy')
    expect(screen.queryByTestId('sucursales')).toBeNull()
    expect(screen.getByText('Nada pendiente.')).toBeTruthy()
  })

  it('espera al contexto antes de pedir (no manda completo=true por el default del store)', async () => {
    useEnabledModulesStore.setState({ loaded: false, perfilUi: 'completo', loading: true })
    pintar()
    await new Promise((r) => setTimeout(r, 20))
    expect(inicio).not.toHaveBeenCalled()
    perfil('basico')
    await screen.findByTestId('cifra-hoy')
    expect(inicio).toHaveBeenCalledWith({ completo: false })
  })
})
