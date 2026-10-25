// frontend/src/pages/inventory/conteos/__tests__/ConteoSesion.test.tsx
// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { render, screen, cleanup, fireEvent, waitFor, within } from '@testing-library/react'

const { ver, lista, cancelar, cerrar, navigate, lectorStop } = vi.hoisted(() => ({
  ver: vi.fn(), lista: vi.fn(), cancelar: vi.fn(), cerrar: vi.fn(), navigate: vi.fn(), lectorStop: vi.fn(),
}))
vi.mock('../../../../api/conteos', () => ({ conteosApi: { ver, lista, cancelar, cerrar } }))
vi.mock('../../../../api/products', () => ({ productsApi: {} }))
// La cámara no se monta en la prueba: el lector solo expone lo que la pantalla lee.
vi.mock('../useLectorCodigos', () => ({
  useLectorCodigos: () => ({ videoRef: { current: null }, canvasRef: { current: null }, camOn: false, camError: null, start: vi.fn(), stop: lectorStop }),
}))
vi.mock('react-router-dom', async (original) => ({
  ...(await original<typeof import('react-router-dom')>()),
  useNavigate: () => navigate,
}))

import { ConteoSesion } from '../ConteoSesion'
import { ConfirmDialogProvider } from '../../../../components/ui/ConfirmDialog'
import { useToastStore } from '../../../../store/toastStore'

const avance = { esperadas_variantes: 2, esperadas_piezas: '5', contadas_variantes: 1, contadas_piezas: '2', desconocidos: 1 }
const linea = (id: number, qty: string, variant_id: string | null) => ({
  id, variant_id, codigo: variant_id ? null : 'XYZ', qty_contada: qty, qty_sistema: null, producto: null,
  corregida: false, ajustada: false, updated_at: null,
})
const detalle = (status: 'ABIERTO' | 'CERRADO' | 'CANCELADO') => ({
  id: 7, branch_id: 1, branch_name: 'Roma', department_id: 'd1', department_name: 'Playeras', status,
  notes: null, created_by: 'ana', created_at: '2026-10-24T10:00:00Z', closed_at: null, aplicado_at: null, aplicado_por: null,
  avance, lineas: [linea(1, '2', 'v1'), linea(2, '1', null)],   // 2 contadas + 1 código desconocido = 3 piezas
})
const LISTA = { filas: [], totales: { total: 0, revisados: 0, pendientes: 0, con_diferencia: 0, corregidas: 0 } }

const pintar = () => render(
  <MemoryRouter initialEntries={['/inventory/conteos/7']}>
    <ConfirmDialogProvider>
      <Routes><Route path="/inventory/conteos/:id" element={<ConteoSesion />} /></Routes>
    </ConfirmDialogProvider>
  </MemoryRouter>,
)
const avisos = () => useToastStore.getState().toasts.map((t) => `${t.type}:${t.message}`)

beforeEach(() => {
  ver.mockReset().mockResolvedValue(detalle('ABIERTO'))
  lista.mockReset().mockResolvedValue(LISTA)
  cancelar.mockReset().mockResolvedValue({ ...detalle('CANCELADO'), lineas: undefined })
  cerrar.mockReset()
  navigate.mockReset()
  lectorStop.mockReset()
  useToastStore.setState({ toasts: [] })
})
afterEach(cleanup)

describe('ConteoSesion: Cancelar conteo', () => {
  it('pide confirmación con las piezas contadas; "Volver" no cancela nada', async () => {
    pintar()
    fireEvent.click(await screen.findByRole('button', { name: 'Cancelar conteo' }))
    const dialogo = await screen.findByRole('dialog')
    expect(within(dialogo).getByText('Cancelar el conteo')).toBeTruthy()
    expect(dialogo.textContent).toContain('Se descarta lo contado (3 piezas)')
    expect(dialogo.textContent).toContain('Los ajustes ya hechos en piso se conservan')
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Volver' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(cancelar).not.toHaveBeenCalled()
    expect(navigate).not.toHaveBeenCalled()
  })

  it('al confirmar cancela, avisa y vuelve a la lista', async () => {
    pintar()
    fireEvent.click(await screen.findByRole('button', { name: 'Cancelar conteo' }))
    const dialogo = await screen.findByRole('dialog')
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Cancelar conteo' }))
    await waitFor(() => expect(navigate).toHaveBeenCalledWith('/inventory/conteos'))
    expect(cancelar).toHaveBeenCalledWith(7)
    expect(lectorStop).toHaveBeenCalled()
    expect(avisos()).toEqual(['success:Conteo cancelado'])
  })

  it('si el servidor rechaza, muestra el motivo y se queda en la sesión', async () => {
    cancelar.mockRejectedValue({ response: { status: 500, data: { detail: 'Error interno' } } })
    pintar()
    fireEvent.click(await screen.findByRole('button', { name: 'Cancelar conteo' }))
    fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Cancelar conteo' }))
    await waitFor(() => expect(avisos()).toEqual(['error:Error interno']))
    expect(navigate).not.toHaveBeenCalled()
    expect(ver).toHaveBeenCalledTimes(1)   // un fallo que no es 409 no relee
  })

  it('un 409 (otro ya lo cerró o canceló) relee el conteo: la pantalla se pone al día y redirige', async () => {
    cancelar.mockRejectedValue({ response: { status: 409, data: { detail: 'Este conteo ya está cerrado o cancelado.' } } })
    pintar()
    fireEvent.click(await screen.findByRole('button', { name: 'Cancelar conteo' }))
    ver.mockResolvedValue(detalle('CANCELADO'))   // lo que ve la relectura tras el 409
    fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Cancelar conteo' }))
    await waitFor(() => expect(navigate).toHaveBeenCalledWith('/inventory/conteos', { replace: true }))
    expect(ver).toHaveBeenCalledTimes(2)
    expect(avisos().sort()).toEqual([
      'error:Este conteo ya está cerrado o cancelado.',
      'info:Este conteo fue cancelado',
    ])
  })

  it('abrir por URL un conteo cancelado regresa a la lista con un solo aviso y sin botones', async () => {
    ver.mockResolvedValue(detalle('CANCELADO'))
    pintar()
    await waitFor(() => expect(navigate).toHaveBeenCalledWith('/inventory/conteos', { replace: true }))
    expect(avisos()).toEqual(['info:Este conteo fue cancelado'])
    expect(screen.queryByRole('button', { name: 'Cerrar conteo' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Cancelar conteo' })).toBeNull()
  })

  it('un conteo abierto trae los dos botones, "Cancelar conteo" en rojo, repartiéndose el ancho en teléfono', async () => {
    pintar()
    const cancelarBtn = await screen.findByRole('button', { name: 'Cancelar conteo' })
    const cerrarBtn = screen.getByRole('button', { name: 'Cerrar conteo' })
    expect(cancelarBtn.className).toContain('dax-btn-danger')
    expect(cerrarBtn.className).toContain('dax-btn-secondary')
    // Mismo grupo; el ancho (jsdom no lo mide) se reparte con flex-1 y el alto táctil con max-sm:min-h-[44px].
    expect(cancelarBtn.parentElement).toBe(cerrarBtn.parentElement)
    for (const b of [cancelarBtn, cerrarBtn]) {
      expect(b.className).toContain('flex-1')
      expect(b.className).toContain('max-sm:min-h-[44px]')
    }
    expect(navigate).not.toHaveBeenCalled()
  })
})
