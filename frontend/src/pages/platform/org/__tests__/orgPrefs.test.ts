import { beforeEach, describe, expect, it } from 'vitest'
import { MODE_KEY, ORG_KEY, readMode, readOrgId, writeMode, writeOrgId } from '../orgPrefs'

// El entorno de vitest es `node`: no hay `localStorage`. Se instala uno de
// juguete para probar la lógica real de lectura/escritura/default.
const almacen = new Map<string, string>()
;(globalThis as unknown as { localStorage: Storage }).localStorage = {
  getItem: (k: string) => (almacen.has(k) ? almacen.get(k)! : null),
  setItem: (k: string, v: string) => void almacen.set(k, v),
  removeItem: (k: string) => void almacen.delete(k),
  clear: () => almacen.clear(),
  key: (i: number) => [...almacen.keys()][i] ?? null,
  get length() {
    return almacen.size
  },
} as Storage

// El modo (Global/Organización) y la organización mirada se recuerdan en
// localStorage; default Global y sin organización; basura → default.
describe('orgPrefs', () => {
  beforeEach(() => almacen.clear())

  it('default: modo global y sin organización recordada', () => {
    expect(readMode()).toBe('global')
    expect(readOrgId()).toBeNull()
  })

  it('persiste y relee modo y organización con las llaves fijas', () => {
    writeMode('organizacion')
    writeOrgId(42)
    expect(almacen.get(MODE_KEY)).toBe('organizacion')
    expect(almacen.get(ORG_KEY)).toBe('42')
    expect(readMode()).toBe('organizacion')
    expect(readOrgId()).toBe(42)
  })

  it('un valor basura cae al default', () => {
    almacen.set(MODE_KEY, 'marte')
    almacen.set(ORG_KEY, 'la de la esquina')
    expect(readMode()).toBe('global')
    expect(readOrgId()).toBeNull()
  })

  it('un id no entero o no positivo no es una organización', () => {
    almacen.set(ORG_KEY, '0')
    expect(readOrgId()).toBeNull()
    almacen.set(ORG_KEY, '-3')
    expect(readOrgId()).toBeNull()
    almacen.set(ORG_KEY, '7.5')
    expect(readOrgId()).toBeNull()
  })

  it('escribir null olvida la organización', () => {
    writeOrgId(9)
    writeOrgId(null)
    expect(almacen.has(ORG_KEY)).toBe(false)
    expect(readOrgId()).toBeNull()
  })
})
