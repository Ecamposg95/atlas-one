// frontend/src/pages/hq/__tests__/InicioBasico.test.tsx
// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { render, screen, cleanup } from '@testing-library/react'

const { inicioBasico, valorInventario } = vi.hoisted(() => ({ inicioBasico: vi.fn(), valorInventario: vi.fn() }))
vi.mock('../../../api/reports', () => ({ reportsApi: { inicioBasico, valorInventario } }))

import { InicioBasico } from '../InicioBasico'

// La forma exacta de la Tarea 3.
const DATOS = {
  branch_id: null,
  hoy: { desde: '2026-10-19', hasta: '2026-10-19', total: 1234.5, tickets: 12 },
  ayer: { desde: '2026-10-18', hasta: '2026-10-18', total: 800, tickets: 1 },
  semana: { desde: '2026-10-13', hasta: '2026-10-19', total: 9000, tickets: 70 },
  por_metodo_hoy: { CARD: 234.5, CASH: 1000 },
  top_semana: [{ nombre: 'Blusa roja', cantidad: 14, total: 1400 }],
  poca_existencia: { umbral: 3, productos: [{ variant_id: 'v1', nombre: 'Falda negra', sku: 'FAL-1', existencia: 1 }] },
  corte: { estado: 'abierto', cajera: 'Mirna', abierto_en: '2026-10-19T15:00:00+00:00', cerrado_en: null, efectivo_esperado: 1500, efectivo_contado: null },
}
const VALUACION = {
  agrupar: 'sucursal', branch_id: null, ve_costo: true, grupos: [],
  totales: { piezas: 10, skus: 2, valor_venta: 5000, valor_costo: 2000, piezas_sin_costo: 0, skus_sin_costo: 0 },
}
const pintar = () => render(<MemoryRouter><InicioBasico /></MemoryRouter>)

beforeEach(() => {
  inicioBasico.mockReset().mockResolvedValue(DATOS)
  valorInventario.mockReset().mockResolvedValue(VALUACION)
})
afterEach(cleanup)

describe('InicioBasico', () => {
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
    inicioBasico.mockResolvedValue({ ...DATOS, corte: { ...DATOS.corte, estado: 'cerrado', cerrado_en: '2026-10-19T23:00:00+00:00', efectivo_esperado: null, efectivo_contado: 850 } })
    pintar()
    expect((await screen.findByTestId('corte')).textContent).toContain('$850.00')
    cleanup()
    inicioBasico.mockResolvedValue({ ...DATOS, corte: { estado: 'sin_turno', cajera: null, abierto_en: null, cerrado_en: null, efectivo_esperado: null, efectivo_contado: null } })
    pintar()
    expect((await screen.findByTestId('corte')).textContent).toContain('Nadie ha abierto turno')
  })

  it('si el resumen falla, el mensaje del servidor y la tarjeta del valor siguen', async () => {
    inicioBasico.mockRejectedValue({ response: { data: { detail: 'Solo administrador, dueño o gerente pueden ver el inicio' } } })
    pintar()
    expect(await screen.findByText('Solo administrador, dueño o gerente pueden ver el inicio')).toBeTruthy()
    expect(await screen.findByTestId('valor-tienda')).toBeTruthy()
  })
})
