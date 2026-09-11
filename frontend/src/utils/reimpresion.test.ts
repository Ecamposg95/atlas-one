import { describe, expect, it } from 'vitest'
import { mensajeReimpresion, pinBloqueado, pinIncorrecto, requierePin } from './reimpresion'

const error = (status: number, detail?: unknown) => ({ response: { status, data: { detail } } })
const pinMal = error(403, { code: 'PIN_INCORRECTO', message: 'PIN incorrecto' })

describe('requierePin', () => {
  it('reconoce el 428 del backend', () => {
    expect(requierePin(error(428, 'Se requiere el PIN de un supervisor'))).toBe(true)
  })

  it('no confunde el 403 del PIN incorrecto con la falta de PIN', () => {
    expect(requierePin(pinMal)).toBe(false)
  })

  it('tolera un error sin respuesta (red caida)', () => {
    expect(requierePin(new Error('Network Error'))).toBe(false)
    expect(requierePin(undefined)).toBe(false)
  })
})

describe('pinIncorrecto y pinBloqueado', () => {
  it('distingue reintentar (403 con codigo) de esperar (423)', () => {
    expect(pinIncorrecto(pinMal)).toBe(true)
    expect(pinBloqueado(pinMal)).toBe(false)
    expect(pinBloqueado(error(423))).toBe(true)
    expect(pinIncorrecto(error(423))).toBe(false)
  })

  it('un 403 que NO es del PIN no deja el modal reintentando', () => {
    // El mismo endpoint responde 403 cuando la venta es de otra organizacion.
    expect(pinIncorrecto(error(403, 'Sin acceso a esta venta'))).toBe(false)
    expect(pinIncorrecto(error(403))).toBe(false)
  })
})

describe('mensajeReimpresion', () => {
  it('prefiere el detalle del backend, que dice cuanto falta', () => {
    const msg = mensajeReimpresion(error(423, 'Demasiados intentos fallidos. Intenta de nuevo en 840 segundos.'))
    expect(msg).toContain('840 segundos')
  })

  it('explica la venta cancelada en vez de un error generico', () => {
    const msg = mensajeReimpresion(error(409, 'Esta venta esta cancelada: su ticket ya no se puede reimprimir.'))
    expect(msg).toContain('cancelada')
  })

  it('lee el mensaje del detalle estructurado', () => {
    expect(mensajeReimpresion(pinMal)).toBe('PIN incorrecto')
  })

  it('tiene texto propio cuando el backend no manda detalle', () => {
    expect(mensajeReimpresion(error(428))).toBe('Se requiere el PIN de un supervisor')
    expect(mensajeReimpresion(error(423))).toContain('intentos fallidos')
  })

  it('ignora un detalle que no es texto (el 422 manda una lista)', () => {
    expect(mensajeReimpresion(error(422, [{ loc: ['body'], msg: 'x' }]))).toBe('Error al reimprimir')
  })

  it('cae a un mensaje generico sin respuesta', () => {
    expect(mensajeReimpresion(new Error('Network Error'))).toBe('Error al reimprimir')
  })
})
