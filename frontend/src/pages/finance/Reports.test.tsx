// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, cleanup, waitFor } from '@testing-library/react'

const { dashboard } = vi.hoisted(() => ({ dashboard: vi.fn() }))
vi.mock('../../api/reports', () => ({ reportsApi: { dashboard } }))
vi.mock('react-chartjs-2', () => ({ Bar: () => null }))
vi.mock('../../context/ThemeContext', () => ({ useTheme: () => ({ theme: 'dark' }) }))

import { Reports } from './Reports'
import { useAuthStore } from '../../store/authStore'
import { useEnabledModulesStore } from '../../store/enabledModulesStore'

const como = (perfilUi: 'basico' | 'completo', role: string) => {
  useEnabledModulesStore.setState({ perfilUi })
  useAuthStore.setState({ user: { role } as never })
}

beforeEach(() => { dashboard.mockReset().mockResolvedValue(null) })
afterEach(cleanup)

describe('Reports según perfil y rol', () => {
  it('dueña en básico pide la org entera (branch_id 0)', async () => {
    como('basico', 'DUEÑO')
    render(<Reports />)
    await waitFor(() => expect(dashboard).toHaveBeenCalled())
    expect(dashboard.mock.calls[0][0].branch_id).toBe(0)
  })
  it('cajera en básico y completo no mandan branch_id', async () => {
    como('basico', 'CAJERO')
    render(<Reports />)
    await waitFor(() => expect(dashboard).toHaveBeenCalled())
    expect('branch_id' in dashboard.mock.calls[0][0]).toBe(false)
    cleanup(); dashboard.mockClear()
    como('completo', 'DUEÑO')
    render(<Reports />)
    await waitFor(() => expect(dashboard).toHaveBeenCalled())
    expect('branch_id' in dashboard.mock.calls[0][0]).toBe(false)
  })
})
