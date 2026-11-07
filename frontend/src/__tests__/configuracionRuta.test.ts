import { execSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const raiz = resolve(__dirname, '..')

describe('Impresora ahora es Configuración', () => {
  it('la URL vieja redirige conservando la consulta', () => {
    const app = readFileSync(resolve(raiz, 'App.tsx'), 'utf8')
    expect(app).toMatch(/path="printer-settings" element=\{<RedirigirConQuery a="\/configuracion" \/>\}/)
    expect(app).toMatch(/path="configuracion" element=\{<RutaPorRol url="\/configuracion">/)
  })

  it('ninguna pantalla enlaza a la URL vieja', () => {
    const hits = execSync(`grep -rl "/printer-settings" "${raiz}" --include=*.ts --include=*.tsx || true`)
      .toString().split('\n').filter(Boolean).map((f) => f.replace(raiz + '/', ''))
    expect(hits).toEqual(['__tests__/configuracionRuta.test.ts'])
  })
})
