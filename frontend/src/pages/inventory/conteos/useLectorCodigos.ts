import { useCallback, useEffect, useRef, useState } from 'react'

import { createDetector, normalizeCode } from '../../scanner/barcodeReader'

/**
 * Cámara + detector, portado de `pages/scanner/StoreScanner.tsx` con una
 * diferencia: `pausado`. En el conteo la misma pieza quieta frente a la
 * cámara NO debe contarse una vez por cuadro, así que tras cada lectura la
 * pantalla pausa la detección y el usuario reanuda con "Siguiente". Al
 * reanudar se olvida el último código para que la pieza idéntica siguiente
 * sí cuente.
 */
export function useLectorCodigos({ onCodigo, pausado }: { onCodigo: (code: string) => void; pausado: boolean }) {
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const loopRef = useRef<number | null>(null)
  const lastCodeRef = useRef('')
  const pausadoRef = useRef(pausado)
  const cancelledRef = useRef(false)
  const onCodigoRef = useRef(onCodigo)
  const [camOn, setCamOn] = useState(false)
  const [camError, setCamError] = useState<string | null>(null)

  useEffect(() => { onCodigoRef.current = onCodigo }, [onCodigo])
  useEffect(() => {
    pausadoRef.current = pausado
    if (!pausado) lastCodeRef.current = ''
  }, [pausado])

  const stop = useCallback(() => {
    if (loopRef.current) { window.clearInterval(loopRef.current); loopRef.current = null }
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
    lastCodeRef.current = ''
    if (videoRef.current) videoRef.current.srcObject = null
    setCamOn(false)
  }, [])

  const start = useCallback(async () => {
    setCamError(null)
    cancelledRef.current = false
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' } } })
      if (cancelledRef.current) { stream.getTracks().forEach((t) => t.stop()); return }
      streamRef.current = stream
      if (videoRef.current) { videoRef.current.srcObject = stream; await videoRef.current.play() }
      setCamOn(true)
      let detector
      try {
        detector = await createDetector()
      } catch (err) {
        stop()
        setCamError(err instanceof Error ? err.message : 'Este navegador no puede leer códigos de barras con la cámara.')
        return
      }
      if (cancelledRef.current) { stop(); return }
      loopRef.current = window.setInterval(async () => {
        if (pausadoRef.current) return
        const video = videoRef.current
        const canvas = canvasRef.current
        if (!video || !canvas || video.readyState < 2) return
        canvas.width = video.videoWidth
        canvas.height = video.videoHeight
        canvas.getContext('2d')?.drawImage(video, 0, 0)
        try {
          const hits = await detector.detect(canvas)
          const clean = normalizeCode(hits?.[0]?.rawValue)
          if (clean && clean !== lastCodeRef.current) {
            lastCodeRef.current = clean
            onCodigoRef.current(clean)
          }
        } catch { /* cuadro sin código: lo normal entre lecturas */ }
      }, 400)
    } catch {
      setCamError('No se pudo abrir la cámara. Revisa el permiso del navegador para este sitio, o teclea el código a mano.')
      setCamOn(false)
    }
  }, [stop])

  useEffect(() => () => { cancelledRef.current = true; stop() }, [stop])

  return { videoRef, canvasRef, camOn, camError, start, stop }
}
