// @vitest-environment jsdom
import { describe, it, expect, afterEach } from 'vitest'
import { cleanup, renderHook, waitFor } from '@testing-library/react'
import { colorMetodo, leerTemaGrafica, useTemaGrafica } from '../tema'

const raiz = document.documentElement
afterEach(() => {
  cleanup()
  for (const v of ['--dax-accent', '--dax-text-muted', '--dax-success']) raiz.style.removeProperty(v)
  raiz.className = ''
})

describe('useTemaGrafica', () => {
  it('lee los tokens --dax-* de <html>', () => {
    raiz.style.setProperty('--dax-accent', '#123456')
    raiz.style.setProperty('--dax-text-muted', '#654321')
    const t = leerTemaGrafica()
    expect(t.acento).toBe('#123456')
    expect(t.muted).toBe('#654321')
  })

  it('sin la variable usa el respaldo del tema oscuro', () => {
    expect(leerTemaGrafica().danger).toBe('#F87171')
    expect(leerTemaGrafica().borde).toBe('rgba(255, 255, 255, 0.08)')
  })

  it('se vuelve a leer al cambiar la clase de <html>', async () => {
    raiz.style.setProperty('--dax-accent', '#111111')
    const { result } = renderHook(() => useTemaGrafica())
    expect(result.current.acento).toBe('#111111')
    raiz.style.setProperty('--dax-accent', '#222222')
    raiz.classList.add('dark')
    await waitFor(() => expect(result.current.acento).toBe('#222222'))
  })

  it('métodos, como en el POS: efectivo = acento, tarjeta = índigo, transferencia = lavanda, otros = tenue', () => {
    raiz.style.setProperty('--dax-indigo', '#00aa00')
    const t = leerTemaGrafica()
    raiz.style.removeProperty('--dax-indigo')
    expect(colorMetodo('CASH', t)).toBe(t.acento)
    expect(colorMetodo('card', t)).toBe('#00aa00')
    expect(colorMetodo('TRANSFER', t)).toBe(t.lavanda)
    expect(colorMetodo('MIXED', t)).toBe(t.faint)
  })
})
