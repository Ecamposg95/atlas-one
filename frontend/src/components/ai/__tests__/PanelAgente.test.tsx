// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react'

const api = vi.hoisted(() => ({
  crear: vi.fn(), listar: vi.fn(), leer: vi.fn(), enviar: vi.fn(), borrar: vi.fn(),
}))
vi.mock('../../../api/ai', () => ({ aiApi: api }))
const telefono = vi.hoisted(() => ({ valor: false }))
vi.mock('../../../hooks/useIsMobile', () => ({ useEsTelefono: () => telefono.valor, useIsMobile: () => telefono.valor }))

import PanelAgente, { celda, mensajeDeError } from '../PanelAgente'
import { AnfitrionAgente, BotonAgente } from '../BotonAgente'
import { useAgenteStore } from '../../../store/agenteStore'
import { useAuthStore } from '../../../store/authStore'
import { useEnabledModulesStore } from '../../../store/enabledModulesStore'
import { NO_DISPONIBLES } from '../../../utils/estadoModulos'

const RESPUESTA = {
  id: 'm-2', rol: 'assistant', contenido: 'La playera cuesta $1,500 en tu sucursal.', created_at: '2026-11-24T10:00:00Z',
  tablas: [{
    titulo: 'Productos', columnas: ['Producto', 'Color / talla', 'SKU', 'Precio'],
    filas: [['Playera', 'Negro M', 'PLY-M', 1500], ['Playera', 'Negro L', 'PLY-L', null]], mas: 3,
  }],
}
const error = (status: number, detail?: string) => ({ response: { status, data: { detail } } })
const caja = () => screen.getByLabelText('Tu pregunta') as HTMLTextAreaElement
const preguntar = (texto: string) => {
  fireEvent.change(caja(), { target: { value: texto } })
  fireEvent.click(screen.getByText('Enviar'))
}
const sesion = (role: string, modulos: string[], noDisponibles: Record<string, 'en_construccion' | 'oculto'> = {}) => {
  useAuthStore.setState({ user: { id: 1, username: 'u', role, branch_id: 7 } } as never)
  useEnabledModulesStore.setState({ enabledModules: modulos, noDisponibles, loaded: true })
}

beforeEach(() => {
  vi.clearAllMocks()
  telefono.valor = false
  useAgenteStore.getState().reset()
  api.crear.mockResolvedValue({ id: 'c-1', titulo: null })
  api.enviar.mockResolvedValue(RESPUESTA)
})
afterEach(() => {
  cleanup()
  vi.unstubAllEnvs()
})

describe('PanelAgente', () => {
  it('abre con lo que la persona ya había escrito y sin conversación no llama al servidor', () => {
    useAgenteStore.getState().abrir('¿hay playera negra?')
    render(<PanelAgente />)
    expect(caja().value).toBe('¿hay playera negra?')
    expect(screen.getByText(/El agente solo consulta/)).toBeTruthy()
    expect(api.leer).not.toHaveBeenCalled()
    expect(api.crear).not.toHaveBeenCalled()
  })

  it('envía: crea la conversación, muestra la pregunta, la respuesta y la tabla del servidor', async () => {
    render(<PanelAgente />)
    preguntar('precio de la playera')
    expect(await screen.findByText('La playera cuesta $1,500 en tu sucursal.')).toBeTruthy()
    expect(api.crear).toHaveBeenCalledTimes(1)
    expect(api.enviar).toHaveBeenCalledWith('c-1', 'precio de la playera')
    expect(screen.getByText('precio de la playera')).toBeTruthy()
    expect(useAgenteStore.getState().conversacionId).toBe('c-1')
    expect(caja().value).toBe('')
    // Tabla de escritorio: encabezados, dinero con formato, vacío como raya y aviso de recorte.
    expect(screen.getByRole('table')).toBeTruthy()
    expect(screen.getByText('Color / talla')).toBeTruthy()
    expect(screen.getByText('$1,500.00')).toBeTruthy()
    expect(screen.getByText('—')).toBeTruthy()
    expect(screen.getByText(/y 3 más/)).toBeTruthy()
  })

  it('la segunda pregunta va a la misma conversación', async () => {
    render(<PanelAgente />)
    preguntar('uno')
    await screen.findByText(RESPUESTA.contenido)
    preguntar('dos')
    await waitFor(() => expect(api.enviar).toHaveBeenCalledTimes(2))
    expect(api.crear).toHaveBeenCalledTimes(1)
    expect(api.enviar).toHaveBeenLastCalledWith('c-1', 'dos')
  })

  it('en teléfono la tabla se pinta como lista, sin <table>', async () => {
    telefono.valor = true
    render(<PanelAgente />)
    preguntar('precio')
    await screen.findByText(RESPUESTA.contenido)
    expect(screen.queryByRole('table')).toBeNull()
    expect(screen.getByTestId('tabla-agente').textContent).toContain('PLY-M')
    expect(screen.getAllByText('Precio').length).toBe(2)
  })

  it('cupo agotado (429): avisa con el texto del servidor y devuelve la pregunta a la caja', async () => {
    api.enviar.mockRejectedValue(error(429, 'Se alcanzó el límite diario de uso de IA de tu organización. Intenta mañana.'))
    render(<PanelAgente />)
    preguntar('ventas de hoy')
    expect((await screen.findByRole('alert')).textContent).toContain('límite diario')
    expect(caja().value).toBe('ventas de hoy')
    expect(screen.queryByText('Consultando…')).toBeNull()
  })

  it('sin llave en el servidor (503): mensaje claro', async () => {
    api.enviar.mockRejectedValue(error(503, 'IA no configurada: falta ANTHROPIC_API_KEY en el servidor.'))
    render(<PanelAgente />)
    preguntar('hola')
    expect((await screen.findByRole('alert')).textContent).toContain('IA no configurada')
  })

  it('retoma la conversación en curso al abrir', async () => {
    useAgenteStore.getState().fijarConversacion('c-9')
    api.leer.mockResolvedValue({ id: 'c-9', titulo: 'x', mensajes: [
      { id: 'm-1', rol: 'user', contenido: 'pregunta vieja', tablas: [], created_at: '' }, RESPUESTA,
    ] })
    render(<PanelAgente />)
    expect(await screen.findByText('pregunta vieja')).toBeTruthy()
    expect(api.leer).toHaveBeenCalledWith('c-9')
  })

  it('conversación que ya no es de esta sesión (404): abre otra y manda la pregunta', async () => {
    useAgenteStore.getState().fijarConversacion('c-ajena')
    api.leer.mockResolvedValue({ id: 'c-ajena', titulo: null, mensajes: [] })
    api.crear.mockResolvedValue({ id: 'c-nueva', titulo: null })
    api.enviar.mockRejectedValueOnce(error(404, 'Conversación no encontrada.')).mockResolvedValueOnce(RESPUESTA)
    render(<PanelAgente />)
    await waitFor(() => expect(api.leer).toHaveBeenCalled())
    preguntar('precio')
    expect(await screen.findByText(RESPUESTA.contenido)).toBeTruthy()
    expect(api.enviar).toHaveBeenLastCalledWith('c-nueva', 'precio')
    expect(useAgenteStore.getState().conversacionId).toBe('c-nueva')
  })

  it('Nueva conversación limpia la pantalla y suelta la conversación', async () => {
    render(<PanelAgente />)
    preguntar('uno')
    await screen.findByText(RESPUESTA.contenido)
    fireEvent.click(screen.getByText('Nueva conversación'))
    expect(screen.queryByText(RESPUESTA.contenido)).toBeNull()
    expect(useAgenteStore.getState().conversacionId).toBeNull()
  })

  it('Enter envía y Shift+Enter no', async () => {
    render(<PanelAgente />)
    fireEvent.change(caja(), { target: { value: 'hola' } })
    fireEvent.keyDown(caja(), { key: 'Enter', shiftKey: true })
    expect(api.enviar).not.toHaveBeenCalled()
    fireEvent.keyDown(caja(), { key: 'Enter' })
    await waitFor(() => expect(api.enviar).toHaveBeenCalledWith('c-1', 'hola'))
  })
})

describe('celda y mensajeDeError', () => {
  it('formatea por tipo y por columna', () => {
    expect(celda(1500, 'Precio')).toBe('$1,500.00')
    expect(celda(12, 'Existencia')).toBe('12')
    expect(celda(null, 'Costo')).toBe('—')
    expect(celda(true, '¿Hay?')).toBe('Sí')
    expect(celda('Sí hay', '¿Hay?')).toBe('Sí hay')
  })
  it('sin respuesta del servidor da un texto genérico', () => {
    expect(mensajeDeError(new Error('red'))).toMatch(/No se pudo enviar/)
    expect(mensajeDeError(error(429))).toMatch(/límite de uso/)
  })
})

describe('BotonAgente: sigue la regla del módulo `ai`', () => {
  it('con `ai` en construcción no se pinta (hoy)', () => {
    sesion('CAJERO', ['pos', 'ai'], NO_DISPONIBLES as never)
    const { container } = render(<BotonAgente variante="texto" />)
    expect(container.innerHTML).toBe('')
  })

  it('sin el módulo encendido tampoco, aunque `ai` esté disponible', () => {
    sesion('DUEÑO', ['pos'])
    const { container } = render(<BotonAgente variante="barra" />)
    expect(container.innerHTML).toBe('')
  })

  it('vista previa (VITE_AGENTE_PREVIA=1): se ve aunque siga en construcción', () => {
    vi.stubEnv('VITE_AGENTE_PREVIA', '1')
    sesion('CAJERO', ['pos', 'ai'], NO_DISPONIBLES as never)
    render(<BotonAgente variante="barra" />)
    expect(screen.getByLabelText('Preguntar al agente')).toBeTruthy()
  })

  it('con `ai` disponible abre el panel (perezoso) con lo escrito', async () => {
    sesion('GERENTE', ['pos', 'ai'])
    render(<><BotonAgente variante="texto" borrador="  ¿hay talla 42?  " /><AnfitrionAgente /></>)
    expect(screen.queryByRole('dialog')).toBeNull()
    fireEvent.click(screen.getByText('Preguntar al agente'))
    expect(useAgenteStore.getState()).toMatchObject({ abierto: true, borrador: '¿hay talla 42?' })
    expect(await screen.findByRole('dialog')).toBeTruthy()
    expect(caja().value).toBe('¿hay talla 42?')
    fireEvent.click(screen.getByLabelText('Cerrar'))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  })
})
