import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'

/**
 * Tipografía Atlas Horizon (2026-11-18): Inter para todo, JetBrains Mono para
 * folios y códigos, y nunca peso 700. index.css carga Inter solo hasta 600, así
 * que un 700 lo engruesa el navegador a mano (negrita sintética).
 */
const SRC = resolve(__dirname, '..')

function archivos(dir: string): string[] {
  return readdirSync(dir).flatMap((nombre) => {
    const ruta = join(dir, nombre)
    if (statSync(ruta).isDirectory()) return nombre === '__tests__' ? [] : archivos(ruta)
    return /\.(tsx?|css)$/.test(nombre) && !/\.test\.tsx?$/.test(nombre) ? [ruta] : []
  })
}

// La vista previa del ticket térmico imita la negrita que imprime la impresora
// (ESC/POS); es el papel, no la interfaz de la marca.
const EXENTOS = ['pages/pos/PrinterSettings.tsx']

function hallazgos(patron: RegExp, exentos: string[] = []): string[] {
  return archivos(SRC)
    .filter((ruta) => !exentos.includes(ruta.slice(SRC.length + 1)))
    .flatMap((ruta) =>
    readFileSync(ruta, 'utf8')
      .split('\n')
      .flatMap((linea, i) => (patron.test(linea) ? [`${ruta.slice(SRC.length + 1)}:${i + 1}`] : [])),
  )
}

describe('tipografía Horizon', () => {
  it('ningún peso mayor a 600 escrito a mano', () => {
    expect(
      hallazgos(/font-weight:\s*(700|800|900|bold)\b|fontWeight:\s*(['"]?(700|800|900)\b|['"]bold['"])|\?\s*(700|800|900)\s*:/, EXENTOS),
    ).toEqual([])
  })

  it('sin fuentes retiradas (IBM Plex, Montserrat, Barlow, Archivo Black)', () => {
    expect(hallazgos(/IBM Plex|Montserrat|Barlow|Archivo Black/)).toEqual([])
  })

  it('Tailwind manda font-bold, extrabold y black a 600', () => {
    const tw = readFileSync(resolve(SRC, '..', 'tailwind.config.js'), 'utf8')
    for (const clase of ['bold', 'extrabold', 'black']) {
      expect(tw).toMatch(new RegExp(`${clase}:\\s*'600'`))
    }
  })
})
