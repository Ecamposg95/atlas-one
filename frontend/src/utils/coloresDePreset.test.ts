// frontend/src/utils/coloresDePreset.test.ts
/// <reference types="node" />
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

/** Todo preset que exista tiene color propio. Sin esto, Eleven y Kaory caían al
 *  color por defecto y se veían idénticas entre sí y que un restaurante. */
describe('color por preset', () => {
  it('ningún preset se queda sin acento', () => {
    const css = readFileSync('src/index.css', 'utf-8')
    const conColor = new Set(
      [...css.matchAll(/\[data-preset="([A-Z_0-9]+)"\]/g)].map((m) => m[1]),
    )
    const seed = readFileSync('../scripts/init_presets_v2.py', 'utf-8')
    const todos = [...seed.matchAll(/"id":\s*"([A-Z_0-9]+)"/g)].map((m) => m[1])
    const sinColor = todos.filter((p) => !conColor.has(p))
    expect(sinColor).toEqual([])
  })
})
