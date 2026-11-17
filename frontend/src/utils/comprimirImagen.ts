// Reduce una foto del teléfono antes de subirla. El servidor acepta hasta 2 MB
// y JPEG/PNG/WEBP; la cámara entrega 3-12 MB (y HEIC en iPhone). Redibujar en un
// canvas a lo más LADO_MAX px y exportar a JPEG deja la foto en ~300-600 KB,
// suficiente para la tienda web y el POS, y sube rápido con datos móviles.

export const LADO_MAX = 1600
export const LIMITE_BYTES = 2 * 1024 * 1024
const CALIDADES = [0.85, 0.75, 0.65, 0.5]

/** Medidas finales manteniendo la proporción; nunca agranda. */
export function medidasReducidas(ancho: number, alto: number, ladoMax = LADO_MAX): { ancho: number; alto: number } {
  const mayor = Math.max(ancho, alto)
  if (mayor <= ladoMax || mayor <= 0) return { ancho, alto }
  const f = ladoMax / mayor
  return { ancho: Math.round(ancho * f), alto: Math.round(alto * f) }
}

/** Ya sirve tal cual: tipo aceptado, ligera y no más grande de lo necesario. */
export function sirveSinTocar(tipo: string, bytes: number): boolean {
  return ['image/jpeg', 'image/webp'].includes(tipo) && bytes <= 600 * 1024
}

async function decodificar(archivo: File): Promise<{ fuente: CanvasImageSource; ancho: number; alto: number; cerrar: () => void }> {
  // createImageBitmap respeta la orientación EXIF (la foto no sale de lado).
  if (typeof createImageBitmap === 'function') {
    try {
      const bmp = await createImageBitmap(archivo, { imageOrientation: 'from-image' } as ImageBitmapOptions)
      return { fuente: bmp, ancho: bmp.width, alto: bmp.height, cerrar: () => bmp.close() }
    } catch { /* cae al <img> */ }
  }
  const url = URL.createObjectURL(archivo)
  try {
    const img = new Image()
    img.src = url
    await img.decode()
    return { fuente: img, ancho: img.naturalWidth, alto: img.naturalHeight, cerrar: () => URL.revokeObjectURL(url) }
  } catch (e) {
    URL.revokeObjectURL(url)
    throw e
  }
}

function aBlob(canvas: HTMLCanvasElement, calidad: number): Promise<Blob | null> {
  return new Promise((ok) => canvas.toBlob(ok, 'image/jpeg', calidad))
}

/**
 * Devuelve un JPEG listo para subir. Si el navegador no puede leer la foto
 * (formato raro), regresa el archivo original y que el servidor decida.
 */
export async function comprimirImagen(archivo: File): Promise<File> {
  if (sirveSinTocar(archivo.type, archivo.size)) return archivo
  let dec
  try { dec = await decodificar(archivo) } catch { return archivo }
  try {
    const { ancho, alto } = medidasReducidas(dec.ancho, dec.alto)
    const canvas = document.createElement('canvas')
    canvas.width = ancho
    canvas.height = alto
    const ctx = canvas.getContext('2d')
    if (!ctx) return archivo
    ctx.fillStyle = '#fff' // PNG con transparencia → fondo blanco en JPEG
    ctx.fillRect(0, 0, ancho, alto)
    ctx.drawImage(dec.fuente, 0, 0, ancho, alto)
    for (const q of CALIDADES) {
      const blob = await aBlob(canvas, q)
      if (blob && blob.size <= LIMITE_BYTES) {
        const nombre = (archivo.name || 'foto').replace(/\.[^.]+$/, '') + '.jpg'
        return new File([blob], nombre, { type: 'image/jpeg' })
      }
    }
    return archivo
  } finally {
    dec.cerrar()
  }
}
