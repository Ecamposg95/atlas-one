// @vitest-environment jsdom
import { describe, it, expect, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { ValorTiendaCard, type ValorTiendaCardProps } from '../ValorTiendaCard'

afterEach(cleanup)

const base: ValorTiendaCardProps = {
  valorVenta: 10200, valorCosto: 2000, piezas: 19, piezasSinCosto: 14, skusSinCosto: 2,
}
const pinta = (props: Partial<ValorTiendaCardProps> = {}) =>
  render(<MemoryRouter><ValorTiendaCard {...base} {...props} /></MemoryRouter>)

describe('ValorTiendaCard', () => {
  it('con piezas sin costo la cifra grande es la de venta y avisa cuántas faltan', () => {
    pinta()
    expect(screen.getByTestId('valor-principal').textContent).toBe('$10,200.00')
    expect(screen.getByText('Valor a precio de venta')).toBeTruthy()
    expect(screen.getByTestId('valor-costo').textContent).toBe('$2,000.00')
    expect(screen.getByRole('status').textContent).toContain('14 piezas sin costo')
    expect(screen.getByRole('status').textContent).toContain('2 SKUs')
  })

  it('con costo completo la cifra grande es el costo y la venta queda al lado', () => {
    pinta({ piezasSinCosto: 0, skusSinCosto: 0 })
    expect(screen.getByTestId('valor-principal').textContent).toBe('$2,000.00')
    expect(screen.getByText('Valor a costo')).toBeTruthy()
    expect(screen.getByTestId('valor-venta').textContent).toBe('$10,200.00')
    expect(screen.queryByRole('status')).toBeNull()
  })

  it('sin costo visible (gerente) solo muestra venta y piezas, sin aviso', () => {
    pinta({ valorCosto: null })
    expect(screen.getByTestId('valor-principal').textContent).toBe('$10,200.00')
    expect(screen.queryByTestId('valor-costo')).toBeNull()
    expect(screen.queryByRole('status')).toBeNull()
    expect(screen.getByText('19 piezas')).toBeTruthy()
  })

  it('una sola pieza va en singular', () => {
    pinta({ piezas: 1, piezasSinCosto: 1, skusSinCosto: 1 })
    expect(screen.getByText('1 pieza')).toBeTruthy()
    expect(screen.getByRole('status').textContent).toContain('1 pieza sin costo (1 SKU)')
  })

  it('enlaza al desglose', () => {
    pinta()
    const link = screen.getByRole('link', { name: /ver desglose/i })
    expect(link.getAttribute('href')).toBe('/hq/valor-inventario')
  })

  it('el error gana a los números y cargando no pinta cifras', () => {
    pinta({ error: 'No se pudo calcular el valor de la tienda.' })
    expect(screen.getByText('No se pudo calcular el valor de la tienda.')).toBeTruthy()
    expect(screen.queryByTestId('valor-principal')).toBeNull()
    cleanup()
    pinta({ cargando: true })
    expect(screen.getByText('Calculando…')).toBeTruthy()
    expect(screen.queryByTestId('valor-principal')).toBeNull()
  })
})
