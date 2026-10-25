// @vitest-environment jsdom
import { describe, it, expect, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import { KpiCard } from '../KpiCard'

afterEach(cleanup)

describe('KpiCard', () => {
  it('pinta etiqueta, valor y detalle con las clases dax-kpi-*', () => {
    render(<KpiCard etiqueta="Hoy" valor="$1,234.50" detalle="12 ventas" data-testid="k" />)
    const k = screen.getByTestId('k')
    expect(k.querySelector('.dax-kpi-label')?.textContent).toBe('Hoy')
    expect(k.querySelector('.dax-kpi-value')?.textContent).toBe('$1,234.50')
    expect(k.textContent).toContain('12 ventas')
    expect(screen.queryByTestId('variacion')).toBeNull()
  })
  it('sube: flecha arriba en success', () => {
    render(<KpiCard etiqueta="Hoy" valor="$1" variacion={{ pct: 12, texto: 'vs ayer' }} />)
    const v = screen.getByTestId('variacion')
    expect(v.textContent).toContain('▲ 12 %')
    expect(v.textContent).toContain('vs ayer')
    expect(v.className).toContain('text-dax-success')
  })
  it('baja: flecha abajo en danger', () => {
    render(<KpiCard etiqueta="Hoy" valor="$1" variacion={{ pct: -8, texto: 'vs ayer' }} />)
    const v = screen.getByTestId('variacion')
    expect(v.textContent).toContain('▼ 8 %')
    expect(v.className).toContain('text-dax-danger')
  })
  it('igual y sin referencia van en muted', () => {
    render(<KpiCard etiqueta="A" valor="$1" variacion={{ pct: 0, texto: 'vs ayer' }} data-testid="a" />)
    render(<KpiCard etiqueta="B" valor="$1" variacion={{ pct: null, texto: 'vs semana anterior' }} data-testid="b" />)
    const [a, b] = screen.getAllByTestId('variacion')
    expect(a.textContent).toBe('Igual · vs ayer')
    expect(a.className).toContain('text-dax-muted')
    expect(b.textContent).toBe('Sin referencia · vs semana anterior')
    expect(b.className).toContain('text-dax-muted')
  })
  it('invertida: subir es malo (devoluciones) y se pinta en danger', () => {
    render(<KpiCard etiqueta="Devoluciones" valor="$400" variacion={{ pct: 300, texto: 'vs periodo anterior', invertida: true }} />)
    const v = screen.getByTestId('variacion')
    expect(v.textContent).toContain('▲ 300 %')
    expect(v.className).toContain('text-dax-danger')
  })
  it('el tono colorea el valor', () => {
    render(<KpiCard etiqueta="Utilidad" valor="$400" tono="success" data-testid="k" />)
    expect(screen.getByTestId('k').querySelector('.dax-kpi-value')?.className).toContain('text-dax-success')
  })
})
