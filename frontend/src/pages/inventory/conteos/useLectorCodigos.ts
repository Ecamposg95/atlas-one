import { useCallback, useEffect, useRef, useState } from 'react'

import { createDetector, normalizeCode } from '../../scanner/barcodeReader'
import { olvidarUltimoCodigo } from './sesion'

/**
 * Cámara + detector, portado de `pages/scanner/StoreScanner.tsx` con una
 * diferencia: `pausado`. En el conteo la misma pieza quieta frente a la
 * cámara NO debe contarse una vez por cuadro, así que tras cada lectura la
 * pantalla pausa la detección y el usuario reanuda con "Siguiente". Al
 * reanudar NO se olvida el último código: el "+1 igual" cubre las piezas
 * idénticas, y la cámara solo lo olvida cuando la etiqueta sale del cuadro
 * (2 cuadros seguidos sin código), para no recontar la pieza que sigue a la vista.
 */
export function useLectorCodigos({ onCodigo, pausado }: { onCodigo: (code: string) => void; pausado: boolean }) {
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const loopRef = useRef<number | null>(null)
  const lastCodeRef = useRef('')
  const sinCodigoRef = useRef(0)
  const pausadoRef = useRef(pausado)
  const cancelledRef = useRef(false)
  const startingRef = useRef(false)
  const onCodigoRef = useRef(onCodigo)
  const [camOn, setCamOn] = useState(false)
  const [camError, setCamError] = useState<string | null>(null)

  useEffect(() => { onCodigoRef.current = onCodigo }, [onCodigo])
  useEffect(() => {
    pausadoRef.current = pausado
  }, [pausado])

  const stop = useCallback(() => {
    if (loopRef.current) { window.clearInterval(loopRef.current); loopRef.current = null }
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
    lastCodeRef.current = ''
    sinCodigoRef.current = 0
    if (videoRef.current) videoRef.current.srcObject = null
    setCamOn(false)
  }, [])

  const start = useCallback(async () => {
    // Dos toques rápidos no deben abrir dos flujos: el primero quedaría sin liberar.
    if (startingRef.current || streamRef.current) return
    startingRef.current = true
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
          if (clean) {
            sinCodigoRef.current = 0
            if (clean !== lastCodeRef.current) {
              lastCodeRef.current = clean
              onCodigoRef.current(clean)
            }
          } else {
            sinCodigoRef.current += 1
            if (olvidarUltimoCodigo(sinCodigoRef.current)) lastCodeRef.current = ''
          }
        } catch {
          // cuadro sin código: lo normal entre lecturas
          sinCodigoRef.current += 1
          if (olvidarUltimoCodigo(sinCodigoRef.current)) lastCodeRef.current = ''
        }
      }, 400)
    } catch {
      setCamError('No se pudo abrir la cámara. Revisa el permiso del navegador para este sitio, o teclea el código a mano.')
      setCamOn(false)
    } finally {
      startingRef.current = false
    }
  }, [stop])

  useEffect(() => () => { cancelledRef.current = true; stop() }, [stop])

  return { videoRef, canvasRef, camOn, camError, start, stop }
}
