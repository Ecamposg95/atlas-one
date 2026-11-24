// frontend/src/utils/coloresDePreset.test.ts
/// <reference types="node" />
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

/** Acento único (Atlas Horizon, 2026-11-18): ningún preset cambia el color.
 *  Antes cada giro traía el suyo; se retiró para que toda la plataforma lleve
 *  el ámbar de la marca. Si alguien vuelve a declarar un acento por preset,
 *  esta prueba lo frena. */
describe('acento único', () => {
  const css = readFileSync('src/index.css', 'utf-8')

  it('ningún preset redefine el acento', () => {
    const bloques = [...css.matchAll(/\[data-preset="[A-Z_0-9]+"\]\s*\{[^}]*\}/g)].map((m) => m[0])
    expect(bloques.filter((b) => b.includes('--p-accent'))).toEqual([])
  })

  it('el acento es el ámbar de la marca', () => {
    expect(/--p-accent:\s*#FF6A1F;/.test(css)).toBe(true)
  })
})
