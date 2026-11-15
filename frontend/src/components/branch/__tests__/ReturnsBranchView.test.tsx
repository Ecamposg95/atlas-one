// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, cleanup, fireEvent } from '@testing-library/react'

const { get } = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('../../../api/client', () => ({ default: { get, post: vi.fn() } }))

import { ReturnsBranchView } from '../ReturnsBranchView'
import { useAuthStore } from '../../../store/authStore'

const usuario = (role: string) =>
  useAuthStore.setState({ user: { id: 1, username: 'u', role, branch_id: 1, platform_role: 'NONE' } } as never)

beforeEach(() => {
  get.mockReset().mockRejectedValue({ response: { status: 404, data: { detail: 'Venta no encontrada' } } })
})
afterEach(cleanup)

function buscar(folio: string) {
  render(<ReturnsBranchView />)
  fireEvent.change(screen.getByPlaceholderText('V-0001234'), { target: { value: folio } })
  fireEvent.keyDown(screen.getByPlaceholderText('V-0001234'), { key: 'Enter' })
}

describe('ReturnsBranchView', () => {
  it('la cajera, ante un folio no encontrado, ve que solo aparecen ventas de hoy', async () => {
    usuario('CAJERO')
    buscar('A-12')
    expect(await screen.findByText('Ticket no encontrado. Solo aparecen ventas de hoy; para días anteriores pide al gerente.')).toBeTruthy()
    expect(get).toHaveBeenCalledWith('/sales/by-folio/A/12')
  })

  it('otro rol conserva el texto de siempre', async () => {
    usuario('GERENTE')
    buscar('A-12')
    expect(await screen.findByText('No encontré esa venta.')).toBeTruthy()
  })
})
