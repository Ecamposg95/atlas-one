/**
 * Lectura de código de barras con la cámara del teléfono.
 *
 * Chrome en Android expone `BarcodeDetector` nativo: decodifica el sistema
 * operativo, no cuesta un solo byte de bundle y es más rápido.
 *
 * Safari en iPhone no lo trae. Rmazh (referencia de este puerto) resuelve eso
 * cargando `@zxing/browser` por `import()` dinámico. Aquí NO se agregó esa
 * dependencia: el worktree de este cambio comparte `node_modules` por symlink
 * con el repo principal y no se permite instalar paquetes desde aquí (ver
 * implementer-contract). Sin el detector nativo, `createDetector` falla con un
 * mensaje claro y la pantalla cae a la captura manual (SKU o código
 * tecleado), que siempre está visible. Pendiente: agregar `@zxing/browser` en
 * una sesión con `npm install` habilitado para recuperar el escaneo por
 * cámara en iPhone.
 *
 * Este módulo NO abre la cámara ni pinta nada: solo decide con qué se
 * decodifica y normaliza lo que sale. Así la parte con lógica es testeable sin
 * navegador; lo que necesita hardware queda en el hook de la página.
 */

/** Formatos que existen en el catálogo: 1,564 EAN-13, 121 UPC-A, 8 EAN-8. */
export const FORMATS = ['ean_13', 'ean_8', 'upc_a', 'upc_e', 'code_128'] as const

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
 * Devuelve un detector listo para usar. No tiene test unitario a propósito:
 * la rama nativa es una API de navegador, y un test aquí verificaría el mock,
 * no el comportamiento.
 *
 * Lanza cuando el navegador no trae `BarcodeDetector` (Safari/iPhone) — ver la
 * nota de dependencia al inicio del archivo. El caller (la página) lo atrapa
 * y muestra la captura manual en vez de una cámara que nunca decodifica nada.
 */
export async function createDetector(): Promise<NativeDetector> {
  if (isNativeDetectorAvailable()) {
    const Ctor = (globalThis as Record<string, unknown>).BarcodeDetector as new (
      opts: { formats: readonly string[] },
    ) => NativeDetector
    return new Ctor({ formats: FORMATS })
  }
  throw new Error(
    'Este navegador no puede leer códigos de barras con la cámara. Teclea el código o SKU.',
  )
}
