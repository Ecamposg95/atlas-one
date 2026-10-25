// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'

// Stubs del kit: exponen etiquetas, valores y colores; el dibujo lo prueba el kit.
vi.mock('../../../components/graficas', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../components/graficas')>()),
  GraficaLinea: (p: { etiquetas: string[]; series: { nombre: string; valores: number[]; comparativo?: boolean }[] }) => (
    <div data-testid="linea" data-etiquetas={p.etiquetas.join('|')}
      data-series={p.series.map((s) => `${s.nombre}${s.comparativo ? '*' : ''}=${s.valores.join(',')}`).join('|')} />
  ),
  GraficaBarras: (p: { etiquetas: string[]; valores: number[]; resaltar?: number | null; horizontal?: boolean }) => (
    <div data-testid={p.horizontal ? 'barras-h' : 'barras'} data-etiquetas={p.etiquetas.join('|')}
      data-valores={p.valores.join(',')} data-resaltar={String(p.resaltar)} />
  ),
  GraficaDona: (p: { partes: { nombre: string; valor: number; color: string }[]; centro?: React.ReactNode }) => (
    <div data-testid="dona" data-partes={p.partes.map((x) => `${x.nombre}=${x.valor}`).join('|')}>{p.centro}</div>
  ),
}))

import { InicioGraficas } from '../InicioGraficas'
import type { Inicio } from '../../../api/reports'

const dia = (n: number) => `2026-10-${String(n).padStart(2, '0')}`
const corte = { estado: 'sin_turno' as const, cajera: null, abierto_en: null, cerrado_en: null, efectivo_esperado: null, efectivo_contado: null }
const DATOS: Inicio = {
  branch_id: null,
  hoy: { desde: dia(19), hasta: dia(19), total: 1234.5, devuelto: 0, tickets: 12 },
  ayer: { desde: dia(18), hasta: dia(18), total: 800, devuelto: 0, tickets: 1 },
  semana: { desde: dia(13), hasta: dia(19), total: 9000, devuelto: 0, tickets: 70 },
  por_metodo_hoy: { CARD: 234.5, CASH: 1000, MIXED: -10 },
  top_semana: [], poca_existencia: { umbral: 3, productos: [] }, corte,
  sin_movimiento: null, pendientes: null, utilidad_bruta_hoy: null, venta_sin_costo_hoy: null, utilidad_bruta_ayer: null,
  sucursales: [
    { branch_id: 1, nombre: 'Roma', ventas_hoy: 1000, devuelto_hoy: 0, tickets_hoy: 9, corte, poca_existencia: 0 },
    { branch_id: 2, nombre: 'Condesa', ventas_hoy: 3000, devuelto_hoy: 0, tickets_hoy: 3, corte, poca_existencia: 0 },
  ],
  tendencia: {
    dias: [500, 900, 1100, 1300, 1000, 800, 1234.5].map((neta, i) => ({ fecha: dia(13 + i), neta, tickets: 1 })),
    anterior: [1, 2, 3, 4, 5, 6, 7].map((neta, i) => ({ fecha: dia(6 + i), neta, tickets: 1 })),
  },
  por_hora_hoy: Array.from({ length: 24 }, (_, h) => ({ hora: h, neta: h === 7 ? 100 : h === 12 ? 1134.5 : 0, tickets: 0 })),
}

afterEach(cleanup)

describe('InicioGraficas', () => {
  it('tendencia: siete etiquetas de día y la semana anterior como comparativo', () => {
    render(<InicioGraficas seccion="tendencia" datos={DATOS} />)
    const l = screen.getByTestId('linea')
    expect(l.getAttribute('data-etiquetas')?.split('|')).toHaveLength(7)
    expect(l.getAttribute('data-series')).toBe('Estos 7 días=500,900,1100,1300,1000,800,1234.5|Semana anterior*=1,2,3,4,5,6,7')
  })

  it('métodos: efectivo, tarjeta y lo demás con nombre legible y el total de hoy al centro', () => {
    render(<InicioGraficas seccion="metodos" datos={DATOS} />)
    const d = screen.getByTestId('dona')
    expect(d.getAttribute('data-partes')).toBe('Efectivo=1000|Tarjeta=234.5|MIXED=-10')
    expect(d.textContent).toContain('$1,224.50')
  })

  it('horas: recorta la ventana a la primera venta (7) .. 21 y resalta la hora actual', () => {
    render(<InicioGraficas seccion="horas" datos={DATOS} horaActual={12} />)
    const b = screen.getByTestId('barras')
    const etiquetas = b.getAttribute('data-etiquetas')?.split('|') ?? []
    expect(etiquetas[0]).toBe('7:00')
    expect(etiquetas[etiquetas.length - 1]).toBe('21:00')
    expect(b.getAttribute('data-resaltar')).toBe(String(12 - 7))
  })

  it('horas: fuera de la ventana no resalta nada', () => {
    render(<InicioGraficas seccion="horas" datos={DATOS} horaActual={23} />)
    expect(screen.getByTestId('barras').getAttribute('data-resaltar')).toBe('null')
  })

  it('sucursales: barras horizontales ordenadas por venta', () => {
    render(<InicioGraficas seccion="sucursales" datos={DATOS} />)
    const b = screen.getByTestId('barras-h')
    expect(b.getAttribute('data-etiquetas')).toBe('Condesa|Roma')
    expect(b.getAttribute('data-valores')).toBe('3000,1000')
  })

  it('sin tendencia ni horas (servidor viejo) no pinta nada', () => {
    const { container } = render(<InicioGraficas seccion="tendencia" datos={{ ...DATOS, tendencia: null }} />)
    expect(container.innerHTML).toBe('')
  })
})
