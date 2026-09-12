interface Props {
  breadcrumb?: React.ReactNode
  title: string
  actions?: React.ReactNode
  kpis?: React.ReactNode
  children: React.ReactNode
}

export function PlatformPageShell({
  breadcrumb = 'Platform / Superadmin',
  title,
  actions,
  kpis,
  children,
}: Props) {
  return (
    <div className="pv2-page">
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'flex-end',
        marginBottom: '1.5rem',
        flexWrap: 'wrap',
        gap: 16,
      }}>
        <div>
          <p style={{
            fontSize: 12,
            color: 'var(--p-muted)',
            letterSpacing: '0.02em',
            margin: 0,
            marginBottom: 6,
            fontFamily: 'var(--font-sans)',
          }}>
            {breadcrumb}
          </p>
          <h1 style={{
            fontFamily: 'var(--font-display)',
            fontSize: 30,
            letterSpacing: '-0.025em',
            fontWeight: 600,
            color: 'var(--p-text)',
            margin: 0,
            lineHeight: 1.15,
          }}>
            {title}
          </h1>
        </div>
        {actions && <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>{actions}</div>}
      </div>
      {kpis && (
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
          gap: 14,
          marginBottom: '1.5rem',
        }}>
          {kpis}
        </div>
      )}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '1rem' }}>
        {children}
      </div>
    </div>
  )
}
