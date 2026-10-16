import { describe, it, expect } from 'vitest'

// Una sola librería de gráficas (chart.js). Si alguien vuelve a importar
// recharts, el chunk `CartesianChart` (340 KB) regresa a la plataforma.
const fuentes = import.meta.glob('/src/**/*.{ts,tsx}', { query: '?raw', import: 'default', eager: true }) as Record<string, string>

describe('librería de gráficas única', () => {
  it('ningún archivo de src importa recharts', () => {
    const culpables = Object.entries(fuentes)
      .filter(([ruta]) => !ruta.includes('/__tests__/'))
      .filter(([, src]) => /from ['"]recharts['"]/.test(src))
      .map(([ruta]) => ruta)
    expect(culpables).toEqual([])
  })
})
