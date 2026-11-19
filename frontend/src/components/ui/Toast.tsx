import { useEffect, useState } from 'react'
import { useToastStore, type ToastItem } from '../../store/toastStore'

const STYLES: Record<string, { bg: string; border: string; icon: string; color: string }> = {
  success: { bg: 'rgba(5,46,22,0.95)',  border: 'rgba(52,211,153,0.3)',  icon: 'fa-circle-check',         color: '#34d399' },
  error:   { bg: 'rgba(69,10,10,0.95)', border: 'rgba(251,113,133,0.3)', icon: 'fa-circle-xmark',         color: '#fb7185' },
  warning: { bg: 'rgba(69,46,0,0.95)',  border: 'rgba(251,191,36,0.3)',  icon: 'fa-triangle-exclamation', color: '#fbbf24' },
  info:    { bg: 'rgba(14, 13, 12,0.95)', border: 'rgba(255, 106, 31,0.3)',  icon: 'fa-circle-info',          color: '#FFC08A' },
}

function ToastItemView({ toast }: { toast: ToastItem }) {
  const dismiss = useToastStore(s => s.dismiss)
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    const t = setTimeout(() => setVisible(true), 10)
    return () => clearTimeout(t)
  }, [])

  const s = STYLES[toast.type]
  return (
    <div
      // Los errores se anuncian de inmediato al lector de pantalla;
      // el resto entra por el aria-live del contenedor.
      role={toast.type === 'error' ? 'alert' : undefined}
      onClick={() => dismiss(toast.id)}
      style={{
        background: s.bg,
        border: `1px solid ${s.border}`,
        borderRadius: '12px',
        padding: '0.75rem 1rem',
        display: 'flex',
        alignItems: 'flex-start',
        gap: '0.75rem',
        maxWidth: '22rem',
        cursor: 'pointer',
        backdropFilter: 'blur(16px)',
        boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
        transform: visible ? 'translateX(0)' : 'translateX(24px)',
        opacity: visible ? 1 : 0,
        transition: 'all 0.3s cubic-bezier(0.19,1,0.22,1)',
        fontFamily: 'var(--font-sans)',
      }}
    >
      <i className={`fa-solid ${s.icon} mt-0.5 flex-shrink-0`} style={{ color: s.color, fontSize: '0.875rem' }} />
      <span style={{ color: '#f1f5f9', fontSize: '0.8rem', fontWeight: 500, lineHeight: 1.4 }}>
        {toast.message}
      </span>
    </div>
  )
}

export function Toaster() {
  const toasts = useToastStore(s => s.toasts)
  return (
    <div role="status" aria-live="polite" style={{
      position: 'fixed', bottom: '1.5rem', right: '1.5rem',
      zIndex: 9999, display: 'flex', flexDirection: 'column', gap: '0.5rem',
      alignItems: 'flex-end',
    }}>
      {toasts.map(t => <ToastItemView key={t.id} toast={t} />)}
    </div>
  )
}
