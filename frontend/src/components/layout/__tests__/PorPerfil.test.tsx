// frontend/src/components/layout/__tests__/PorPerfil.test.tsx
// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'

const { get } = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('../../../api/client', () => ({ default: { get } }))

import { PorPerfil } from '../PorPerfil'
import { useEnabledModulesStore } from '../../../store/enabledModulesStore'

const pintar = () => render(<PorPerfil basico={<p>pantalla básica</p>} completo={<p>pantalla completa</p>} />)

beforeEach(() => { useEnabledModulesStore.getState().reset(); get.mockReset() })
afterEach(cleanup)

describe('PorPerfil (Review Focus #1)', () => {
  it('mientras el contexto no llega no monta ninguna de las dos y lo pide', () => {
    get.mockReturnValue(new Promise(() => {}))
    pintar()
    expect(screen.queryByText('pantalla básica')).toBeNull()
    expect(screen.queryByText('pantalla completa')).toBeNull()
    expect(get).toHaveBeenCalledWith('/users/me/context')
  })

  it('FREE: monta solo la básica', async () => {
    get.mockResolvedValue({ data: { enabled_modules: ['core'], perfil_ui: 'basico' } })
    pintar()
    expect(await screen.findByText('pantalla básica')).toBeTruthy()
    expect(screen.queryByText('pantalla completa')).toBeNull()
  })

  it('de paga o servidor viejo: la completa', async () => {
    get.mockResolvedValue({ data: { enabled_modules: ['core'] } })
    pintar()
    expect(await screen.findByText('pantalla completa')).toBeTruthy()
  })

  it('si el contexto falla: la completa', async () => {
    get.mockRejectedValue(new Error('red caída'))
    pintar()
    expect(await screen.findByText('pantalla completa')).toBeTruthy()
    expect(screen.queryByText('pantalla básica')).toBeNull()
  })
})
