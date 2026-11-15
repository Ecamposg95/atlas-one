// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react'

const api = vi.hoisted(() => ({ webPublish: vi.fn(async () => ({ processed: 1 })) }))
vi.mock('../../../api/products', () => ({ productsApi: api }))

import { DialogoPublicarWeb } from '../DialogoPublicarWeb'
import { useAuthStore } from '../../../store/authStore'
import { useEnabledModulesStore } from '../../../store/enabledModulesStore'

const como = (role: string, modulos: string[]) => {
  useAuthStore.setState({ user: { id: 1, username: 'u', role, branch_id: null, branch_name: null } } as never)
  useEnabledModulesStore.setState({ enabledModules: modulos } as never)
}
const pintar = (onClose = vi.fn()) => {
  render(<DialogoPublicarWeb producto={{ id: 'p-1', name: 'Playera' }} onClose={onClose} />)
  return onClose
}

beforeEach(() => vi.clearAllMocks())
afterEach(cleanup)

describe('DialogoPublicarWeb', () => {
  it('admin con módulo: pregunta y «Sí, publicar» publica ese producto', async () => {
    como('ADMINISTRADOR', ['tienda_en_linea'])
    const onClose = pintar()
    expect(screen.getByText('¿Lo publicamos también en la tienda web?')).toBeTruthy()
    fireEvent.click(screen.getByText('Sí, publicar'))
    await waitFor(() => expect(api.webPublish).toHaveBeenCalledWith({ ids: ['p-1'], published: true }))
    await waitFor(() => expect(onClose).toHaveBeenCalled())
  })

  it('«Ahora no» no llama a nada', () => {
    como('DUEÑO', ['tienda_en_linea'])
    const onClose = pintar()
    fireEvent.click(screen.getByText('Ahora no'))
    expect(api.webPublish).not.toHaveBeenCalled()
    expect(onClose).toHaveBeenCalled()
  })

  it('cajero o sin módulo: no se pinta', () => {
    como('CAJERO', ['tienda_en_linea'])
    pintar()
    expect(screen.queryByText('¿Lo publicamos también en la tienda web?')).toBeNull()
    cleanup()
    como('ADMINISTRADOR', [])
    pintar()
    expect(screen.queryByText('¿Lo publicamos también en la tienda web?')).toBeNull()
  })
})
