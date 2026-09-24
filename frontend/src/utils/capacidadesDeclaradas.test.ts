import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

/** Toda clave que la pantalla use tiene que existir en el catálogo del servidor.
 *  Sin esta red, alguien inventa una clave, `puede()` devuelve false para siempre
 *  y la función queda escondida sin que nadie sepa por qué. */
function archivos(dir: string): string[] {
  return readdirSync(dir).flatMap((n) => {
    const p = join(dir, n)
    return statSync(p).isDirectory() ? archivos(p) : p.match(/\.tsx?$/) ? [p] : []
  })
}

describe('claves de capacidad usadas en la pantalla', () => {
  it('todas existen en app/capacidades/catalogo.json', () => {
    const catalogo = JSON.parse(readFileSync('../app/capacidades/catalogo.json', 'utf-8'))
    const declaradas = new Set(catalogo.map((f: { clave: string }) => f.clave))
    const usadas = new Set<string>()
    for (const f of archivos('src')) {
      for (const m of readFileSync(f, 'utf-8').matchAll(/useCapacidad\(\s*['"]([a-z_]+)['"]/g)) {
        usadas.add(m[1])
      }
    }
    const inventadas = [...usadas].filter((c) => !declaradas.has(c))
    expect(inventadas).toEqual([])
  })
})
