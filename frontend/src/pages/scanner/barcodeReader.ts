/**
 * Lectura de código de barras (y QR) con la cámara.
 *
 * Chrome en Android expone `BarcodeDetector` nativo: decodifica el sistema
 * operativo, no cuesta un solo byte de bundle y es más rápido.
 *
 * Safari (iPhone), Firefox y Chrome de escritorio en Windows/Linux no lo
 * traen. Ahí se carga `@zxing/browser` por `import()` dinámico, de modo que el
 * Android nunca descarga la librería. Antes de este respaldo, esos navegadores
 * mostraban "Este navegador no puede leer códigos de barras con la cámara" y
 * la cajera quedaba tecleando el código a mano.
 *
 * Este módulo NO abre la cámara ni pinta nada: solo decide con qué se
 * decodifica y normaliza lo que sale. Así la parte con lógica es testeable sin
 * navegador; lo que necesita hardware queda en el hook de la página.
 */

/**
 * Formatos que existen en el catálogo: 1,564 EAN-13, 121 UPC-A, 8 EAN-8.
 * `qr_code` entra por las boutiques, que etiquetan con QR que lleva el SKU.
 */
export const FORMATS = ['ean_13', 'ean_8', 'upc_a', 'upc_e', 'code_128', 'qr_code'] as const

export type ScannedCode = string

interface DetectedBarcode {
  rawValue?: string
}

interface NativeDetector {
  detect(source: CanvasImageSource): Promise<DetectedBarcode[]>
}

/** ¿El navegador decodifica por su cuenta? (Chrome/Android sí, Safari no) */
export function isNativeDetectorAvailable(): boolean {
  return typeof (globalThis as Record<string, unknown>).BarcodeDetector === 'function'
}

/**
 * Limpia lo que devuelve el lector antes de mandarlo al backend.
 *
 * Los ceros a la izquierda NO se tocan: un EAN-13 puede empezar con 0 y
 * recortarlo lo convierte en el código de otro producto.
 */
export function normalizeCode(raw: string | null | undefined): ScannedCode {
  if (!raw) return ''
  return raw.replace(/[\s-]/g, '').trim()
}

/**
 * Limpia lo que el admin TECLEA. Solo recorta los extremos.
 *
 * No es lo mismo que `normalizeCode`: ahí quitar guiones y espacios corrige el
 * ruido del lector, pero aquí los destruiría. 2,259 SKUs del catálogo llevan
 * letras y guiones (`m-1151`), y la búsqueda exacta del backend compara por
 * igualdad — `m1151` no empata con nada. Peor aún, el resultado vacío ofrecía
 * pegarle ese texto mutilado al producto como código de barras.
 */
export function normalizeTyped(raw: string | null | undefined): string {
  return (raw ?? '').trim()
}

/**
 * Devuelve un detector listo para usar, cargando ZXing solo si hace falta.
 *
 * La rama nativa es una API de navegador y no se prueba (verificaría el
 * mock). La rama ZXing sí tiene prueba: que resuelva un detector en vez de
 * lanzar, que es exactamente el fallo que se vio en producción.
 */
export async function createDetector(): Promise<NativeDetector> {
  if (isNativeDetectorAvailable()) {
    const Ctor = (globalThis as Record<string, unknown>).BarcodeDetector as new (
      opts: { formats: readonly string[] },
    ) => NativeDetector
    return new Ctor({ formats: FORMATS })
  }
  const { BrowserMultiFormatReader } = await import('@zxing/browser')
  // Sin hints ZXing prueba todos sus formatos (1D y QR): cubre FORMATS de sobra.
  const reader = new BrowserMultiFormatReader()
  return {
    async detect(source: CanvasImageSource) {
      try {
        const result = reader.decodeFromCanvas(source as HTMLCanvasElement)
        return result ? [{ rawValue: result.getText() }] : []
      } catch {
        // decodeFromCanvas lanza cuando no hay código en el cuadro. Es el caso
        // normal entre lecturas, no un error que valga la pena propagar.
        return []
      }
    },
  }
}
