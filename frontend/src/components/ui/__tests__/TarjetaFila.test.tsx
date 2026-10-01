// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import { TarjetaFila } from '../TarjetaFila'

afterEach(cleanup)

describe('TarjetaFila', () => {
  it('pinta titulo, importe, estado y datos', () => {
    render(<TarjetaFila titulo="A-41" subtitulo="29/09" importe="$1,250.00" estado={<span>PAGADA</span>} datos={[{ etiqueta: 'Pago', valor: 'Tarjeta' }]} />)
    expect(screen.getByText('A-41')).toBeTruthy(); expect(screen.getByText('$1,250.00')).toBeTruthy()
    expect(screen.getByText('PAGADA')).toBeTruthy(); expect(screen.getByText('29/09')).toBeTruthy()
    expect(screen.getByText('Pago')).toBeTruthy(); expect(screen.getByText('Tarjeta')).toBeTruthy()
  })
  it('la raiz lleva data-tarjeta-fila y dax-card', () => {
    const { container } = render(<TarjetaFila titulo="x" data-testid="t1" />)
    const raiz = container.firstElementChild as HTMLElement
    expect(raiz.hasAttribute('data-tarjeta-fila')).toBe(true)
    expect(raiz.classList.contains('dax-card')).toBe(true)
    expect(raiz.getAttribute('data-testid')).toBe('t1')
  })
  it('oculta los datos de mas y los muestra con Ver mas', () => {
    const datos = Array.from({ length: 6 }, (_, i) => ({ etiqueta: `E${i}`, valor: `V${i}` }))
    render(<TarjetaFila titulo="x" datos={datos} maxDatosVisibles={4} />)
    expect(screen.getByText('E3')).toBeTruthy()
    expect(screen.queryByText('E5')).toBeNull()
    const verMas = screen.getByRole('button', { name: /ver más/i })
    expect(verMas.getAttribute('aria-expanded')).toBe('false')
    fireEvent.click(verMas)
    expect(screen.getByText('E5')).toBeTruthy()
    expect(screen.getByRole('button', { name: /ver menos/i }).getAttribute('aria-expanded')).toBe('true')
  })
  it('sin datos de sobra no hay Ver mas', () => {
    const datos = Array.from({ length: 4 }, (_, i) => ({ etiqueta: `E${i}`, valor: `V${i}` }))
    render(<TarjetaFila titulo="x" datos={datos} />)
    expect(screen.queryByRole('button', { name: /ver más/i })).toBeNull()
  })
  it('las acciones no disparan el onClick de la tarjeta', () => {
    const abrir = vi.fn(); const imprimir = vi.fn()
    render(<TarjetaFila titulo="x" onClick={abrir} acciones={<button onClick={imprimir}>Reimprimir</button>} />)
    fireEvent.click(screen.getByRole('button', { name: 'Reimprimir' }))
    expect(imprimir).toHaveBeenCalledTimes(1); expect(abrir).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: /^x$/ }))
    expect(abrir).toHaveBeenCalledTimes(1)
  })
  it('Ver mas no dispara el onClick de la tarjeta', () => {
    const abrir = vi.fn()
    const datos = Array.from({ length: 6 }, (_, i) => ({ etiqueta: `E${i}`, valor: `V${i}` }))
    render(<TarjetaFila titulo="x" onClick={abrir} datos={datos} />)
    fireEvent.click(screen.getByRole('button', { name: /ver más/i }))
    expect(abrir).not.toHaveBeenCalled()
    expect(screen.getByText('E5')).toBeTruthy()
  })
  it('acciones={false} no pinta la fila de acciones', () => {
    const { container } = render(<TarjetaFila titulo="x" acciones={false} estado={false} />)
    const raiz = container.firstElementChild as HTMLElement
    // solo el cuerpo: ni fila de acciones ni hueco de estado
    expect(raiz.children).toHaveLength(1)
    expect(container.querySelector('.flex-wrap')).toBeNull()
  })
  it('sin onClick no hay boton envolvente', () => {
    render(<TarjetaFila titulo="solo" />)
    expect(screen.queryByRole('button')).toBeNull()
  })
})
