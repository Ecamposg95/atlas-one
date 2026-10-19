import { describe, it, expect, vi, beforeEach } from 'vitest'

// `vi.mock` se iza por encima de los imports: lo que use la fábrica tiene que
// venir de `vi.hoisted`, no de una const del módulo.
const { get } = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('../../api/client', () => ({ default: { get } }))

import { useEnabledModulesStore } from '../enabledModulesStore'

const contexto = (extra: Record<string, unknown>) => ({
  data: { enabled_modules: ['core', 'pos'], preset: 'ATLAS_POS', capacidades: [], ...extra },
})

beforeEach(() => {
  useEnabledModulesStore.getState().reset()
  get.mockReset()
})

describe('enabledModulesStore.plan', () => {
  it('guarda el plan que manda /users/me/context', async () => {
    get.mockResolvedValue(contexto({ plan: { clave: 'FREE', nombre: 'ONE FREE' } }))
    await useEnabledModulesStore.getState().load()
    expect(useEnabledModulesStore.getState().plan).toEqual({ clave: 'FREE', nombre: 'ONE FREE' })
    expect(useEnabledModulesStore.getState().enabledModules).toEqual(['core', 'pos'])
  })

  it('sin `plan` en la respuesta (servidor viejo) queda null y lo demás carga igual', async () => {
    get.mockResolvedValue(contexto({}))
    await useEnabledModulesStore.getState().load()
    expect(useEnabledModulesStore.getState().plan).toBeNull()
    expect(useEnabledModulesStore.getState().loaded).toBe(true)
  })

  it('un plan mal formado (sin nombre) se descarta en vez de romper el menú', async () => {
    get.mockResolvedValue(contexto({ plan: { clave: 'FREE' } }))
    await useEnabledModulesStore.getState().load()
    expect(useEnabledModulesStore.getState().plan).toBeNull()
  })

  it('si la petición falla, plan null y loaded true (fail-open)', async () => {
    get.mockRejectedValue(new Error('red caída'))
    await useEnabledModulesStore.getState().load()
    expect(useEnabledModulesStore.getState().plan).toBeNull()
    expect(useEnabledModulesStore.getState().loaded).toBe(true)
  })

  it('reset vuelve el plan a null', async () => {
    get.mockResolvedValue(contexto({ plan: { clave: 'PRO', nombre: 'ONE PRO' } }))
    await useEnabledModulesStore.getState().load()
    useEnabledModulesStore.getState().reset()
    expect(useEnabledModulesStore.getState().plan).toBeNull()
  })
})
