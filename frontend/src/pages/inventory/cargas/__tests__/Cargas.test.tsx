// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { render, screen, cleanup, fireEvent, waitFor, act } from '@testing-library/react'

const { listar, subir, getOrg, getBranches, navigate } = vi.hoisted(() => ({
  listar: vi.fn(), subir: vi.fn(), getOrg: vi.fn(), getBranches: vi.fn(), navigate: vi.fn(),
}))
vi.mock('../../../../api/cargas', () => ({ cargasApi: { listar, subir } }))
vi.mock('../../../../api/organization', () => ({ organizationApi: { getOrg, getBranches } }))
vi.mock('react-router-dom', async (original) => ({
  ...(await original<typeof import('react-router-dom')>()),
  useNavigate: () => navigate,
}))

import { Cargas } from '../Cargas'
import { useToastStore } from '../../../../store/toastStore'

const carga = (id: string, folio: number, estado: string) => ({
  id, folio, estado, proposito: 'entrada', archivo_nombre: `lista-${folio}.pdf`, archivo_tipo: 'pdf',
  sucursal_destino_id: 2, sucursal_nombre: 'Tienda Uno', piezas: '12', usuario: 'ana',
  created_at: '2026-11-14T10:00:00Z', aplicada_at: null, error: null,
})
const CARGAS = [carga('c1', 2, 'plan'), carga('c2', 1, 'aplicada')]

const anchoDePantalla = (telefono: boolean) => {
  window.matchMedia = ((query: string) => ({
    matches: telefono && query === '(max-width: 767px)', media: query, onchange: null,
    addEventListener: () => {}, removeEventListener: () => {}, addListener: () => {}, removeListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia
}
const pintar = () => render(<MemoryRouter><Cargas /></MemoryRouter>)
const avisos = () => useToastStore.getState().toasts.map((t) => `${t.type}:${t.message}`)
const archivo = (nombre: string, bytes = 10) => new File([new Uint8Array(bytes)], nombre, { type: 'application/pdf' })
const elegir = (f: File) => fireEvent.change(document.querySelector('input[type="file"]') as HTMLInputElement, { target: { files: [f] } })

beforeEach(() => {
  anchoDePantalla(false)
  listar.mockReset().mockResolvedValue(CARGAS)
  subir.mockReset().mockResolvedValue({ id: 'c9', folio: 3, estado: 'leyendo' })
  getOrg.mockReset().mockResolvedValue({ id: 1, reglas_carga: { sucursal_recibe: 3 } })
  getBranches.mockReset().mockResolvedValue([
    { id: 2, name: 'Tienda Uno', branch_type: 'STORE', is_active: true, can_sell: true },
    { id: 3, name: 'Bodega Dos', branch_type: 'WAREHOUSE', is_active: true, can_sell: false },
  ])
  navigate.mockReset()
  useToastStore.setState({ toasts: [] })
})
afterEach(() => { cleanup(); vi.useRealTimers() })

describe('Cargar mercancía: lista y subida', () => {
  it('sube el archivo con el propósito elegido y navega al plan', async () => {
    pintar()
    await screen.findByText('lista-2.pdf')
    await waitFor(() => expect((screen.getByLabelText('Sucursal que recibe') as HTMLSelectElement).value).toBe('3'))
    fireEvent.change(screen.getByLabelText('Propósito'), { target: { value: 'migracion' } })
    const f = archivo('nueva.pdf')
    elegir(f)
    await waitFor(() => expect(subir).toHaveBeenCalledWith(f, 'migracion', 3))
    await waitFor(() => expect(navigate).toHaveBeenCalledWith('/inventory/cargas/c9'))
  })

  it('rechaza en cliente archivos de más de 20 MB con mensaje', async () => {
    pintar()
    await screen.findByText('lista-2.pdf')
    elegir(archivo('enorme.pdf', 20 * 1024 * 1024 + 1))
    await waitFor(() => expect(avisos().some((a) => a.includes('20 MB'))).toBe(true))
    expect(subir).not.toHaveBeenCalled()
    expect(navigate).not.toHaveBeenCalled()
  })

  it('en teléfono muestra tarjetas, no tabla', async () => {
    anchoDePantalla(true)
    pintar()
    await screen.findByText('#2 · lista-2.pdf')
    expect(document.querySelector('table')).toBeNull()
    expect(document.querySelectorAll('[data-tarjeta-fila]').length).toBe(2)
  })

  it('en PC muestra la tabla con folio, estado y navega al tocar la fila', async () => {
    pintar()
    fireEvent.click((await screen.findByText('lista-2.pdf')).closest('tr') as HTMLElement)
    expect(navigate).toHaveBeenCalledWith('/inventory/cargas/c1')
    expect(screen.getByText('Por revisar')).toBeTruthy()
    expect(screen.getByText('Aplicada')).toBeTruthy()
  })

  it('refresca cada 5 s mientras haya una carga leyendo y se detiene al desmontar', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    listar.mockResolvedValue([carga('c1', 2, 'leyendo')])
    const { unmount } = pintar()
    await waitFor(() => expect(listar).toHaveBeenCalledTimes(1))
    await act(async () => { await vi.advanceTimersByTimeAsync(5000) })
    expect(listar).toHaveBeenCalledTimes(2)
    unmount()
    await act(async () => { await vi.advanceTimersByTimeAsync(10000) })
    expect(listar).toHaveBeenCalledTimes(2)
  })

  it('no refresca si ninguna carga está leyendo ni aplicando', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    pintar()
    await waitFor(() => expect(listar).toHaveBeenCalledTimes(1))
    await act(async () => { await vi.advanceTimersByTimeAsync(15000) })
    expect(listar).toHaveBeenCalledTimes(1)
  })
})
