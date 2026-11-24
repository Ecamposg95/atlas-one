import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useImpersonationStore } from '../../store/impersonationStore'
import { platformApi } from '../../api/platform'
import { toast } from '../../store/toastStore'

// TODO(backend): Impersonation today is AUDIT-ONLY.
// app/routers/platform.py:810-847 logs a PlatformAuditLog entry with
// action="IMPERSONATE_START" but does NOT issue a new JWT token or
// swap X-Organization-ID. The axios client (api/client.ts) continues
// to send the caller's original token, so all requests identify the
// acting user as their own superadmin self.
// When backend adds a real impersonator_id claim + token swap, update
// the banner copy here from "AUDIT MODE" to "IMPERSONATING".

export function ImpersonationBanner() {
  const { orgId, orgName, exit, hydrate } = useImpersonationStore()
  const [exiting, setExiting] = useState(false)
  const navigate = useNavigate()

  useEffect(() => { hydrate() }, [hydrate])

  if (orgId == null) return null

  const handleExit = async () => {
    setExiting(true)
    try {
      await platformApi.exitImpersonate()
      exit()
      toast.success('Impersonation finalizada')
      navigate(`/platform/organizations/${orgId}`)
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'No se pudo salir del modo impersonación')
    } finally {
      setExiting(false)
    }
  }

  return (
    <div
      role="status"
      aria-live="polite"
      style={{
        background: 'linear-gradient(90deg, rgba(148, 58, 13,0.95) 0%, rgba(184, 75, 20,0.95) 100%)',
        borderBottom: '1px solid rgba(212, 101, 45,0.5)',
        color: 'white',
        padding: '0.5rem 1rem',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: '1rem',
        fontSize: '0.75rem',
        fontWeight: 600,
        letterSpacing: '0.05em',
        fontFamily: 'var(--font-sans)',
      }}
    >
      <i className="fa-solid fa-eye" />
      <span>
        AUDIT MODE · OBSERVING <span style={{ textTransform: 'uppercase' }}>{orgName}</span> (#{orgId})
      </span>
      <button
        onClick={handleExit}
        disabled={exiting}
        aria-label="Salir del modo auditoría"
        style={{
          background: 'rgba(0,0,0,0.25)',
          border: '1px solid rgba(255,255,255,0.3)',
          color: 'white',
          padding: '0.25rem 0.75rem',
          borderRadius: '6px',
          fontSize: '0.7rem',
          fontWeight: 600,
          letterSpacing: '0.1em',
          textTransform: 'uppercase',
          cursor: exiting ? 'not-allowed' : 'pointer',
          opacity: exiting ? 0.6 : 1,
        }}
      >
        <i className="fa-solid fa-arrow-right-from-bracket mr-1" />
        {exiting ? 'Saliendo…' : 'Exit Audit Mode'}
      </button>
    </div>
  )
}
