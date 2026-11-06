import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

// Guardia de fuente: POS.tsx es demasiado pesado para montarlo. La regla de cuándo
// abrir vive en utils/cajon (con su prueba); aquí se fija que se use donde toca.
const leer = (rel: string) => readFileSync(resolve(__dirname, rel), 'utf8')
const pos = leer('../POS.tsx')

describe('el cajón en el POS', () => {
  it('sin ticket se pide aparte; con ticket va en los bytes', () => {
    expect(pos).toMatch(/if \(saleId && shouldPrint\) printViaAgent\(saleId\)\s+else if \(!shouldPrint\) abrirCajonSinTicket\(payments\)/)
  })

  it('una venta sin red también lo abre: el agente es local', () => {
    expect(pos).toMatch(/await enqueueSale\(payload\)[\s\S]{0,400}abrirCajonSinTicket\(payments\)/)
  })

  it('respeta el interruptor de la sucursal', () => {
    expect(pos).toMatch(/abreAlCobrar: leerCajonAlCobrar\(branch\?\.id\)/)
  })

  it('solo el cierre de turno pide abrirlo con el corte', () => {
    expect(pos).toMatch(/getCashCutBase64\(closed\.id, true\)/)
    expect(leer('../../finance/CashHistory.tsx')).not.toMatch(/getCashCutBase64\([^)]*true/)
    expect(leer('../../../components/branch/CashBranchView.tsx')).not.toMatch(/getCashCutBase64\([^)]*true/)
  })
})
