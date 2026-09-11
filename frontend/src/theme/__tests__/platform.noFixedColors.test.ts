import { describe, it, expect } from 'vitest'

// Spec 2026-09-09 §3.4: en los archivos que esta rebanada tocó no vuelven
// colores fijos. Los tokens --p-* (alias) y --dax-* son la única vía; el
// único hex tolerado es blanco sobre el acento. Las demás páginas de
// /platform heredan la piel pero conservan sus hex puntuales — entran al
// candado cuando se toquen (flujos del tablero y de reportes).
// Los fuentes entran como texto (`?raw`, Vite) porque el proyecto no tiene
// @types/node y `node:fs` no compila con `tsc --noEmit`.
import platformLayout from '../../pages/platform/PlatformLayout.tsx?raw'
import dataTable from '../../components/platform/DataTable.tsx?raw'
import platformPageShell from '../../components/platform/PlatformPageShell.tsx?raw'
import kpiCard from '../../components/platform/KPICard.tsx?raw'

const FILES: [string, string][] = [
  ['pages/platform/PlatformLayout.tsx', platformLayout],
  ['components/platform/DataTable.tsx', dataTable],
  ['components/platform/PlatformPageShell.tsx', platformPageShell],
  ['components/platform/KPICard.tsx', kpiCard],
]
const TAILWIND = /\b(hover:)?(text|bg|border)-(slate|gray|zinc|indigo)-[0-9]{2,3}\b|\btext-white\b(?!\/)|backdrop-blur/g
const HEX = /#[0-9a-fA-F]{3,8}\b/g

describe.each(FILES)('%s sin colores fijos', (name, src) => {
  it('no usa clases slate/gray/zinc/indigo, text-white sólido ni backdrop-blur', () => {
    const hits = [...src.matchAll(TAILWIND)].map((m) => m[0])
    expect(hits, `restos en ${name}: ${[...new Set(hits)].join(', ')}`).toEqual([])
  })

  it('no usa hex salvo #fff', () => {
    const hits = [...src.matchAll(HEX)].map((m) => m[0].toLowerCase()).filter((h) => h !== '#fff' && h !== '#ffffff')
    expect(hits, `hex en ${name}: ${[...new Set(hits)].join(', ')}`).toEqual([])
  })
})
