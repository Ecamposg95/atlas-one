import { useCallback, useEffect, useState } from 'react'
import { announcementsApi, type AnnouncementSeverity, type TenantAnnouncement } from '../../api/platform'

const ORDEN: Record<AnnouncementSeverity, number> = {
  critical: 0,
  warning: 1,
  info: 2,
  success: 3,
}

const COLOR: Record<AnnouncementSeverity, { fondo: string; borde: string; icono: string }> = {
  critical: { fondo: 'linear-gradient(90deg, rgba(190,18,60,0.95) 0%, rgba(225,29,72,0.95) 100%)', borde: 'rgba(251,113,133,0.5)', icono: 'fa-circle-exclamation' },
  warning:  { fondo: 'linear-gradient(90deg, rgba(180,83,9,0.95) 0%, rgba(217,119,6,0.95) 100%)',  borde: 'rgba(251,191,36,0.5)', icono: 'fa-triangle-exclamation' },
  info:     { fondo: 'linear-gradient(90deg, rgba(175, 78, 30,0.95) 0%, rgba(235, 103, 37,0.95) 100%)', borde: 'rgba(250, 147, 96,0.5)', icono: 'fa-circle-info' },
  success:  { fondo: 'linear-gradient(90deg, rgba(6,95,70,0.95) 0%, rgba(16,185,129,0.95) 100%)',  borde: 'rgba(52,211,153,0.5)', icono: 'fa-circle-check' },
}

const CLAVE = 'atlas_ann_dismissed'

function hoy(): string {
  return new Date().toISOString().slice(0, 10)
}

function leerDescartados(): Record<string, string> {
  try {
    const crudo = localStorage.getItem(CLAVE)
    return crudo ? JSON.parse(crudo) : {}
  } catch {
    return {}
  }
}

function descartar(id: number) {
  try {
    localStorage.setItem(CLAVE, JSON.stringify({ ...leerDescartados(), [String(id)]: hoy() }))
  } catch {
    /* modo privado o almacenamiento lleno: el aviso simplemente reaparece */
  }
}

export function AnnouncementBanner() {
  const [avisos, setAvisos] = useState<TenantAnnouncement[]>([])
  const [indice, setIndice] = useState(0)
  const [version, setVersion] = useState(0)

  const cargar = useCallback(async () => {
    try {
      const datos = await announcementsApi.activeForTenant()
      const descartados = leerDescartados()
      const visibles = datos
        .filter((a) => descartados[String(a.id)] !== hoy())
        .sort((a, b) => (ORDEN[a.severity] ?? 9) - (ORDEN[b.severity] ?? 9))
      setAvisos(visibles)
      setIndice(0)
    } catch {
      // Un aviso caido no debe estorbar la venta: se calla y no pinta nada.
      setAvisos([])
    }
  }, [version])

  useEffect(() => {
    cargar()
    const id = setInterval(cargar, 15 * 60 * 1000)
    return () => clearInterval(id)
  }, [cargar])

  if (avisos.length === 0) return null

  const aviso = avisos[Math.min(indice, avisos.length - 1)]
  const tono = COLOR[aviso.severity] ?? COLOR.info

  const cerrar = () => {
    descartar(aviso.id)
    setVersion((v) => v + 1)
  }

  return (
    <div
      role="status"
      aria-live="polite"
      style={{
        background: tono.fondo,
        borderBottom: `1px solid ${tono.borde}`,
        color: 'white',
        padding: '0.5rem 1rem',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: '0.75rem',
        fontSize: '0.8125rem',
        fontFamily: "'IBM Plex Sans', sans-serif",
      }}
    >
      <i className={`fa-solid ${tono.icono}`} aria-hidden="true" />
      <span style={{ fontWeight: 700 }}>{aviso.title}</span>
      <span style={{ opacity: 0.9 }}>{aviso.body_md}</span>
      {avisos.length > 1 && (
        <button
          type="button"
          onClick={() => setIndice((i) => (i + 1) % avisos.length)}
          aria-label="Ver el siguiente aviso"
          style={{ background: 'transparent', border: 'none', color: 'inherit', cursor: 'pointer', opacity: 0.85 }}
        >
          <i className="fa-solid fa-chevron-right" aria-hidden="true" />
          <span style={{ marginLeft: '0.25rem' }}>{indice + 1}/{avisos.length}</span>
        </button>
      )}
      <button
        type="button"
        onClick={cerrar}
        aria-label="Cerrar el aviso por hoy"
        style={{ background: 'transparent', border: 'none', color: 'inherit', cursor: 'pointer', opacity: 0.85, marginLeft: '0.25rem' }}
      >
        <i className="fa-solid fa-xmark" aria-hidden="true" />
      </button>
    </div>
  )
}
