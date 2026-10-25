// frontend/src/pages/hq/__tests__/Inicio.test.tsx
// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { render, screen, cleanup, within } from '@testing-library/react'

const { inicio, valorInventario } = vi.hoisted(() => ({ inicio: vi.fn(), valorInventario: vi.fn() }))
vi.mock('../../../api/reports', () => ({ reportsApi: { inicio, valorInventario } }))
// El módulo perezoso de gráficas se sustituye por un marcador: aquí se prueba
// CUÁNDO se monta (perfil), no el dibujo (eso es de InicioGraficas.test.tsx).
vi.mock('../InicioGraficas', () => ({
  InicioGraficas: ({ seccion }: { seccion: string }) => <div data-testid={`grafica-${seccion}`} />,
}))

import { Inicio } from '../Inicio'
import { useEnabledModulesStore } from '../../../store/enabledModulesStore'

const dia = (n: number) => `2026-10-${String(n).padStart(2, '0')}`
// La forma exacta de GET /reports/inicio sin `completo` (modo básico).
const DATOS = {
  branch_id: null,
  hoy: { desde: dia(19), hasta: dia(19), total: 1234.5, devuelto: 0, tickets: 12 },
  ayer: { desde: dia(18), hasta: dia(18), total: 800, devuelto: 0, tickets: 1 },
  semana: { desde: dia(13), hasta: dia(19), total: 9000, devuelto: 0, tickets: 70 },
  por_metodo_hoy: { CARD: 234.5, CASH: 1000 },
  top_semana: [{ nombre: 'Blusa roja', cantidad: 14, total: 1400 }],
  poca_existencia: { umbral: 3, productos: [{ variant_id: 'v1', nombre: 'Falda negra', sku: 'FAL-1', existencia: 1 }] },
  corte: { estado: 'abierto', cajera: 'Mirna', abierto_en: '2026-10-19T15:00:00+00:00', cerrado_en: null, efectivo_esperado: 1500, efectivo_contado: null },
  sin_movimiento: null, pendientes: null, sucursales: null, utilidad_bruta_hoy: null, venta_sin_costo_hoy: null,
  tendencia: null, por_hora_hoy: null, utilidad_bruta_ayer: null,
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
    { branch_id: 1, nombre: 'Roma', ventas_hoy: 1000, devuelto_hoy: 0, tickets_hoy: 9, corte: DATOS.corte, poca_existencia: 2 },
    { branch_id: 2, nombre: 'Condesa', ventas_hoy: 234.5, devuelto_hoy: 0, tickets_hoy: 3, corte: { ...DATOS.corte, estado: 'sin_turno' }, poca_existencia: 0 },
  ],
  utilidad_bruta_hoy: 400, venta_sin_costo_hoy: 234.5, utilidad_bruta_ayer: 300,
  // 7 días terminando hoy (antier = índice 4 → 1000) y los 7 previos (suman 7500).
  tendencia: {
    dias: [500, 900, 1100, 1300, 1000, 800, 1234.5].map((neta, i) => ({ fecha: dia(13 + i), neta, tickets: i + 1 })),
    anterior: [1000, 1000, 1000, 1000, 1000, 1000, 1500].map((neta, i) => ({ fecha: dia(6 + i), neta, tickets: 1 })),
  },
  por_hora_hoy: Array.from({ length: 24 }, (_, h) => ({ hora: h, neta: h === 12 ? 1234.5 : 0, tickets: h === 12 ? 12 : 0 })),
}
const VALUACION = {
  agrupar: 'sucursal', branch_id: null, ve_costo: true, grupos: [],
  totales: { piezas: 10, skus: 2, valor_venta: 5000, valor_costo: 2000, piezas_sin_costo: 0, skus_sin_costo: 0 },
}
const pintar = () => render(<MemoryRouter><Inicio /></MemoryRouter>)
const perfil = (perfilUi: 'basico' | 'completo') => useEnabledModulesStore.setState({ loaded: true, perfilUi })
const variacionDe = (testId: string) => within(screen.getByTestId(testId)).queryByTestId('variacion')

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
    for (const texto of ['Ver corte →', 'Ver productos →', 'Ver desglose →']) {
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

  it('hoy con devoluciones dice cuánto se devolvió', async () => {
    inicio.mockResolvedValue({ ...DATOS, hoy: { ...DATOS.hoy, total: 1194.5, devuelto: 40 } })
    pintar()
    expect((await screen.findByTestId('cifra-hoy')).textContent).toContain('12 ventas · $40.00 devuelto')
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

  it('en básico no monta ninguna gráfica (el chunk charts no baja) ni muestra variaciones', async () => {
    pintar()
    await screen.findByTestId('cifra-hoy')
    await new Promise((r) => setTimeout(r, 20))
    expect(document.querySelector('[data-testid^="grafica-"]')).toBeNull()
    expect(screen.queryByText('Cargando gráfica…')).toBeNull()
    // Spec §3.1: en básico solo cambian las cifras a netas; ninguna lleva variación.
    expect(document.querySelector('[data-testid="variacion"]')).toBeNull()
  })

  it('en completo pide completo=true y pinta las tres secciones y la utilidad', async () => {
    perfil('completo')
    inicio.mockResolvedValue(COMPLETO)
    pintar()
    await screen.findByTestId('cifra-hoy')
    expect(inicio).toHaveBeenCalledWith({ completo: true })
    expect(screen.getByTestId('cifra-utilidad').textContent).toContain('$400.00')
    expect(screen.getByTestId('cifra-utilidad').textContent).toContain('sobre $1,000.00 con costo · $234.50 vendidos sin costo')
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

  it('en completo monta las cuatro gráficas y conserva la lista de métodos y la caja', async () => {
    perfil('completo')
    inicio.mockResolvedValue(COMPLETO)
    pintar()
    for (const s of ['tendencia', 'metodos', 'horas', 'sucursales']) expect(await screen.findByTestId(`grafica-${s}`)).toBeTruthy()
    expect(screen.getAllByTestId('metodo')).toHaveLength(2)
    expect(screen.getByTestId('corte').textContent).toContain('Turno abierto')
    expect(screen.getByText('Ver corte →').className).toContain('max-md:min-h-[44px]')
  })

  it('variaciones: hoy vs ayer, ayer vs antier, 7 días vs semana anterior, utilidad vs ayer', async () => {
    perfil('completo')
    inicio.mockResolvedValue(COMPLETO)
    pintar()
    await screen.findByTestId('cifra-hoy')
    expect(variacionDe('cifra-hoy')?.textContent).toBe('▲ 54 % vs ayer')                // 1234.5 vs 800
    expect(variacionDe('cifra-ayer')?.textContent).toBe('▼ 20 % vs antier')             // 800 vs 1000
    expect(variacionDe('cifra-semana')?.textContent).toBe('▲ 20 % vs semana anterior')  // 9000 vs 7500
    expect(variacionDe('cifra-utilidad')?.textContent).toBe('▲ 33 % vs ayer')           // 400 vs 300
  })

  it('completo sin tendencia (servidor viejo) cae al diseño sin gráficas', async () => {
    perfil('completo')
    inicio.mockResolvedValue({ ...COMPLETO, tendencia: null, por_hora_hoy: null })
    pintar()
    await screen.findByTestId('cifra-hoy')
    await new Promise((r) => setTimeout(r, 20))
    expect(screen.queryByTestId('grafica-tendencia')).toBeNull()
    expect(screen.queryByTestId('grafica-horas')).toBeNull()
    expect(screen.getAllByTestId('metodo')).toHaveLength(2)
    expect(variacionDe('cifra-ayer')).toBeNull()
  })

  it('completo con una sola sucursal y nada pendiente: sin sección de sucursales y "Nada pendiente"', async () => {
    perfil('completo')
    inicio.mockResolvedValue({ ...COMPLETO, sucursales: null, pendientes: { devoluciones: 0, turnos_abiertos: 0, diferencias_caja: [] } })
    pintar()
    await screen.findByTestId('cifra-hoy')
    expect(screen.queryByTestId('sucursales')).toBeNull()
    expect(screen.queryByTestId('grafica-sucursales')).toBeNull()
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

  it('en básico los enlaces van a Productos y Mis ventas, nunca a pantallas HQ escondidas', async () => {
    pintar()
    await screen.findByTestId('cifra-hoy')
    const hrefs = Array.from(document.querySelectorAll('a')).map((a) => a.getAttribute('href'))
    expect(hrefs).toContain('/products')
    expect(hrefs).toContain('/sales')
    expect(hrefs.some((h) => h?.startsWith('/hq/inventory') || h?.startsWith('/hq/sales'))).toBe(false)
    expect(screen.getByText('Falda negra').closest('a')?.getAttribute('href')).toBe('/products')
  })

  it('en completo los mismos enlaces abren Existencias y Ventas HQ', async () => {
    perfil('completo')
    inicio.mockResolvedValue(COMPLETO)
    pintar()
    await screen.findByTestId('cifra-hoy')
    expect(screen.getByText('Falda negra').closest('a')?.getAttribute('href')).toBe('/hq/inventory?q=FAL-1&variant=v1')
    expect(screen.getByText('Ver ventas →').getAttribute('href')).toBe('/hq/sales')
  })
})
