import type { ReactNode } from 'react'

export interface MoneyColumn<T> {
  key: string
  label: string
  align?: 'left' | 'right'
  render: (row: T) => ReactNode
}

interface Props<T> {
  rows: T[]
  columns: MoneyColumn<T>[]
  rowKey: (row: T) => string | number
  onRowClick?: (row: T) => void
  emptyMessage?: string
  /** Total de filas en el backend (sin paginar). Sin ella no hay control de página. */
  total?: number
  page?: number
  onPageChange?: (p: number) => void
  /** Debe coincidir con el `limit` mandado al backend. */
  pageSize?: number
}

const DEFAULT_PAGE_SIZE = 50

function MoneyPagination({
  page, total, pageSize, onPageChange,
}: {
  page: number
  total: number
  pageSize: number
  onPageChange: (p: number) => void
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize))
  return (
    <div style={{
      padding: '12px 14px',
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center',
      borderTop: '1px solid var(--p-border)',
    }}>
      <button
        type="button"
        onClick={() => onPageChange(Math.max(0, page - 1))}
        disabled={page === 0}
        style={{
          background: 'var(--p-surface)',
          border: '1px solid var(--p-border)',
          color: 'var(--p-text)',
          padding: '6px 12px',
          borderRadius: 8,
          fontSize: 12,
          cursor: page === 0 ? 'not-allowed' : 'pointer',
          opacity: page === 0 ? 0.5 : 1,
        }}
      >
        <i className="fa-solid fa-chevron-left" style={{ fontSize: 10 }} /> Anterior
      </button>
      <span style={{
        color: 'var(--p-muted)',
        fontSize: 11,
        fontFamily: 'var(--font-mono)',
        fontVariantNumeric: 'tabular-nums',
      }}>
        Pág. {page + 1} / {pages} · {total} registros
      </span>
      <button
        type="button"
        onClick={() => onPageChange(Math.min(pages - 1, page + 1))}
        disabled={page >= pages - 1}
        style={{
          background: 'var(--p-surface)',
          border: '1px solid var(--p-border)',
          color: 'var(--p-text)',
          padding: '6px 12px',
          borderRadius: 8,
          fontSize: 12,
          cursor: page >= pages - 1 ? 'not-allowed' : 'pointer',
          opacity: page >= pages - 1 ? 0.5 : 1,
        }}
      >
        Siguiente <i className="fa-solid fa-chevron-right" style={{ fontSize: 10 }} />
      </button>
    </div>
  )
}

const headStyle: React.CSSProperties = {
  padding: '10px 14px', color: 'var(--p-hint)', fontSize: 10,
  textTransform: 'uppercase', letterSpacing: '0.12em', fontWeight: 500,
  borderBottom: '1px solid var(--p-border)', background: 'transparent',
}

const cellStyle: React.CSSProperties = {
  padding: '12px 14px', borderBottom: '1px solid var(--p-border-2)',
  fontSize: 13, color: 'var(--p-text)',
}

export function MoneyTable<T>({
  rows, columns, rowKey, onRowClick, emptyMessage = 'Sin datos en el periodo',
  total, page = 0, onPageChange, pageSize = DEFAULT_PAGE_SIZE,
}: Props<T>) {
  if (rows.length === 0) {
    // Una página vacía MÁS ALLÁ de la primera no es "no hay datos": es que el
    // periodo o el filtro cambiaron bajo los pies del usuario. Sin salida,
    // quedaba atrapado en una pantalla vacía sin control de página.
    return (
      <div style={{ padding: 32, textAlign: 'center', color: 'var(--p-muted)', fontSize: 13 }}>
        {page > 0 ? 'No hay más registros en esta página.' : emptyMessage}
        {page > 0 && onPageChange && (
          <div style={{ marginTop: 12 }}>
            <button
              type="button"
              onClick={() => onPageChange(0)}
              style={{
                background: 'var(--p-surface)', border: '1px solid var(--p-border)',
                color: 'var(--p-text)', padding: '6px 12px', borderRadius: 8,
                fontSize: 12, cursor: 'pointer',
              }}
            >
              Volver a la primera página
            </button>
          </div>
        )}
      </div>
    )
  }
  const showPagination = total !== undefined && onPageChange && total > pageSize
  return (
    <div style={{
      background: 'var(--p-surface)', border: '1px solid var(--p-border)',
      borderRadius: 10, overflow: 'hidden',
    }}>
      <div className="pv2-scroll-x">
        <table style={{ width: '100%', borderCollapse: 'separate', borderSpacing: 0, fontSize: 13, minWidth: 640 }}>
          <thead>
            <tr>
              {columns.map((c) => (
                <th key={c.key} style={{ ...headStyle, textAlign: c.align ?? 'left' }}>{c.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={rowKey(row)}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                style={{ cursor: onRowClick ? 'pointer' : 'default' }}
              >
                {columns.map((c) => (
                  <td key={c.key} style={{
                    ...cellStyle,
                    textAlign: c.align ?? 'left',
                    fontFamily: c.align === 'right' ? 'var(--font-mono)' : undefined,
                  }}>
                    {c.render(row)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {showPagination && (
        <MoneyPagination page={page} total={total as number} pageSize={pageSize} onPageChange={onPageChange as (p: number) => void} />
      )}
    </div>
  )
}
