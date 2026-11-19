import { Link } from 'react-router-dom'

export interface ComingSoonMeta {
  moduleKey: string
  title: string
  icon: string
  category: 'Beauty' | 'Gastro' | 'Services' | 'Retail' | 'Enterprise'
  description: string
  valueProps: string[]
  upgradePrompt?: string
}

/**
 * Stub page for modules whose backend exists only as a /health endpoint.
 * Used by the 6 Atlas One stubs (appointments, commissions, memberships,
 * recipes, ai, purchasing) until each module is built out.
 */
export function ComingSoon({ meta }: { meta: ComingSoonMeta }) {
  return (
    <div style={{
      maxWidth: 720,
      margin: '2rem auto',
      padding: '2rem',
      background: 'var(--p-surface)',
      border: '1px solid var(--p-border)',
      borderRadius: 8,
      color: 'var(--p-text)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
        <span style={{
          width: 48,
          height: 48,
          borderRadius: '50%',
          background: 'rgba(196, 69, 5,0.15)',
          color: 'var(--p-teal)',
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: 22,
        }}>
          <i className={`fa-solid ${meta.icon}`} />
        </span>
        <div>
          <h1 style={{ margin: 0, fontSize: '1.6rem', fontWeight: 700 }}>{meta.title}</h1>
          <span style={{
            display: 'inline-block',
            marginTop: 6,
            padding: '2px 8px',
            borderRadius: 4,
            fontSize: 10,
            fontWeight: 700,
            letterSpacing: '0.06em',
            background: 'rgba(245,158,11,0.18)',
            color: 'var(--p-warning)',
          }}>
            BETA · PRÓXIMAMENTE
          </span>
          <span style={{
            marginLeft: 8,
            fontSize: 11,
            color: 'var(--p-muted)',
            fontFamily: 'monospace',
          }}>
            Atlas One {meta.category}
          </span>
        </div>
      </div>

      <p style={{ fontSize: 14, color: 'var(--p-muted)', lineHeight: 1.5 }}>{meta.description}</p>

      {meta.valueProps.length > 0 && (
        <>
          <h3 style={{
            fontSize: 11,
            color: 'var(--p-muted)',
            textTransform: 'uppercase',
            letterSpacing: '0.08em',
            marginTop: 24,
            marginBottom: 8,
          }}>
            Qué traerá este módulo
          </h3>
          <ul style={{ fontSize: 13, lineHeight: 1.6, paddingLeft: 20, margin: 0 }}>
            {meta.valueProps.map((v, i) => <li key={i}>{v}</li>)}
          </ul>
        </>
      )}

      {meta.upgradePrompt && (
        <div style={{
          marginTop: 24,
          padding: 16,
          background: 'var(--p-bg)',
          border: '1px dashed var(--p-border)',
          borderRadius: 6,
          fontSize: 13,
          color: 'var(--p-text)',
        }}>
          <i className="fa-solid fa-lightbulb" style={{ color: 'var(--p-warning)', marginRight: 8 }} />
          {meta.upgradePrompt}
        </div>
      )}

      <div style={{
        marginTop: 24,
        display: 'flex',
        gap: 12,
        fontSize: 12,
        color: 'var(--p-muted)',
      }}>
        <Link to="/" style={{ color: 'var(--p-teal)', textDecoration: 'none' }}>
          <i className="fa-solid fa-arrow-left" style={{ marginRight: 4 }} />
          Volver al inicio
        </Link>
        <span style={{ fontFamily: 'monospace' }}>
          backend: <code>/api/{meta.moduleKey}/health</code>
        </span>
      </div>
    </div>
  )
}
