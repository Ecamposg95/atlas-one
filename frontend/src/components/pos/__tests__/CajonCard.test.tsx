// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { printerApi } from '../../../api/printer'
import { toast } from '../../../store/toastStore'
import { CajonCard } from '../CajonCard'

vi.mock('../../../api/printer', () => ({ printerApi: { abrirCajonManual: vi.fn() } }))
vi.mock('../../../store/toastStore', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

const abrir = vi.mocked(printerApi.abrirCajonManual)
const boton = () => screen.getByRole('button', { name: /Abrir cajón ahora/ }) as HTMLButtonElement

describe('CajonCard', () => {
  beforeEach(() => vi.clearAllMocks())
  afterEach(cleanup)

  it('abre el cajón de la impresora elegida', async () => {
    abrir.mockResolvedValue()
    render(<CajonCard impresora="POS-80" agenteEnLinea abreAlCobrar />)
    fireEvent.click(boton())
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('Cajón abierto'))
    expect(abrir).toHaveBeenCalledWith('POS-80')
  })

  it('sin impresora el botón no responde y dice por qué', () => {
    render(<CajonCard impresora={null} agenteEnLinea abreAlCobrar />)
    expect(boton().disabled).toBe(true)
    expect(screen.getByText('Elige tu impresora primero.')).toBeTruthy()
  })

  it('avisa si el agente falla', async () => {
    abrir.mockRejectedValue(new Error('impresora apagada'))
    render(<CajonCard impresora="POS-80" agenteEnLinea abreAlCobrar />)
    fireEvent.click(boton())
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('No se pudo abrir el cajón: impresora apagada'))
  })

  it('sin permiso de administrar no hay casilla, solo el estado', () => {
    render(<CajonCard impresora="POS-80" agenteEnLinea abreAlCobrar={false} />)
    expect(screen.queryByRole('checkbox')).toBeNull()
    expect(screen.getByText('En esta sucursal no se abre solo al cobrar.')).toBeTruthy()
  })

  it('quien administra cambia el ajuste', async () => {
    const cambiar = vi.fn().mockResolvedValue(undefined)
    render(<CajonCard impresora="POS-80" agenteEnLinea abreAlCobrar onCambiarAbreAlCobrar={cambiar} />)
    fireEvent.click(screen.getByRole('checkbox'))
    await waitFor(() => expect(cambiar).toHaveBeenCalledWith(false))
  })
})
