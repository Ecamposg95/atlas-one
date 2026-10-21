import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

/** Nueva solicitud de transferencia (Logística): lo que la revisión final de SP5 cierre pidió. */
const s = readFileSync(resolve(__dirname, '../Logistics.tsx'), 'utf8')

describe('Logística · Nueva solicitud', () => {
  it('manda variant_id (el backend exige TransferLineCreate.variant_id), no variant_sku', () => {
    expect(s).toMatch(/variant_id: l\.variant_id/)
    expect(s).not.toMatch(/variant_sku/)
  })
  it('Escape no tira lo capturado y los resultados del buscador van en flujo (no absolute)', () => {
    expect(s).toMatch(/closeOnEscape=\{false\}/)
    expect(s).not.toMatch(/absolute z-30 top-full/)
  })
})
