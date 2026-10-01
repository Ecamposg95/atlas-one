// @vitest-environment jsdom
import { describe, it, expect, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import { ListaTarjetas } from '../ListaTarjetas'

afterEach(cleanup)

describe('ListaTarjetas', () => {
  it('renderiza todos los hijos dentro de space-y-2', () => {
    const { container } = render(
      <ListaTarjetas>{Array.from({ length: 60 }, (_, i) => <div key={i} data-testid="hijo">{i}</div>)}</ListaTarjetas>,
    )
    expect(screen.getAllByTestId('hijo')).toHaveLength(60)
    expect((container.firstElementChild as HTMLElement).classList.contains('space-y-2')).toBe(true)
  })
  it('vacio muestra textoVacio y no los hijos', () => {
    render(<ListaTarjetas vacio textoVacio="Sin ventas en el periodo"><div>hijo</div></ListaTarjetas>)
    expect(screen.getByText('Sin ventas en el periodo')).toBeTruthy()
    expect(screen.queryByText('hijo')).toBeNull()
  })
  it('vacio sin texto usa "Sin resultados"', () => {
    render(<ListaTarjetas vacio>{null}</ListaTarjetas>)
    expect(screen.getByText('Sin resultados')).toBeTruthy()
  })
  it('cargando muestra "Cargando…" y no los hijos', () => {
    render(<ListaTarjetas cargando vacio><div>hijo</div></ListaTarjetas>)
    expect(screen.getByText('Cargando…')).toBeTruthy()
    expect(screen.queryByText('hijo')).toBeNull()
    expect(screen.queryByText('Sin resultados')).toBeNull()
  })
})
