import type { PlatformMode } from '../../../types/platformOverview'

export const MODE_KEY = 'atlas_platform_mode'
/** La organización que el superadmin estaba mirando. Aquí NO se guarda un
 *  "grupo": es un cliente concreto, y al volver quiere verlo a él. */
export const ORG_KEY = 'atlas_platform_org'

function read(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

function write(key: string, value: string): void {
  try {
    localStorage.setItem(key, value)
  } catch {
    /* modo privado o bloqueado */
  }
}

function remove(key: string): void {
  try {
    localStorage.removeItem(key)
  } catch {
    /* modo privado o bloqueado */
  }
}

export function readMode(): PlatformMode {
  return read(MODE_KEY) === 'organizacion' ? 'organizacion' : 'global'
}

export function writeMode(mode: PlatformMode): void {
  write(MODE_KEY, mode)
}

/** `null` cuando no hay nada recordado o lo recordado no es un id usable. */
export function readOrgId(): number | null {
  const raw = read(ORG_KEY)
  if (raw === null) return null
  const id = Number(raw)
  return Number.isInteger(id) && id > 0 ? id : null
}

export function writeOrgId(orgId: number | null): void {
  if (orgId === null) remove(ORG_KEY)
  else write(ORG_KEY, String(orgId))
}
