// @vitest-environment jsdom
import { describe, it, expect, afterEach } from 'vitest'
import { render, screen, cleanup, fireEvent } from '@testing-library/react'
import { SalesHeatmap, escalon } from '../Heatmap'

afterEach(cleanup)

const DATA = [
  { day: 1, hour: 12, amount: 1000, tickets: 4 },   // lunes 12:00, el máximo
  { day: 5, hour: 18, amount: 300, tickets: 1 },    // viernes 18:00, 30 %
]

describe('SalesHeatmap', () => {
  it('siete filas con el lunes arriba y la ventana de horas pedida', () => {
    const { container } = render(<SalesHeatmap data={DATA} hourStart={10} hourEnd={20} />)
    const filas = container.querySelectorAll('tbody tr')
    expect(filas).toHaveLength(7)
    expect(filas[0].querySelector('td')?.textContent).toBe('L')
    expect(filas[6].querySelector('td')?.textContent).toBe('D')
    expect(container.querySelectorAll('thead th')).toHaveLength(12)   // 1 vacío + 10..20
  })

  it('la intensidad es el dato: 100 % el máximo, 40 % para 0.3 del máximo, 0 sin venta', () => {
    render(<SalesHeatmap data={DATA} />)
    expect(screen.getByTestId('celda-1-12').getAttribute('data-intensidad')).toBe('100')
    expect(screen.getByTestId('celda-5-18').getAttribute('data-intensidad')).toBe('40')
    const vacia = screen.getByTestId('celda-2-12')
    expect(vacia.getAttribute('data-intensidad')).toBe('0')
    expect(vacia.className).toContain('bg-dax-elevated')
    expect(screen.getByTestId('celda-1-12').getAttribute('style')).toContain('--dax-success')
  })

  it('escalon reparte en cinco pasos', () => {
    expect([0, 0.1, 0.3, 0.5, 0.7, 1].map(escalon)).toEqual([0, 1, 2, 3, 4, 5])
  })

  it('al pasar el ratón enseña día, hora, importe y tickets', () => {
    render(<SalesHeatmap data={DATA} />)
    fireEvent.mouseEnter(screen.getByTestId('celda-1-12'))
    const tip = screen.getByRole('tooltip')
    expect(tip.textContent).toContain('Lunes · 12:00')
    expect(tip.textContent).toContain('$1,000.00')
    expect(tip.textContent).toContain('4 tickets')
    fireEvent.mouseLeave(screen.getByTestId('celda-1-12'))
    expect(screen.queryByRole('tooltip')).toBeNull()
  })

  it('no usa colores fijos (slate/emerald/hex)', () => {
    const { container } = render(<SalesHeatmap data={DATA} />)
    expect(container.innerHTML).not.toMatch(/slate-|emerald-|#[0-9a-f]{6}/i)
  })
})
