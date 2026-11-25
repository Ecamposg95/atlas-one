// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { render, screen, cleanup, fireEvent } from '@testing-library/react'

vi.mock('../PrinterSettings', () => ({ PrinterSettings: () => <div>PANTALLA IMPRESORA</div> }))
vi.mock('../PrinterSettingsCajera', () => ({ PrinterSettingsCajera: () => <div>IMPRESORA CAJERA</div> }))
vi.mock('../../core/Organization', () => ({ Organization: ({ seccion }: { seccion?: string }) => <div>EMPRESA:{seccion}</div> }))
vi.mock('../../core/Sucursales', () => ({ Sucursales: () => <div>PANTALLA SUCURSALES</div> }))
vi.mock('../../core/MiPlanYPagos', () => ({ MiPlanYPagos: () => <div>PANTALLA PLAN</div> }))
vi.mock('../../core/TiendaEnLinea', () => ({ TiendaEnLinea: () => <div>PANTALLA TIENDA</div> }))

import { Configuracion } from '../Configuracion'
import { useAuthStore } from '../../../store/authStore'
import { useEnabledModulesStore } from '../../../store/enabledModulesStore'

/** Simula el ancho: `useIsMobile` pregunta `(max-width: 1023px)`. */
const conAncho = (px: number) => {
  window.matchMedia = ((query: string) => {
    const tope = Number(/max-width:\s*(\d+)px/.exec(query)?.[1] ?? 0)
    return {
      matches: px <= tope, media: query, onchange: null,
      addEventListener: () => {}, removeEventListener: () => {},
      addListener: () => {}, removeListener: () => {}, dispatchEvent: () => false,
    }
  }) as unknown as typeof window.matchMedia
}
const como = (role: string) => {
  useAuthStore.setState({ user: { id: 1, username: 'u', role, branch_id: null, branch_name: null } } as never)
  useEnabledModulesStore.setState({ enabledModules: [] } as never)
}
const pintar = (ruta = '/configuracion') => render(
  <MemoryRouter initialEntries={[ruta]}><Configuracion /></MemoryRouter>,
)

beforeEach(() => como('ADMINISTRADOR'))
afterEach(() => {
  cleanup()
  delete (window as { matchMedia?: unknown }).matchMedia
})

describe('Configuración: disposición del centro de ajustes', () => {
  it('escritorio (≥ 1024): pestañas en columna lateral vertical y el contenido en su panel', () => {
    conAncho(1440)
    pintar()
    const lista = screen.getByRole('tablist')
    expect(lista.getAttribute('aria-orientation')).toBe('vertical')
    expect(lista.className).toContain('flex-col')
    const lateral = screen.getByTestId('pestanas-laterales')
    expect(lateral.contains(lista)).toBe(true)
    expect(lateral.className).toContain('sticky')
    expect(screen.getByRole('tabpanel').textContent).toContain('EMPRESA:empresa')
  })

  it('teléfono y tablet (< 1024): pestañas horizontales arriba, sin columna lateral', () => {
    conAncho(1023)
    pintar()
    const lista = screen.getByRole('tablist')
    expect(lista.getAttribute('aria-orientation')).toBe('horizontal')
    expect(lista.className).toContain('flex-wrap')
    expect(lista.className).not.toContain('flex-col')
    expect(screen.queryByTestId('pestanas-laterales')).toBeNull()
    expect(screen.getByText('EMPRESA:empresa')).toBeTruthy()
  })

  it.each([1440, 390])('?tab= elige la pestaña y la marca como activa (ancho %i)', (px) => {
    conAncho(px)
    pintar('/configuracion?tab=sucursales')
    expect(screen.getByText('PANTALLA SUCURSALES')).toBeTruthy()
    const activa = screen.getByRole('tab', { name: /Sucursales/ })
    expect(activa.getAttribute('aria-selected')).toBe('true')
    expect(activa.getAttribute('aria-current')).toBe('page')
    const otra = screen.getByRole('tab', { name: /Empresa/ })
    expect(otra.getAttribute('aria-selected')).toBe('false')
    expect(otra.getAttribute('aria-current')).toBeNull()
  })

  it('?tab=impresoras abre impresoras; una pestaña desconocida cae en Empresa', () => {
    conAncho(1440)
    pintar('/configuracion?tab=impresoras')
    expect(screen.getByText('PANTALLA IMPRESORA')).toBeTruthy()
    cleanup()
    pintar('/configuracion?tab=noexiste')
    expect(screen.getByText('EMPRESA:empresa')).toBeTruthy()
  })

  it('tocar una pestaña lateral cambia el contenido', () => {
    conAncho(1440)
    pintar()
    fireEvent.click(screen.getByRole('tab', { name: /Ventas y caja/ }))
    expect(screen.getByText('EMPRESA:ventas')).toBeTruthy()
    fireEvent.click(screen.getByRole('tab', { name: /Mi plan y pagos/ }))
    expect(screen.getByText('PANTALLA PLAN')).toBeTruthy()
  })

  it('gerente y cajera: sin pestañas, en cualquier ancho', () => {
    conAncho(1440)
    como('GERENTE')
    pintar()
    expect(screen.getByText('PANTALLA IMPRESORA')).toBeTruthy()
    expect(screen.queryByRole('tab')).toBeNull()
    cleanup()
    como('CAJERO')
    pintar()
    expect(screen.getByText('IMPRESORA CAJERA')).toBeTruthy()
    expect(screen.queryByRole('tab')).toBeNull()
  })
})
