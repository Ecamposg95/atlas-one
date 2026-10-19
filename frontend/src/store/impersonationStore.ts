import { create } from 'zustand'
import { useEnabledModulesStore } from './enabledModulesStore'

interface ImpersonationState {
  orgId: number | null
  orgName: string | null
  start: (orgId: number, orgName: string) => void
  exit: () => void
  hydrate: () => void
}

const KEY = 'atlas_impersonate'

function read(): { orgId: number; orgName: string } | null {
  try {
    const raw = sessionStorage.getItem(KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (typeof parsed.orgId === 'number' && typeof parsed.orgName === 'string') return parsed
    return null
  } catch {
    return null
  }
}

function write(data: { orgId: number; orgName: string } | null) {
  if (data) sessionStorage.setItem(KEY, JSON.stringify(data))
  else sessionStorage.removeItem(KEY)
}

export const useImpersonationStore = create<ImpersonationState>((set) => ({
  orgId: null,
  orgName: null,
  start: (orgId, orgName) => {
    write({ orgId, orgName })
    set({ orgId, orgName })
    useEnabledModulesStore.getState().reset()
  },
  exit: () => {
    write(null)
    set({ orgId: null, orgName: null })
    useEnabledModulesStore.getState().reset()
  },
  hydrate: () => {
    const stored = read()
    if (stored) set({ orgId: stored.orgId, orgName: stored.orgName })
  },
}))
