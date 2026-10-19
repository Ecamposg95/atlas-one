import { describe, it, expect, beforeEach } from 'vitest'
const mk = (): Storage => {
  const m = new Map<string, string>()
  return {
    getItem: (k: string) => (m.has(k) ? m.get(k)! : null),
    setItem: (k: string, v: string) => void m.set(k, v),
    removeItem: (k: string) => void m.delete(k),
    clear: () => m.clear(),
    key: (i: number) => [...m.keys()][i] ?? null,
    get length() { return m.size },
  } as Storage
}
Object.assign(globalThis, { localStorage: mk(), sessionStorage: mk() })

import { useAuthStore } from '../authStore'
import { useImpersonationStore } from '../impersonationStore'
import { useEnabledModulesStore } from '../enabledModulesStore'

function sucio() {
  useEnabledModulesStore.setState({ perfilUi: 'basico', loaded: true, enabledModules: ['core'] })
}
function limpio() {
  const s = useEnabledModulesStore.getState()
  expect(s.loaded).toBe(false)
  expect(s.perfilUi).toBe('completo')
  expect(s.enabledModules).toEqual([])
}

describe('el contexto de la org se reinicia entre sesiones', () => {
  beforeEach(() => { useEnabledModulesStore.getState().reset() })
  it('logout', () => { sucio(); useAuthStore.getState().logout(); limpio() })
  it('suplantar: start', () => { sucio(); useImpersonationStore.getState().start(5, 'X'); limpio() })
  it('suplantar: exit', () => { sucio(); useImpersonationStore.getState().exit(); limpio() })
})
