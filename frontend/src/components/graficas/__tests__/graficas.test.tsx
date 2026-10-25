// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'

// jsdom no tiene canvas: los componentes de react-chartjs-2 se sustituyen por
// stubs que exponen lo que el kit les construye. Se prueba la configuración,
// no el dibujo.
type Dataset = Record<string, unknown>
// vi.mock se iza al inicio del archivo: el stub se define dentro de la fábrica.
vi.mock('react-chartjs-2', () => {
  type Props = { data: { labels?: unknown[]; datasets: Record<string, unknown>[] }; options: Record<string, any> }
  const volcar = (id: string) => (p: Props) => (
    <div data-testid={id} data-datasets={JSON.stringify(p.data.datasets)} data-labels={JSON.stringify(p.data.labels)}
      data-animacion={String(p.options.animation?.duration)} data-eje={String(p.options.indexAxis)} data-cutout={String(p.options.cutout)} />
  )
  return { Line: volcar('line'), Bar: volcar('bar'), Doughnut: volcar('dona') }
})

import { GraficaBarras, GraficaDona, GraficaLinea } from '..'

const raiz = document.documentElement
const datasets = (id: string) => JSON.parse(screen.getByTestId(id).getAttribute('data-datasets') ?? '[]') as Dataset[]

afterEach(() => { cleanup(); raiz.style.removeProperty('--dax-accent'); raiz.style.removeProperty('--dax-text-faint') })

describe('GraficaLinea', () => {
  it('serie principal en acento y comparativo tenue y discontinuo; sin relleno; 300 ms', () => {
    raiz.style.setProperty('--dax-accent', '#111111')
    raiz.style.setProperty('--dax-text-faint', '#999999')
    render(<GraficaLinea etiquetas={['l', 'm']} series={[
      { nombre: 'Estos 7 días', valores: [1, 2] },
      { nombre: 'Semana anterior', valores: [3, 4], comparativo: true },
    ]} />)
    const [principal, comparativo] = datasets('line')
    expect(principal).toMatchObject({ label: 'Estos 7 días', borderColor: '#111111', fill: false, pointRadius: 0 })
    expect(principal.borderDash).toBeUndefined()
    expect(comparativo).toMatchObject({ label: 'Semana anterior', borderColor: '#999999', borderDash: [4, 4], fill: false })
    expect(screen.getByTestId('line').getAttribute('data-animacion')).toBe('300')
  })
})

describe('GraficaBarras', () => {
  it('sin resaltar todas las barras van en acento', () => {
    raiz.style.setProperty('--dax-accent', '#111111')
    render(<GraficaBarras etiquetas={['a', 'b']} valores={[1, 2]} />)
    expect(datasets('bar')[0].backgroundColor).toEqual(['#111111', '#111111'])
    expect(screen.getByTestId('bar').getAttribute('data-eje')).toBe('x')
  })
  it('con resaltar, esa barra va en acento y el resto tenue', () => {
    raiz.style.setProperty('--dax-accent', '#111111')
    raiz.style.setProperty('--dax-text-faint', '#999999')
    render(<GraficaBarras etiquetas={['a', 'b', 'c']} valores={[1, 2, 3]} resaltar={1} />)
    expect(datasets('bar')[0].backgroundColor).toEqual(['#999999', '#111111', '#999999'])
  })
  it('horizontal cambia el eje índice a y', () => {
    render(<GraficaBarras etiquetas={['Roma', 'Condesa']} valores={[6000, 3000]} horizontal />)
    expect(screen.getByTestId('bar').getAttribute('data-eje')).toBe('y')
    expect(screen.getByTestId('bar').getAttribute('data-animacion')).toBe('300')
  })
})

describe('GraficaDona', () => {
  it('la dona recorta negativos a cero, respeta los colores y pinta el centro', () => {
    render(<GraficaDona partes={[
      { nombre: 'Efectivo', valor: 500, color: '#0a0' },
      { nombre: 'Tarjeta', valor: -40, color: '#00a' },
    ]} centro={<span>Total</span>} />)
    const [d] = datasets('dona')
    expect(d.data).toEqual([500, 0])
    expect(d.backgroundColor).toEqual(['#0a0', '#00a'])
    expect(screen.getByTestId('dona').getAttribute('data-cutout')).toBe('70%')
    expect(screen.getByText('Total')).toBeTruthy()
  })
})
