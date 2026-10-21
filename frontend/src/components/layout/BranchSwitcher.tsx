import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import client from '../../api/client'
import { useAuthStore } from '../../store/authStore'
import type { BranchType } from '../../types/auth'

interface Branch {
  id: number
  name: string
  branch_type: string
}

export function BranchSwitcher() {
  const [open, setOpen] = useState(false)
  const [branches, setBranches] = useState<Branch[]>([])
  const [loading, setLoading] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const navigate = useNavigate()
  const setBranch = useAuthStore(s => s.setBranch)
  const user = useAuthStore(s => s.user)

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

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <button
        onClick={toggle}
        className="max-md:min-h-[44px]"
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '0.5rem',
          padding: '0.4rem 0.875rem',
          background: 'rgba(30,41,59,0.8)',
          border: '1px solid rgba(51,65,85,0.7)',
          borderRadius: '10px',
          color: '#cbd5e1',
          fontSize: '0.7rem',
          fontWeight: 700,
          textTransform: 'uppercase',
          letterSpacing: '0.08em',
          cursor: 'pointer',
          transition: 'all 0.2s',
        }}
        onMouseEnter={e => {
          ;(e.currentTarget as HTMLElement).style.borderColor = 'rgba(52,211,153,0.4)'
          ;(e.currentTarget as HTMLElement).style.color = '#34d399'
        }}
        onMouseLeave={e => {
          ;(e.currentTarget as HTMLElement).style.borderColor = 'rgba(51,65,85,0.7)'
          ;(e.currentTarget as HTMLElement).style.color = '#cbd5e1'
        }}
      >
        <i className="fa-solid fa-shuffle" style={{ fontSize: '0.65rem', color: '#34d399' }} />
        Sucursal
        <i className="fa-solid fa-chevron-down" style={{ fontSize: '0.55rem', color: 'rgba(148,163,184,0.5)' }} />
      </button>

      {open && (
        <div
          style={{
            position: 'absolute',
            right: 0,
            top: 'calc(100% + 8px)',
            width: '260px',
            background: 'rgba(15,23,42,0.98)',
            border: '1px solid rgba(51,65,85,0.7)',
            borderRadius: '14px',
            boxShadow: '0 16px 48px rgba(0,0,0,0.5)',
            backdropFilter: 'blur(16px)',
            zIndex: 100,
            overflow: 'hidden',
          }}
        >
          <div style={{ padding: '0.75rem 1rem', borderBottom: '1px solid rgba(51,65,85,0.4)' }}>
            <p style={{ fontSize: '0.6rem', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.12em', color: 'rgba(100,116,139,0.8)', margin: 0 }}>
              Nodos disponibles
            </p>
          </div>
          <div style={{ maxHeight: '240px', overflowY: 'auto', padding: '0.5rem' }}>
            {loading ? (
              <div style={{ padding: '1rem', textAlign: 'center', color: 'rgba(148,163,184,0.5)', fontSize: '0.75rem' }}>
                Cargando...
              </div>
            ) : branches.length === 0 ? (
              <div style={{ padding: '1rem', textAlign: 'center', color: 'rgba(251,113,133,0.7)', fontSize: '0.75rem' }}>
                Sin sucursales
              </div>
            ) : branches.map(b => (
              <button
                key={b.id}
                onClick={() => switchBranch(b.id, b.branch_type, b.name)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.75rem',
                  width: '100%',
                  padding: '0.625rem 0.75rem',
                  borderRadius: '10px',
                  background: 'transparent',
                  border: 'none',
                  cursor: 'pointer',
                  textAlign: 'left',
                  transition: 'background 0.15s',
                }}
                onMouseEnter={e => ((e.currentTarget as HTMLElement).style.background = 'rgba(52,211,153,0.07)')}
                onMouseLeave={e => ((e.currentTarget as HTMLElement).style.background = 'transparent')}
              >
                <div style={{
                  width: '32px', height: '32px', borderRadius: '8px',
                  background: 'rgba(30,41,59,0.8)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  flexShrink: 0,
                }}>
                  <i className="fa-solid fa-store" style={{ fontSize: '0.75rem', color: 'rgba(148,163,184,0.6)' }} />
                </div>
                <div style={{ overflow: 'hidden' }}>
                  <p style={{ fontSize: '0.8rem', fontWeight: 600, color: '#e2e8f0', margin: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {b.name}
                  </p>
                  <p style={{ fontSize: '0.6rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', color: 'rgba(100,116,139,0.8)', margin: 0 }}>
                    {b.branch_type}
                  </p>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
