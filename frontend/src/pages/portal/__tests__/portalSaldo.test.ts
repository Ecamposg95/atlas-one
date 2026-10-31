import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

/** El portal pintaba el saldo deudor en verde y el saldo a favor en rojo: al
 *  revés que el CRM (auditoría 2026-10-28 §3.7). */
const s = readFileSync(resolve(__dirname, '../Portal.tsx'), 'utf8')

describe('Portal: color del saldo', () => {
  it('deudor en rojo, a favor en verde, con tokens', () => {
    expect(s).not.toMatch(/current_balance < 0 \? 'text-red-400' : 'text-emerald-400'/)
    expect((s.match(/current_balance > 0 \? 'text-dax-danger' : 'text-dax-success'/g) ?? []).length).toBe(2)
  })
})
