import { beforeEach, describe, expect, it, vi } from 'vitest'
import client from '../client'
import { printerApi } from '../printer'

vi.mock('../client', () => ({ default: { post: vi.fn(), get: vi.fn() } }))

describe('printerApi.abrirCajonManual', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('el cajón abierto no se vuelve error si falla el registro', async () => {
    vi.spyOn(printerApi, 'openDrawerViaAgent').mockResolvedValue()
    vi.mocked(client.post).mockRejectedValue(new Error('sin red'))
    await expect(printerApi.abrirCajonManual('POS-80')).resolves.toBeUndefined()
    expect(client.post).toHaveBeenCalledWith('/printer/drawer-opened', { printer_name: 'POS-80' })
  })

  it('si el agente falla no se registra nada', async () => {
    vi.mocked(client.post).mockReset()
    vi.spyOn(printerApi, 'openDrawerViaAgent').mockRejectedValue(new Error('apagada'))
    await expect(printerApi.abrirCajonManual('POS-80')).rejects.toThrow('apagada')
    expect(client.post).not.toHaveBeenCalled()
  })
})

describe('printerApi.getCashCutBase64', () => {
  it('por omisión no pide abrir el cajón', async () => {
    vi.mocked(client.post).mockReset()
    vi.mocked(client.post).mockResolvedValue({ data: { content_base64: 'x' } })
    await printerApi.getCashCutBase64(5)
    expect(client.post).toHaveBeenCalledWith('/printer/print-cash-cut', { session_id: 5, open_drawer: false })
  })
})
