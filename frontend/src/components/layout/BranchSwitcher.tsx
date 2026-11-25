import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import client from '../../api/client'
import { useAuthStore } from '../../store/authStore'
import type { BranchType } from '../../types/auth'
import { useBranchCountStore, esTiendaUnica } from '../../store/branchCountStore'

interface Branch {
  id: number
  name: string
  branch_type: string
}

/**
 * `enMenu`: variante para el menú lateral (botón a todo el ancho y lista
 * anclada a la izquierda, que se abre hacia el contenido).
 */
export function BranchSwitcher({ enMenu = false }: { enMenu?: boolean } = {}) {
  const [open, setOpen] = useState(false)
  const [branches, setBranches] = useState<Branch[]>([])
  const [loading, setLoading] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const navigate = useNavigate()
  const setBranch = useAuthStore(s => s.setBranch)
  const user = useAuthStore(s => s.user)
  const activa = useAuthStore(s => s.branch)
  const unaSola = esTiendaUnica(useBranchCountStore((s) => s.count))

  // Close on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const loadBranches = async () => {
    if (branches.length > 0) return
    setLoading(true)
    try {
      const { data } = await client.get<Branch[]>('/branches/')
      setBranches(Array.isArray(data) ? data : [])
    } catch {
      setBranches([])
    } finally {
      setLoading(false)
    }
  }

  const toggle = () => {
    if (!open) loadBranches()
    setOpen(o => !o)
  }

  const switchBranch = async (branchId: number, branchType: string, branchName: string) => {
    try {
      await client.post(`/auth/context/switch?branch_id=${branchId}`)
    } catch {
      // Non-fatal — redirect anyway
    }
    setBranch({
      id: branchId,
      name: branchName,
      branch_type: branchType as BranchType,
      is_headquarters: branchType === 'HQ',
    })
    setOpen(false)
    const isAdmin = user?.role === 'ADMINISTRADOR' || user?.role === 'DUEÑO'
    if (branchType === 'WAREHOUSE') navigate('/inventory')
    else if (isAdmin) navigate('/hq/operations')
    else navigate('/atlas-pos')
  }

  // Volver a ver todo: sin esto, quien elegía una sucursal ya no podía regresar.
  const verTodas = async () => {
    try {
      await client.post('/auth/context/switch')
    } catch {
      // No es fatal: la vista se actualiza igual
    }
    setBranch(null)
    setOpen(false)
    navigate('/hq/operations')
  }

  const palomita = <i className="fa-solid fa-check" style={{ marginLeft: 'auto', fontSize: '0.7rem', color: 'var(--dax-accent-text)' }} aria-hidden="true" />
  const estiloOpcion = {
    display: 'flex', alignItems: 'center', gap: '0.75rem', width: '100%',
    padding: '0.625rem 0.75rem', borderRadius: '10px', background: 'transparent',
    border: 'none', cursor: 'pointer', textAlign: 'left', transition: 'background 0.15s',
  } as const

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <button
        onClick={toggle}
        className="max-md:min-h-[44px]"
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: enMenu ? 'center' : undefined,
          width: enMenu ? '100%' : undefined,
          gap: '0.5rem',
          padding: '0.4rem 0.875rem',
          background: enMenu ? 'rgba(255,255,255,0.04)' : 'var(--dax-card)',
          border: `1px solid ${enMenu ? 'rgba(255,255,255,0.08)' : 'var(--dax-border)'}`,
          borderRadius: '999px',
          color: enMenu ? 'rgba(255,255,255,0.8)' : 'var(--dax-text)',
          fontSize: enMenu ? '12px' : '0.7rem',
          fontWeight: enMenu ? 400 : 600,
          textTransform: enMenu ? undefined : 'uppercase',
          letterSpacing: enMenu ? undefined : '0.08em',
          cursor: 'pointer',
          transition: 'all 0.2s',
        }}
        onMouseEnter={e => {
          ;(e.currentTarget as HTMLElement).style.borderColor = 'var(--dax-accent)'
          ;(e.currentTarget as HTMLElement).style.color = 'var(--dax-accent-text)'
        }}
        onMouseLeave={e => {
          ;(e.currentTarget as HTMLElement).style.borderColor = enMenu ? 'rgba(255,255,255,0.08)' : 'var(--dax-border)'
          ;(e.currentTarget as HTMLElement).style.color = enMenu ? 'rgba(255,255,255,0.8)' : 'var(--dax-text)'
        }}
      >
        <i className="fa-solid fa-shuffle" style={{ fontSize: '0.65rem', color: 'var(--dax-accent-text)' }} />
        {enMenu ? 'Cambiar sucursal' : 'Sucursal'}
        <i className="fa-solid fa-chevron-down" style={{ fontSize: '0.55rem', color: 'var(--dax-text-faint)' }} />
      </button>

      {open && (
        <div
          style={{
            position: 'absolute',
            ...(enMenu ? { left: 0 } : { right: 0 }),
            top: 'calc(100% + 8px)',
            width: '260px',
            maxWidth: 'calc(100vw - 32px)',
            background: 'var(--dax-card-solid)',
            border: '1px solid var(--dax-border)',
            borderRadius: '14px',
            boxShadow: '0 16px 48px rgba(0,0,0,0.5)',
            backdropFilter: 'blur(16px)',
            zIndex: 100,
            overflow: 'hidden',
          }}
        >
          <div style={{ padding: '0.75rem 1rem', borderBottom: '1px solid var(--dax-border-dim)' }}>
            <p style={{ fontSize: '0.6rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.12em', color: 'var(--dax-text-faint)', margin: 0 }}>
              Sucursales
            </p>
          </div>
          <div style={{ maxHeight: '240px', overflowY: 'auto', padding: '0.5rem' }}>
            {loading ? (
              <div style={{ padding: '1rem', textAlign: 'center', color: 'var(--dax-text-faint)', fontSize: '0.75rem' }}>
                Cargando...
              </div>
            ) : branches.length === 0 ? (
              <div style={{ padding: '1rem', textAlign: 'center', color: 'rgba(251,113,133,0.7)', fontSize: '0.75rem' }}>
                Sin sucursales
              </div>
            ) : (<>
              <button
                onClick={verTodas}
                aria-current={activa ? undefined : 'true'}
                style={estiloOpcion}
                onMouseEnter={e => ((e.currentTarget as HTMLElement).style.background = 'var(--dax-accent-soft)')}
                onMouseLeave={e => ((e.currentTarget as HTMLElement).style.background = 'transparent')}
              >
                <div style={{
                  width: '32px', height: '32px', borderRadius: '8px',
                  background: 'var(--dax-elevated)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  flexShrink: 0,
                }}>
                  <i className="fa-solid fa-building" style={{ fontSize: '0.75rem', color: 'var(--dax-text-muted)' }} />
                </div>
                <p style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--dax-text)', margin: 0 }}>
                  {unaSola ? 'Toda la tienda' : 'Todas las sucursales'}
                </p>
                {!activa && palomita}
              </button>
              {branches.map(b => (
              <button
                key={b.id}
                onClick={() => switchBranch(b.id, b.branch_type, b.name)}
                aria-current={activa?.id === b.id ? 'true' : undefined}
                style={estiloOpcion}
                onMouseEnter={e => ((e.currentTarget as HTMLElement).style.background = 'var(--dax-accent-soft)')}
                onMouseLeave={e => ((e.currentTarget as HTMLElement).style.background = 'transparent')}
              >
                <div style={{
                  width: '32px', height: '32px', borderRadius: '8px',
                  background: 'var(--dax-elevated)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  flexShrink: 0,
                }}>
                  <i className="fa-solid fa-store" style={{ fontSize: '0.75rem', color: 'var(--dax-text-muted)' }} />
                </div>
                <div style={{ overflow: 'hidden' }}>
                  <p style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--dax-text)', margin: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {b.name}
                  </p>
                  <p style={{ fontSize: '0.6rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--dax-text-faint)', margin: 0 }}>
                    {b.branch_type}
                  </p>
                </div>
                {activa?.id === b.id && palomita}
              </button>
              ))}
            </>)}
          </div>
        </div>
      )}
    </div>
  )
}
