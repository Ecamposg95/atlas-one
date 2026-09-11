import { describe, it, expect } from 'vitest'

import { errorDetailText } from './errorDetail'

// FastAPI devuelve `detail` como CADENA en los errores que lanzamos nosotros
// (`HTTPException(detail="...")`) pero como ARREGLO de objetos en los 422 de
// validación de Pydantic. Pintarlo directo en un toast produce
// "[object Object]" justo cuando el usuario más necesita entender qué pasó.

const FALLBACK = 'No se pudo cerrar la caja — reintenta'

describe('errorDetailText', () => {
  it('usa el motivo real cuando es una cadena', () => {
    expect(errorDetailText('Debes escribir una nota', FALLBACK)).toBe('Debes escribir una nota')
  })

  it('NO pinta [object Object] con el arreglo de un 422', () => {
    const detail = [{ loc: ['body', 'notes'], msg: 'field required', type: 'value_error' }]
    const out = errorDetailText(detail, FALLBACK)
    expect(out).not.toContain('[object Object]')
    expect(out).toBe('field required')
  })

  it('junta varios mensajes de validación', () => {
    const detail = [{ msg: 'campo requerido' }, { msg: 'debe ser mayor a cero' }]
    expect(errorDetailText(detail, FALLBACK)).toBe('campo requerido; debe ser mayor a cero')
  })

  it('cae al mensaje por defecto si no hay nada usable', () => {
    expect(errorDetailText(undefined, FALLBACK)).toBe(FALLBACK)
    expect(errorDetailText(null, FALLBACK)).toBe(FALLBACK)
    expect(errorDetailText('', FALLBACK)).toBe(FALLBACK)
    expect(errorDetailText([], FALLBACK)).toBe(FALLBACK)
    expect(errorDetailText({ algo: 'raro' }, FALLBACK)).toBe(FALLBACK)
  })

  it('un arreglo sin msg no rompe', () => {
    expect(errorDetailText([{ loc: ['body'] }], FALLBACK)).toBe(FALLBACK)
  })
})
