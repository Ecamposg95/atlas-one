// @vitest-environment jsdom
import { describe, it, expect, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import { BarraFiltros, ParFechas } from '../BarraFiltros'

afterEach(cleanup)

describe('BarraFiltros', () => {
  it('la raiz tiene dax-filtros y la fila flex de hoy', () => {
    const { container } = render(<BarraFiltros className="mb-4"><input aria-label="q" /></BarraFiltros>)
    const raiz = container.firstElementChild as HTMLElement
    for (const c of ['dax-filtros', 'flex', 'flex-wrap', 'items-end', 'gap-2', 'mb-4']) {
      expect(raiz.classList.contains(c)).toBe(true)
    }
    expect(screen.getByLabelText('q').parentElement).toBe(raiz)
  })
  it('accion va dentro de .dax-filtros-accion, al final', () => {
    const { container } = render(<BarraFiltros accion={<button>Aplicar</button>}><input aria-label="q" /></BarraFiltros>)
    const raiz = container.firstElementChild as HTMLElement
    const envoltura = screen.getByRole('button', { name: 'Aplicar' }).parentElement as HTMLElement
    expect(envoltura.classList.contains('dax-filtros-accion')).toBe(true)
    expect(raiz.lastElementChild).toBe(envoltura)
  })
  it('sin accion no pinta la envoltura', () => {
    const { container } = render(<BarraFiltros><input aria-label="q" /></BarraFiltros>)
    expect(container.querySelector('.dax-filtros-accion')).toBeNull()
  })
})

describe('ParFechas', () => {
  it('rejilla de 2 columnas que en sm se disuelve con contents', () => {
    const { container } = render(<ParFechas><input type="date" /><input type="date" /></ParFechas>)
    const raiz = container.firstElementChild as HTMLElement
    for (const c of ['grid', 'grid-cols-2', 'gap-2', 'sm:contents']) {
      expect(raiz.classList.contains(c)).toBe(true)
    }
    expect(raiz.children).toHaveLength(2)
  })
})
