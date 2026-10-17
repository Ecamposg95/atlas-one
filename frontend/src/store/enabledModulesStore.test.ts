import { describe, it, expect, vi, beforeEach } from 'vitest'

const get = vi.fn()
vi.mock('../api/client', () => ({ default: { get: (...a: unknown[]) => get(...a) } }))

const { useEnabledModulesStore } = await import('./enabledModulesStore')

beforeEach(() => {
  useEnabledModulesStore.getState().reset()
  get.mockReset()
})

describe('enabledModulesStore: campos_producto', () => {
  it('guarda lo que manda el contexto', async () => {
    get.mockResolvedValue({ data: {
      enabled_modules: ['core', 'variants'], preset: 'ATLAS_POS', capacidades: [],
      campos_producto: { visibles: ['name'], ocultos: ['gender', 'model', 'material'] },
    } })
    await useEnabledModulesStore.getState().load()
    expect(useEnabledModulesStore.getState().camposProducto.ocultos).toEqual(['gender', 'model', 'material'])
  })

  it('sin el campo, o si el contexto falla, todo es visible', async () => {
    get.mockResolvedValue({ data: { enabled_modules: ['core'], preset: null, capacidades: [] } })
    await useEnabledModulesStore.getState().load()
    expect(useEnabledModulesStore.getState().camposProducto).toEqual({ visibles: [], ocultos: [] })

    useEnabledModulesStore.getState().reset()
    get.mockRejectedValue(new Error('red'))
    await useEnabledModulesStore.getState().load()
    expect(useEnabledModulesStore.getState().camposProducto).toEqual({ visibles: [], ocultos: [] })
  })
})
