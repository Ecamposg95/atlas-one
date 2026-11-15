// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react'

const api = vi.hoisted(() => ({
  getOrg: vi.fn(),
  getBranches: vi.fn(async () => []),
  getExchangeRate: vi.fn(async () => ({ mode: 'off', rate: null, source: null, fix_rate: null, fix_date: null, margin: '0', manual_rate: null })),
  updateOrg: vi.fn(),
}))
const prod = vi.hoisted(() => ({
  getBrands: vi.fn(async () => [{ id: 'b1', name: 'Marca Uno', logo_url: null }]),
  getDepartments: vi.fn(async () => [{ id: 'd1', name: 'Ropa Dos' }]),
}))
vi.mock('../../../api/organization', async (orig) => ({ ...(await orig<object>()), organizationApi: api }))
vi.mock('../../../api/products', () => ({ productsApi: prod }))
vi.mock('../../../api/client', () => ({ default: { get: vi.fn(), post: vi.fn(), delete: vi.fn() } }))

import { Organization } from '../Organization'
import { useEnabledModulesStore } from '../../../store/enabledModulesStore'

const ORG = {
  id: 1, name: 'Casa Dos', tax_id: null, address: null, phone: null, email: null, logo_url: null, website: null,
  ticket_header: null, ticket_footer: null, industry_type: 'ATLAS_POS', usd_rate_mode: 'off',
  usd_rate_margin: '0', card_surcharge_pct: '0', ticket_line_style: 'compact', ticket_show_vendor: false,
  perfil_ui: null, umbral_poca_existencia: null, ai_instrucciones: 'Sé breve',
  reglas_carga: {
    costo_si_falta: 'fraccion_precio', fraccion: '0.5', iva: true, sucursal_recibe: null,
    activar_en: 'todas_las_que_venden', mapa_tallas: {}, escala_ropa: ['CH', 'M'], tipos: {},
    materiales_aparte: [], material_normal: null, genero_por_marca: {}, genero_por_omision: null,
    sufijo_dama: null, matriz_por_omision: 'solo_lo_que_hay', precios_familia: [], ventana_ya_cargado_dias: 21,
  },
}

beforeEach(() => {
  vi.clearAllMocks()
  api.getOrg.mockResolvedValue(JSON.parse(JSON.stringify(ORG)))
  api.updateOrg.mockImplementation(async (d: object) => ({ ...ORG, ...d }))
  useEnabledModulesStore.setState({ loaded: true, perfilUi: 'completo', enabledModules: ['ai'] } as never)
})
afterEach(cleanup)

describe('Empresa: reglas de carga', () => {
  it('carga reglas existentes y guarda cambios con PUT', async () => {
    render(<Organization />)
    const ventana = (await screen.findByLabelText('Días para avisar "ya cargado"')) as HTMLInputElement
    expect(ventana.value).toBe('21')
    expect((screen.getByLabelText('IVA incluido en los precios') as HTMLInputElement).checked).toBe(true)
    fireEvent.change(ventana, { target: { value: '30' } })
    fireEvent.click(screen.getByText('Guardar reglas de carga'))
    await waitFor(() => expect(api.updateOrg).toHaveBeenCalled())
    const enviado = api.updateOrg.mock.calls[0][0]
    expect(Object.keys(enviado)).toEqual(['reglas_carga'])
    expect(enviado.reglas_carga.ventana_ya_cargado_dias).toBe(30)
    expect(enviado.reglas_carga.fraccion).toBe('0.5')
    expect(enviado.reglas_carga.escala_ropa).toEqual(['CH', 'M'])
  })

  it('agregar una fila de tipo de prenda la envía en reglas_carga.tipos', async () => {
    render(<Organization />)
    fireEvent.click(await screen.findByText('Agregar tipo de prenda'))
    fireEvent.change(screen.getByLabelText('Tipo de prenda 1'), { target: { value: 'camisa' } })
    fireEvent.change(screen.getByLabelText('Código SKU 1'), { target: { value: 'CAM' } })
    await waitFor(() => expect(screen.getByRole('option', { name: 'Ropa Dos' })).toBeTruthy())
    fireEvent.change(screen.getByLabelText('Departamento 1'), { target: { value: 'Ropa Dos' } })
    fireEvent.click(screen.getByText('Guardar reglas de carga'))
    await waitFor(() => expect(api.updateOrg).toHaveBeenCalled())
    expect(api.updateOrg.mock.calls[0][0].reglas_carga.tipos).toEqual({ camisa: { codigo_sku: 'CAM', departamento: 'Ropa Dos' } })
  })

  it('un 422 se muestra junto al campo', async () => {
    api.updateOrg.mockRejectedValueOnce({ response: { data: { detail: [{ loc: ['body', 'reglas_carga', 'fraccion'], msg: 'Input should be a valid decimal' }] } } })
    render(<Organization />)
    fireEvent.click(await screen.findByText('Guardar reglas de carga'))
    expect(await screen.findByText('Input should be a valid decimal')).toBeTruthy()
  })

  it('las instrucciones de la IA se guardan solas', async () => {
    render(<Organization />)
    const t = (await screen.findByLabelText('Instrucciones para la IA')) as HTMLTextAreaElement
    expect(t.value).toBe('Sé breve')
    fireEvent.change(t, { target: { value: 'Otra' } })
    fireEvent.click(screen.getByText('Guardar instrucciones'))
    await waitFor(() => expect(api.updateOrg).toHaveBeenCalledWith({ ai_instrucciones: 'Otra' }))
  })

  it('sin módulo ai no muestra las secciones', async () => {
    useEnabledModulesStore.setState({ enabledModules: [] } as never)
    render(<Organization />)
    expect(await screen.findByText('Información de la Empresa')).toBeTruthy()
    expect(screen.queryByText('Reglas de carga')).toBeNull()
    expect(screen.queryByLabelText('Instrucciones para la IA')).toBeNull()
  })
})
