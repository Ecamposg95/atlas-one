// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, cleanup, fireEvent } from '@testing-library/react'

// jsdom no tiene canvas: se sustituye <Line> por un stub que expone las series
// recibidas. Lo que se prueba es qué datos construye TrendChart, no el dibujo.
vi.mock('react-chartjs-2', () => ({
  Line: (props: { data: { datasets: { label?: string }[] } }) => (
    <div data-testid="line" data-series={props.data.datasets.map((d) => d.label).join('|')} />
  ),
}))

import { TrendChart, type TrendPoint } from '../TrendChart'

const puntos: TrendPoint[] = [
  { date: '2026-10-01', label: '01', revenue: 100, ma7: 90, sales: 3 },
  { date: '2026-10-02', label: '02', revenue: 150, ma7: 110, sales: 5 },
]

afterEach(cleanup)

describe('TrendChart (chart.js)', () => {
  it('sin datos muestra el aviso y no pinta gráfica', () => {
    render(<TrendChart data={[]} />)
    expect(screen.getByText('Sin datos de tendencia.')).toBeTruthy()
    expect(screen.queryByTestId('line')).toBeNull()
  })

  it('por defecto pinta ventas diarias y promedio móvil 7d', () => {
    render(<TrendChart data={puntos} />)
    expect(screen.getByTestId('line').getAttribute('data-series')).toBe('Ventas diarias|Promedio móvil 7d')
  })

  it('con toggles, activar "Sales" agrega la serie de tickets', () => {
    render(<TrendChart data={puntos} salesSeries={puntos} showSeriesToggles />)
    fireEvent.click(screen.getByRole('button', { name: 'Sales' }))
    expect(screen.getByTestId('line').getAttribute('data-series')).toBe('Ventas diarias|Promedio móvil 7d|Tickets')
  })

  it('apagar "Revenue" deja solo lo demás', () => {
    render(<TrendChart data={puntos} salesSeries={puntos} showSeriesToggles />)
    fireEvent.click(screen.getByRole('button', { name: 'Revenue' }))
    fireEvent.click(screen.getByRole('button', { name: 'Sales' }))
    expect(screen.getByTestId('line').getAttribute('data-series')).toBe('Tickets')
  })
})
