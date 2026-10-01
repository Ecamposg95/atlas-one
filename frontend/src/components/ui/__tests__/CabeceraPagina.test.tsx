// @vitest-environment jsdom
import { describe, it, expect, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import { CabeceraPagina } from '../CabeceraPagina'

afterEach(cleanup)

describe('CabeceraPagina', () => {
  it('ambas envolturas de acciones tienen piso de 44 px solo bajo md, sin tocar el ancho en escritorio', () => {
    render(
      <CabeceraPagina
        titulo={<h1>Ventas</h1>}
        acciones={<button>Exportar</button>}
        accionPrincipal={<button>Nueva venta</button>}
      />,
    )
    const secundaria = screen.getByRole('button', { name: 'Exportar' }).parentElement as HTMLElement
    const primaria = screen.getByRole('button', { name: 'Nueva venta' }).parentElement as HTMLElement
    for (const env of [secundaria, primaria]) {
      expect(env.classList.contains('max-md:[&>*]:min-h-[44px]')).toBe(true)
      // nada que imponga ancho en escritorio
      expect(Array.from(env.classList).some(c => c.startsWith('md:') && c.includes('w-'))).toBe(false)
    }
    expect(primaria.classList.contains('max-md:[&>*]:w-full')).toBe(true)
  })
  it('la fila de escritorio es la de hoy', () => {
    const { container } = render(<CabeceraPagina titulo={<h1>t</h1>} />)
    const raiz = container.firstElementChild as HTMLElement
    for (const c of ['md:flex-row', 'md:items-center', 'md:justify-between', 'md:flex-wrap', 'gap-3']) {
      expect(raiz.classList.contains(c)).toBe(true)
    }
  })
})
