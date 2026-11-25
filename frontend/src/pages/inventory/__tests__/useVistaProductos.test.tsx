// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { renderHook, act, cleanup } from '@testing-library/react'
import { useVistaProductos, leerVista, guardarVista, claveVista } from '../useVistaProductos'

beforeEach(() => localStorage.clear())
afterEach(() => { cleanup(); vi.restoreAllMocks() })

describe('useVistaProductos', () => {
  it('por omisión, tarjetas', () => {
    const { result } = renderHook(() => useVistaProductos(7))
    expect(result.current[0]).toBe('tarjetas')
    expect(leerVista(null)).toBe('tarjetas')
  })

  it('recuerda la elección con una clave que lleva el id del usuario', () => {
    const { result, unmount } = renderHook(() => useVistaProductos(7))
    act(() => result.current[1]('lista'))
    expect(result.current[0]).toBe('lista')
    expect(claveVista(7)).toBe('atlas:productos:vista:7')
    expect(localStorage.getItem('atlas:productos:vista:7')).toBe('lista')
    unmount()
    expect(renderHook(() => useVistaProductos(7)).result.current[0]).toBe('lista')
  })

  it('la elección de un usuario no cambia la de otro en el mismo navegador', () => {
    guardarVista(7, 'lista')
    expect(renderHook(() => useVistaProductos(8)).result.current[0]).toBe('tarjetas')
    // Cambio de sesión sin desmontar: manda lo del usuario nuevo.
    const { result, rerender } = renderHook(({ id }) => useVistaProductos(id), { initialProps: { id: 8 } })
    rerender({ id: 7 })
    expect(result.current[0]).toBe('lista')
  })

  it('un valor desconocido guardado vuelve a la omisión', () => {
    localStorage.setItem(claveVista(7), 'grid')
    expect(leerVista(7)).toBe('tarjetas')
  })

  it('sin almacenamiento no truena: la elección vale esta visita', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('bloqueado') })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('bloqueado') })
    const { result } = renderHook(() => useVistaProductos(7))
    expect(result.current[0]).toBe('tarjetas')
    act(() => result.current[1]('lista'))
    expect(result.current[0]).toBe('lista')
  })
})
