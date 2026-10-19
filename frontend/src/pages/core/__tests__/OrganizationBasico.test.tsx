// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react'

const api = vi.hoisted(() => ({
  getOrg: vi.fn(),
  getBranches: vi.fn(async () => []),
  getExchangeRate: vi.fn(async () => ({ mode: 'off', rate: null, source: null, fix_rate: null, fix_date: null, margin: '0', manual_rate: null })),
  updateOrg: vi.fn(),
}))
vi.mock('../../../api/organization', () => ({ organizationApi: api }))
vi.mock('../../../api/client', () => ({ default: { get: vi.fn(), post: vi.fn(), delete: vi.fn() } }))

import { Organization } from '../Organization'
import { useEnabledModulesStore } from '../../../store/enabledModulesStore'

const ORG = {
  id: 1, name: 'Kaory', tax_id: null, address: null, phone: null, email: null, logo_url: null, website: null,
  ticket_header: 'Kaory', ticket_footer: 'Gracias', industry_type: 'ATLAS_POS', usd_rate_mode: 'off',
  usd_rate_margin: '0', card_surcharge_pct: '0', ticket_line_style: 'compact', ticket_show_vendor: false,
  perfil_ui: null, umbral_poca_existencia: null,
}

beforeEach(() => {
  vi.clearAllMocks()
  api.getOrg.mockResolvedValue({ ...ORG })
  api.updateOrg.mockImplementation(async (d: object) => ({ ...ORG, ...d }))
})
afterEach(cleanup)

describe('Empresa', () => {
  it('completo: todo a la vista, sin Más opciones ni tope', async () => {
    useEnabledModulesStore.setState({ loaded: true, perfilUi: 'completo' } as never)
    render(<Organization />)
    expect(await screen.findByText(/Tipo de cambio USD/)).toBeTruthy()
    expect(screen.getByText('Términos y condiciones')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Más opciones' })).toBeNull()
    expect(screen.queryByLabelText(/Avisar cuando queden/)).toBeNull()
  })

  it('básico: datos, encabezado y pie; lo demás plegado y sin montar', async () => {
    useEnabledModulesStore.setState({ loaded: true, perfilUi: 'basico' } as never)
    render(<Organization />)
    expect(await screen.findByText('Información de la Empresa')).toBeTruthy()
    expect(screen.getByText('Encabezado del ticket')).toBeTruthy()
    expect(screen.getByText('Pie de página del ticket')).toBeTruthy()
    expect(screen.queryByText(/Tipo de cambio USD/)).toBeNull()
    expect(screen.queryByText('Términos y condiciones')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Más opciones' }))
    expect(screen.getByText(/Tipo de cambio USD/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Más opciones del ticket' }))
    expect(screen.getByText('Términos y condiciones')).toBeTruthy()
  })

  it('básico: el tope de "se está acabando" se guarda', async () => {
    useEnabledModulesStore.setState({ loaded: true, perfilUi: 'basico' } as never)
    render(<Organization />)
    const tope = await screen.findByLabelText(/Avisar cuando queden/)
    fireEvent.change(tope, { target: { value: '5' } })
    fireEvent.click(screen.getByText('Guardar aviso'))
    await waitFor(() => expect(api.updateOrg).toHaveBeenCalledWith(expect.objectContaining({ umbral_poca_existencia: 5 })))
    expect(api.updateOrg.mock.calls[0][0]).not.toHaveProperty('perfil_ui')
  })
})
