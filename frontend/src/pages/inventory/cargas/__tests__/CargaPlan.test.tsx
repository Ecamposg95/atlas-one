// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { render, screen, cleanup, fireEvent, waitFor, act } from '@testing-library/react'

const api = vi.hoisted(() => ({
  obtener: vi.fn(), responder: vi.fn(), resolverDuda: vi.fn(), deshacer: vi.fn(),
  reintentar: vi.fn(), autorizar: vi.fn(), descartar: vi.fn(), etiquetas: vi.fn(),
}))
const { confirmar, navegar } = vi.hoisted(() => ({ confirmar: vi.fn(), navegar: vi.fn() }))
vi.mock('react-router-dom', async (o) => ({ ...(await o<typeof import('react-router-dom')>()), useNavigate: () => navegar }))
vi.mock('../../../../api/cargas', () => ({ cargasApi: api }))
vi.mock('../../../../components/ui/ConfirmDialog', () => ({ confirm: confirmar }))

import CargaPlan from '../CargaPlan'
import { useAuthStore } from '../../../../store/authStore'
import { useToastStore } from '../../../../store/toastStore'

const duda = (numero: number, extra: object = {}) => ({
  numero, tipo: 'precio_faltante', texto: `Duda ${numero}`, opciones: [{ clave: 'a', etiqueta: 'Opción A' }, { clave: 'b', etiqueta: 'Opción B' }],
  recomendada: 'b', acepta_texto: false, estado: 'abierta', respuesta: null, ...extra,
})
const detalle = () => ({
  carga: { id: 'c1', folio: 7, estado: 'plan', proposito: 'entrada', archivo_nombre: 'lista.pdf', archivo_tipo: 'pdf',
    sucursal_destino_id: 1, sucursal_nombre: 'Tienda Uno', piezas: '5.00', usuario: 'ana', created_at: '2026-11-14T10:00:00Z',
    aplicada_at: null, error: null, monedas: {}, totales: null },
  contadores: { EXISTE: 0, SUMA: 1, NUEVO: 2, YA_CARGADO: 0, IGNORADO: 0, piezas: '5.00' },
  dudas: [], cambios: [], ultimos_conteos: [{ departamento: 'Ropa', numero: 3, cerrado_at: '2026-11-10T10:00:00Z' }],
  grupos: [{ grupo: 'g1', titulo: 'Marca Uno · Camisa lino', marca: 'Marca Uno', tipo: 'Camisa', departamento: 'Ropa', genero: null, product_id: null,
    renglones: [{ orden: 1, talla: 'M', color: null, cantidad: '5.00', precio: '500.00', costo: '250.00', clase: 'NUEVO', sku: 'MU-CAM-M', origen: 'pág. 2', descripcion: 'CAMISA LINO MU 3201' }] }],
  puede_autorizar: true,
})
const D = (over: any = {}) => { const d: any = detalle(); const { carga, ...resto } = over; Object.assign(d, resto); Object.assign(d.carga, carga ?? {}); return d }

const cambio = (over: object = {}) => ({
  id: 'k1', secuencia: 1, texto: 'precio 600', deshecho: false, puede_deshacer: true, usuario: 'ana', created_at: '2026-11-14T10:00:00Z',
  resumen: { grupos: [{ grupo: 'g1', titulo: 'Marca Uno · Camisa lino', renglones: [1], cambios: { precio: { antes: '500.00', despues: '600.00' } } }],
    dudas_resueltas: [1, 3], dudas_nuevas: [7] }, ...over,
})

const anchoDePantalla = (telefono: boolean) => {
  window.matchMedia = ((query: string) => ({
    matches: telefono && query === '(max-width: 767px)', media: query, onchange: null,
    addEventListener: () => {}, removeEventListener: () => {}, addListener: () => {}, removeListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia
}
const avisos = () => useToastStore.getState().toasts.map((t) => `${t.type}:${t.message}`)
const pintar = () => render(
  <MemoryRouter initialEntries={['/inventory/cargas/c1']}>
    <Routes><Route path="/inventory/cargas/:id" element={<CargaPlan />} /></Routes>
  </MemoryRouter>)
const conRol = (role: string) => useAuthStore.setState({ user: { role } as any })

beforeEach(() => {
  anchoDePantalla(false)
  Object.values(api).forEach((f) => f.mockReset())
  confirmar.mockReset().mockResolvedValue(true)
  api.obtener.mockResolvedValue(D())
  conRol('ADMINISTRADOR')
  useToastStore.setState({ toasts: [] })
})
afterEach(() => { cleanup(); vi.useRealTimers() })

describe('Cargar mercancía: plan', () => {
  it('mientras lee, consulta cada 3 s y luego muestra el plan', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    api.obtener.mockResolvedValueOnce(D({ carga: { estado: 'leyendo' } })).mockResolvedValue(D())
    pintar()
    await screen.findByText('Leyendo el documento…')
    expect(api.obtener).toHaveBeenCalledTimes(1)
    await act(async () => { await vi.advanceTimersByTimeAsync(3100) })
    await screen.findByText('Marca Uno · Camisa lino')
    expect(api.obtener).toHaveBeenCalledTimes(2)
    expect(screen.getByText("Último conteo de Ropa: #3, 10 nov")).toBeTruthy()
    await act(async () => { await vi.advanceTimersByTimeAsync(9000) })
    expect(api.obtener).toHaveBeenCalledTimes(2)
  })

  it('un botón de opción llama resolverDuda con su clave y la recomendada va primero', async () => {
    api.obtener.mockResolvedValue(D({ dudas: [duda(1)] }))
    api.resolverDuda.mockResolvedValue({ cambio: null, rechazos: [] })
    pintar()
    const botones = await screen.findAllByRole('button', { name: /Opción/ })
    expect(botones[0].textContent).toContain('Opción B')
    expect(botones[0].textContent).toContain('Recomendado')
    fireEvent.click(botones[0])
    await waitFor(() => expect(api.resolverDuda).toHaveBeenCalledWith('c1', 1, 'b', undefined))
    await waitFor(() => expect(api.obtener).toHaveBeenCalledTimes(2))
  })

  it('una duda que acepta texto muestra input y manda el valor', async () => {
    api.obtener.mockResolvedValue(D({ dudas: [duda(2, { acepta_texto: true })] }))
    api.resolverDuda.mockResolvedValue({ cambio: null, rechazos: [] })
    pintar()
    fireEvent.change(await screen.findByLabelText('Respuesta a la duda 2'), { target: { value: '450' } })
    fireEvent.click(screen.getByRole('button', { name: 'Responder' }))
    await waitFor(() => expect(api.resolverDuda).toHaveBeenCalledWith('c1', 2, '', '450'))
  })

  it('enviar respuesta muestra antes/después, preguntas y rechazos; Deshacer usa el detalle devuelto', async () => {
    api.responder.mockResolvedValue({ cambio: cambio(), rechazos: ['No entendí el 9'] })
    api.deshacer.mockResolvedValue(D())
    pintar()
    fireEvent.change(await screen.findByPlaceholderText('Contesta por número: 1. … 2. …'), { target: { value: '1. 600' } })
    fireEvent.click(screen.getByRole('button', { name: 'Enviar' }))
    await screen.findByText(/Precio: 500.00 →/)
    expect(screen.getByText('Preguntas resueltas: 1, 3')).toBeTruthy()
    expect(screen.getByText('Preguntas nuevas: 7')).toBeTruthy()
    expect(screen.getByText('No entendí el 9')).toBeTruthy()
    expect(api.responder).toHaveBeenCalledWith('c1', '1. 600')
    fireEvent.click(screen.getByRole('button', { name: 'Deshacer' }))
    await waitFor(() => expect(api.deshacer).toHaveBeenCalledWith('c1', 'k1'))
    await waitFor(() => expect(screen.queryByText(/Precio: 500.00 →/)).toBeNull())
  })

  it('Autorizar deshabilitado con dudas abiertas', async () => {
    api.obtener.mockResolvedValue(D({ dudas: [duda(1)], puede_autorizar: false }))
    pintar()
    const b = (await screen.findByRole('button', { name: 'Autorizar' })) as HTMLButtonElement
    expect(b.disabled).toBe(true)
  })

  it('Autorizar no aparece para GERENTE', async () => {
    conRol('GERENTE')
    pintar()
    await screen.findByText('Marca Uno · Camisa lino')
    expect(screen.queryByRole('button', { name: 'Autorizar' })).toBeNull()
  })

  it('autorizar confirma con el resumen y luego muestra etiquetas con el enlace a /labels', async () => {
    api.autorizar.mockResolvedValue({ productos_nuevos: 1, variantes_nuevas: 1, piezas: '5.00', valor_costo: '1250.00',
      etiquetas: [{ marca: 'Marca Uno', producto: 'Camisa lino', sku: 'MU-CAM-M', talla: 'M', barcode: '2000000000017', piezas: '5.00', precio: '500.00' }] })
    api.obtener.mockResolvedValueOnce(D()).mockResolvedValue(D({ carga: { estado: 'aplicada' } }))
    pintar()
    fireEvent.click(await screen.findByRole('button', { name: 'Autorizar' }))
    await waitFor(() => expect(api.autorizar).toHaveBeenCalledWith('c1'))
    expect(confirmar.mock.calls[0][0].message).toContain('1 producto nuevo, 5 piezas, $1,250.00')
    const enlace = await screen.findByRole('link', { name: /Imprimir etiquetas/ })
    expect(enlace.getAttribute('href')).toBe('/labels?carga=c1&folio=7')
    expect(screen.getByText('2000000000017')).toBeTruthy()
  })

  it('si no confirma, no autoriza', async () => {
    confirmar.mockResolvedValue(false)
    pintar()
    fireEvent.click(await screen.findByRole('button', { name: 'Autorizar' }))
    await waitFor(() => expect(confirmar).toHaveBeenCalled())
    expect(api.autorizar).not.toHaveBeenCalled()
  })

  it('error muestra Volver a intentar y llama reintentar', async () => {
    api.obtener.mockResolvedValue(D({ carga: { estado: 'error', error: 'El PDF está vacío' } }))
    api.reintentar.mockResolvedValue({ id: 'c1', folio: 7, estado: 'leyendo' })
    pintar()
    await screen.findByText('El PDF está vacío')
    fireEvent.click(screen.getByRole('button', { name: /Volver a intentar/ }))
    await waitFor(() => expect(api.reintentar).toHaveBeenCalledWith('c1'))
  })

  it('aplicando espera con su texto y descartada avisa', async () => {
    api.obtener.mockResolvedValue(D({ carga: { estado: 'aplicando' } }))
    pintar()
    await screen.findByText('Aplicando la carga…')
    cleanup()
    api.obtener.mockResolvedValue(D({ carga: { estado: 'descartada' } }))
    pintar()
    await screen.findByText(/se descartó/)
    expect(screen.getByRole('link', { name: /Volver a las cargas/ })).toBeTruthy()
  })

  it('cada renglón enseña la descripción original y su origen', async () => {
    pintar()
    await screen.findByText('Marca Uno · Camisa lino')
    expect(screen.getByText('CAMISA LINO MU 3201 · pág. 2')).toBeTruthy()
    cleanup()
    anchoDePantalla(true)
    pintar()
    await screen.findByText('Marca Uno · Camisa lino')
    expect(screen.getByText('CAMISA LINO MU 3201 · pág. 2')).toBeTruthy()
  })

  it('en teléfono el plan va en tarjetas y la caja de respuesta existe', async () => {
    anchoDePantalla(true)
    pintar()
    await screen.findByText('Marca Uno · Camisa lino')
    expect(document.querySelector('table')).toBeNull()
    expect(document.querySelectorAll('[data-tarjeta-fila]').length).toBe(1)
    expect(screen.getByPlaceholderText('Contesta por número: 1. … 2. …')).toBeTruthy()
  })

  it('Descartar confirma, descarta y vuelve a la lista', async () => {
    api.descartar.mockResolvedValue({ id: 'c1', folio: 7, estado: 'descartada' })
    pintar()
    fireEvent.click(await screen.findByRole('button', { name: 'Descartar' }))
    await waitFor(() => expect(api.descartar).toHaveBeenCalledWith('c1'))
    expect(confirmar).toHaveBeenCalledTimes(1)
    await waitFor(() => expect(navegar).toHaveBeenCalledWith('/inventory/cargas'))
  })

  it('al reabrir una carga aplicada pide las etiquetas', async () => {
    api.obtener.mockResolvedValue(D({ carga: { estado: 'aplicada' } }))
    api.etiquetas.mockResolvedValue([{ marca: 'Marca Uno', producto: 'Camisa lino', sku: 'MU-CAM-M', talla: 'M', barcode: '2000000000017', piezas: '5.00', precio: '500.00' }])
    pintar()
    await screen.findByText('2000000000017')
    expect(api.etiquetas).toHaveBeenCalledWith('c1')
    expect(screen.getByRole('link', { name: /Imprimir etiquetas/ }).getAttribute('href')).toBe('/labels?carga=c1&folio=7')
  })

  it('si una mutación falla muestra un aviso', async () => {
    api.responder.mockRejectedValue({ response: { data: { detail: 'Carga bloqueada' } } })
    pintar()
    fireEvent.change(await screen.findByLabelText('Respuesta'), { target: { value: '1. 600' } })
    fireEvent.click(screen.getByRole('button', { name: 'Enviar' }))
    await waitFor(() => expect(avisos().some((a) => a.includes('Carga bloqueada'))).toBe(true))
  })

  it('si falla la recarga tras responder avisa', async () => {
    api.responder.mockResolvedValue({ cambio: null, rechazos: [] })
    api.obtener.mockResolvedValueOnce(D()).mockRejectedValue(new Error('red'))
    pintar()
    fireEvent.change(await screen.findByLabelText('Respuesta'), { target: { value: '1. 600' } })
    fireEvent.click(screen.getByRole('button', { name: 'Enviar' }))
    await waitFor(() => expect(avisos().some((a) => a.includes('no se pudo actualizar'))).toBe(true))
  })

  it('si autorizar falla (preguntas nuevas) recarga el detalle para enseñarlas', async () => {
    api.autorizar.mockRejectedValue({ response: { status: 409, data: { detail: 'Ahora hay preguntas nuevas' } } })
    api.obtener.mockResolvedValueOnce(D()).mockResolvedValue(D({ dudas: [duda(9, { texto: 'Pregunta nueva' })], puede_autorizar: false }))
    pintar()
    fireEvent.click(await screen.findByRole('button', { name: 'Autorizar' }))
    await screen.findByText('Pregunta nueva')
    expect(api.obtener).toHaveBeenCalledTimes(2)
    expect(avisos().some((a) => a.includes('Ahora hay preguntas nuevas'))).toBe(true)
  })

  it('si autorizar falla y la recarga también, avisa', async () => {
    api.autorizar.mockRejectedValue({ response: { status: 422, data: { detail: 'No se aplicó nada' } } })
    api.obtener.mockResolvedValueOnce(D()).mockRejectedValue(new Error('red'))
    pintar()
    fireEvent.click(await screen.findByRole('button', { name: 'Autorizar' }))
    await waitFor(() => expect(avisos().some((a) => a.includes('No se aplicó nada'))).toBe(true))
    expect(avisos().some((a) => a.includes('no se pudo actualizar'))).toBe(true)
  })

  it('si reintentar falla recarga el detalle', async () => {
    api.obtener.mockResolvedValueOnce(D({ carga: { estado: 'error', error: 'Falló' } }))
      .mockResolvedValue(D({ carga: { estado: 'error', error: 'Ya se aplicó' } }))
    api.reintentar.mockRejectedValue({ response: { status: 409, data: { detail: 'Esta carga ya se aplicó' } } })
    pintar()
    fireEvent.click(await screen.findByRole('button', { name: /Volver a intentar/ }))
    await screen.findByText('Ya se aplicó')
    expect(api.obtener).toHaveBeenCalledTimes(2)
  })

  it('dos toques seguidos en Autorizar abren un solo diálogo', async () => {
    confirmar.mockReturnValue(new Promise(() => {}))
    pintar()
    const b = await screen.findByRole('button', { name: 'Autorizar' })
    fireEvent.click(b); fireEvent.click(b)
    expect(confirmar).toHaveBeenCalledTimes(1)
  })
})
