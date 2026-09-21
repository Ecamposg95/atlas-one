import { describe, it, expect } from 'vitest'
import { claseEtiquetaFila, ETIQUETA_FILA_BASE } from './formResponsivo'

describe('claseEtiquetaFila', () => {
  it('la primera fila muestra su etiqueta en todos los anchos', () => {
    expect(claseEtiquetaFila(0)).toBe(ETIQUETA_FILA_BASE)
    expect(claseEtiquetaFila(0)).not.toContain('sm:hidden')
  })

  it('las filas siguientes muestran la etiqueta solo en teléfono', () => {
    // `block` (visible por defecto) + `sm:hidden` (oculta de 640 px hacia
    // arriba, donde la primera fila ya hace de encabezado de columna).
    expect(claseEtiquetaFila(1)).toBe(`${ETIQUETA_FILA_BASE} sm:hidden`)
    expect(claseEtiquetaFila(7)).toContain('sm:hidden')
    expect(claseEtiquetaFila(1)).toContain('block')
  })

  it('respeta un estilo base distinto', () => {
    expect(claseEtiquetaFila(0, 'block text-xs')).toBe('block text-xs')
    expect(claseEtiquetaFila(2, 'block text-xs')).toBe('block text-xs sm:hidden')
  })
})
