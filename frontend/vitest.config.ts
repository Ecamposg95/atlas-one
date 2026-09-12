import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
    // Sin esto Vitest devuelve cadena vacía para cualquier import de CSS,
    // incluso con `?raw`. Las pruebas de tokens y breakpoints leen
    // index.css y platform-v2.css como texto por esa vía (el proyecto no
    // tiene @types/node, así que `node:fs` no compila con tsc).
    css: true,
  },
})
