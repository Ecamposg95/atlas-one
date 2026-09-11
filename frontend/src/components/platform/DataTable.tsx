import { useMemo, useState } from 'react'

import { TablaDesplazable } from '../ui/TablaDesplazable'
import { useMediaQuery } from '../../hooks/useMediaQuery'
import { cardColumns, cardKeyActivatesRow } from './dataTableCards'

export interface DataTableColumn<T> {
  key: string
  label: string
  accessor: (row: T) => React.ReactNode
  sortValue?: (row: T) => string | number
  sortable?: boolean
  width?: string
}

export type RowId = string | number

export interface BulkAction {
  key: string
  label: string
  icon?: string
  destructive?: boolean
  disabled?: boolean
  onRun: (ids: RowId[]) => Promise<void> | void
}

export type SelectionMode = 'none' | 'show-count-only' | 'toolbar'

interface Props<T> {
  data: T[]
  columns: DataTableColumn<T>[]
  searchable?: boolean
  searchKeys?: (row: T) => string
  pageSize?: number
  csvFilename?: string
  csvRow?: (row: T) => Record<string, string | number>
  rowKey: (row: T) => RowId
  onRowClick?: (row: T) => void
  emptyMessage?: string
  toolbar?: React.ReactNode
  // Selection (all optional — absence preserves existing behavior exactly)
  selectable?: boolean
  selectedIds?: RowId[]
  onSelectionChange?: (ids: RowId[]) => void
  bulkActions?: BulkAction[]
  selectionMode?: SelectionMode
}

const btnStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 6,
  height: 32,
  padding: '0 12px',
  borderRadius: 8,
  background: 'var(--p-surface)',
  border: '1px solid var(--p-border)',
  color: 'var(--p-text)',
  fontSize: 12,
  fontWeight: 500,
  cursor: 'pointer',
  fontFamily: 'var(--font-sans)',
}

const checkboxStyle: React.CSSProperties = {
  width: 16,
  height: 16,
  accentColor: 'var(--p-accent)',
  cursor: 'pointer',
  margin: 0,
}

function BulkToolbar({
  count, actions, runningKey, onClear, onRun,
}: {
  count: number
  actions: BulkAction[]
  runningKey: string | null
  onClear: () => void
  onRun: (a: BulkAction) => void
}) {
  return (
    <div style={{
      padding: '14px 18px', display: 'flex', gap: 10,
      justifyContent: 'space-between', alignItems: 'center',
      borderBottom: '1px solid var(--p-border)', flexWrap: 'wrap',
      background: 'var(--p-surface-2)',
    }}>
      <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
        <span style={{
          fontFamily: 'var(--font-display)', fontSize: 15, color: 'var(--p-text)',
          fontWeight: 600, letterSpacing: '-0.01em',
        }}>
          {count} {count === 1 ? 'seleccionada' : 'seleccionadas'}
        </span>
        <button
          type="button" onClick={onClear}
          style={{ ...btnStyle, height: 28, padding: '0 10px', fontSize: 11, background: 'transparent' }}
        >
          Limpiar
        </button>
      </div>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        {actions.map(action => {
          const running = runningKey === action.key
          const disabled = action.disabled || !!runningKey
          return (
            <button
              key={action.key} type="button" disabled={disabled}
              onClick={() => onRun(action)}
              style={{
                ...btnStyle,
                opacity: disabled ? 0.6 : 1,
                cursor: disabled ? 'not-allowed' : 'pointer',
                ...(action.destructive ? { color: 'var(--p-danger)' } : {}),
              }}
              onMouseEnter={(e) => {
                if (disabled) return
                if (action.destructive) e.currentTarget.style.borderColor = 'var(--p-danger)'
                else e.currentTarget.style.background = 'var(--p-surface-2)'
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.borderColor = 'var(--p-border)'
                e.currentTarget.style.background = 'var(--p-surface)'
              }}
            >
              {running
                ? <i className="fa-solid fa-spinner fa-spin" style={{ fontSize: 11 }} />
                : action.icon ? <i className={action.icon} style={{ fontSize: 11 }} /> : null}
              {action.label}
            </button>
          )
        })}
      </div>
    </div>
  )
}

export function DataTable<T>({
  data, columns, searchable = true, searchKeys, pageSize = 20,
  csvFilename, csvRow, rowKey, onRowClick, emptyMessage = 'Sin datos', toolbar,
  selectable = false, selectedIds, onSelectionChange, bulkActions, selectionMode = 'toolbar',
}: Props<T>) {
  const [search, setSearch] = useState('')
  const [sortKey, setSortKey] = useState<string | null>(null)
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc')
  const [page, setPage] = useState(0)
  const [runningKey, setRunningKey] = useState<string | null>(null)
  // Bajo 640 px la tabla no cabe ni con scroll: cada fila se pinta como tarjeta.
  const isCards = useMediaQuery('(max-width: 639px)')
  const cardCols = useMemo(() => (isCards && columns.length > 0 ? cardColumns(columns) : null), [isCards, columns])

  const filtered = useMemo(() => {
    if (!search.trim() || !searchKeys) return data
    const q = search.toLowerCase()
    return data.filter(r => searchKeys(r).toLowerCase().includes(q))
  }, [data, search, searchKeys])

  const sorted = useMemo(() => {
    if (!sortKey) return filtered
    const col = columns.find(c => c.key === sortKey)
    if (!col?.sortValue) return filtered
    return [...filtered].sort((a, b) => {
      const va = col.sortValue!(a)
      const vb = col.sortValue!(b)
      if (va < vb) return sortDir === 'asc' ? -1 : 1
      if (va > vb) return sortDir === 'asc' ? 1 : -1
      return 0
    })
  }, [filtered, sortKey, sortDir, columns])

  const pages = Math.max(1, Math.ceil(sorted.length / pageSize))
  const pageRows = sorted.slice(page * pageSize, (page + 1) * pageSize)

  const toggleSort = (key: string) => {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortKey(key); setSortDir('asc') }
  }

  const exportCSV = () => {
    if (!csvRow || !csvFilename) return
    const rows = sorted.map(csvRow)
    if (rows.length === 0) return
    const headers = Object.keys(rows[0])
    const csv = [
      headers.join(','),
      ...rows.map(r => headers.map(h => JSON.stringify(r[h] ?? '')).join(',')),
    ].join('\n')
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = csvFilename
    a.click()
    URL.revokeObjectURL(url)
  }

  // ── Selection helpers ──────────────────────────────────────────
  const selected = selectedIds ?? []
  const selectedSet = useMemo(() => new Set<RowId>(selected), [selected])
  const pageIds = useMemo(() => pageRows.map(rowKey), [pageRows, rowKey])
  const pageSelectedCount: number = pageIds.reduce<number>(
    (n, id) => n + (selectedSet.has(id) ? 1 : 0), 0,
  )
  const allPageSelected = pageIds.length > 0 && pageSelectedCount === pageIds.length
  const somePageSelected = pageSelectedCount > 0 && !allPageSelected

  const emit = (ids: RowId[]) => onSelectionChange?.(ids)

  const toggleRow = (id: RowId) => {
    if (!onSelectionChange) return
    if (selectedSet.has(id)) emit(selected.filter(x => x !== id))
    else emit([...selected, id])
  }

  const toggleAllPage = () => {
    if (!onSelectionChange) return
    if (allPageSelected) {
      const pageSet = new Set<RowId>(pageIds)
      emit(selected.filter(id => !pageSet.has(id)))
    } else {
      const merged = new Set<RowId>(selected)
      pageIds.forEach(id => merged.add(id))
      emit(Array.from(merged))
    }
  }

  const runBulk = async (action: BulkAction) => {
    if (action.disabled || runningKey) return
    try {
      setRunningKey(action.key)
      await action.onRun(selected)
    } finally {
      setRunningKey(null)
    }
  }

  const showBulkToolbar =
    selectable &&
    selectionMode === 'toolbar' &&
    selected.length > 0

  const hasTopBar = searchable || csvRow || toolbar || showBulkToolbar

  return (
    <div style={{
      background: 'var(--p-surface)',
      border: '1px solid var(--p-border)',
      borderRadius: 14,
      overflow: 'hidden',
      fontFamily: 'var(--font-sans)',
    }}>
      {hasTopBar && (showBulkToolbar ? (
        <BulkToolbar
          count={selected.length}
          actions={bulkActions ?? []}
          runningKey={runningKey}
          onClear={() => emit([])}
          onRun={runBulk}
        />
      ) : (
        <div style={{
          padding: '14px 18px', display: 'flex', gap: 10,
          justifyContent: 'space-between', alignItems: 'center',
          borderBottom: '1px solid var(--p-border)', flexWrap: 'wrap',
        }}>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
            {searchable && (
              <input
                value={search}
                onChange={e => { setSearch(e.target.value); setPage(0) }}
                placeholder="Buscar…"
                style={{
                  background: 'var(--p-surface-2)', border: '1px solid var(--p-border)',
                  color: 'var(--p-text)', padding: '8px 12px', borderRadius: 8,
                  fontSize: 13, width: 260, outline: 'none', fontFamily: 'var(--font-sans)',
                }}
              />
            )}
            {toolbar}
            {selectable && selectionMode === 'show-count-only' && selected.length > 0 && (
              <span style={{ color: 'var(--p-muted)', fontSize: 12, fontFamily: 'var(--font-mono)' }}>
                {selected.length} {selected.length === 1 ? 'seleccionada' : 'seleccionadas'}
              </span>
            )}
          </div>
          {csvRow && csvFilename && (
            <button onClick={exportCSV} style={btnStyle}>
              <i className="fa-solid fa-download" style={{ fontSize: 11, color: 'var(--p-muted)' }} /> CSV
            </button>
          )}
        </div>
      ))}
      {cardCols ? (
        <div className="pv2-dt-cards">
          {pageRows.length === 0 ? (
            <div style={{ padding: 32, textAlign: 'center', color: 'var(--p-muted)', fontSize: 13 }}>{emptyMessage}</div>
          ) : pageRows.map((r) => {
            const id = rowKey(r)
            const isSelected = selectable && selectedSet.has(id)
            const { primary, secondary, actions } = cardCols
            return (
              <div
                key={id}
                className={'pv2-dt-card' + (isSelected ? ' selected' : '')}
                role={onRowClick ? 'button' : undefined}
                tabIndex={onRowClick ? 0 : undefined}
                onClick={() => onRowClick?.(r)}
                onKeyDown={onRowClick ? (e) => {
                  if (!cardKeyActivatesRow(e.key, e.target === e.currentTarget)) return
                  e.preventDefault()
                  onRowClick(r)
                } : undefined}
              >
                <div className="pv2-dt-card-head">
                  {selectable && (
                    <input
                      type="checkbox"
                      aria-label="Seleccionar fila"
                      checked={selectedSet.has(id)}
                      onChange={() => toggleRow(id)}
                      onClick={e => e.stopPropagation()}
                      onKeyDown={e => e.stopPropagation()}
                      style={checkboxStyle}
                    />
                  )}
                  <div className="pv2-dt-card-title">{primary.accessor(r)}</div>
                </div>
                {secondary.length > 0 && (
                  <dl className="pv2-dt-card-body">
                    {secondary.map(c => (
                      <div key={c.key} className="pv2-dt-card-row">
                        <dt>{c.label}</dt>
                        <dd>{c.accessor(r)}</dd>
                      </div>
                    ))}
                  </dl>
                )}
                {actions && (
                  <div
                    className="pv2-dt-card-actions"
                    onClick={e => e.stopPropagation()}
                    onKeyDown={e => e.stopPropagation()}
                  >
                    {actions.accessor(r)}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      ) : (
      <TablaDesplazable>
        <table style={{
          width: '100%',
          borderCollapse: 'separate',
          borderSpacing: 0,
          fontSize: 13,
        }}>
          <thead>
            <tr>
              {selectable && (
                <th style={{
                  padding: '10px 14px',
                  width: 40,
                  borderBottom: '1px solid var(--p-border)',
                  background: 'transparent',
                  textAlign: 'left',
                }}>
                  <input
                    type="checkbox"
                    aria-label="Seleccionar todo"
                    checked={allPageSelected}
                    ref={el => { if (el) el.indeterminate = somePageSelected }}
                    onChange={toggleAllPage}
                    onClick={e => e.stopPropagation()}
                    style={checkboxStyle}
                  />
                </th>
              )}
              {columns.map(c => (
                <th
                  key={c.key}
                  onClick={() => c.sortable && toggleSort(c.key)}
                  style={{
                    padding: '10px 16px',
                    textAlign: 'left',
                    color: 'var(--p-hint)',
                    fontSize: 10,
                    textTransform: 'uppercase',
                    letterSpacing: '0.12em',
                    fontWeight: 500,
                    cursor: c.sortable ? 'pointer' : 'default',
                    userSelect: 'none',
                    borderBottom: '1px solid var(--p-border)',
                    width: c.width,
                    background: 'transparent',
                  }}
                >
                  {c.label}
                  {sortKey === c.key && (
                    <span style={{ marginLeft: 6, color: 'var(--p-accent)' }}>
                      {sortDir === 'asc' ? '↑' : '↓'}
                    </span>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pageRows.length === 0 ? (
              <tr>
                <td
                  colSpan={columns.length + (selectable ? 1 : 0)}
                  style={{ padding: 32, textAlign: 'center', color: 'var(--p-muted)', fontSize: 13 }}
                >
                  {emptyMessage}
                </td>
              </tr>
            ) : pageRows.map((r, i) => {
              const id = rowKey(r)
              const isSelected = selectable && selectedSet.has(id)
              return (
                <tr
                  key={id}
                  onClick={() => onRowClick?.(r)}
                  style={{
                    cursor: onRowClick ? 'pointer' : 'default',
                    transition: 'background 0.12s ease',
                    background: isSelected ? 'var(--p-surface-2)' : 'transparent',
                  }}
                  onMouseEnter={(e) => { if (onRowClick) e.currentTarget.style.background = 'var(--p-surface-2)' }}
                  onMouseLeave={(e) => { if (onRowClick) e.currentTarget.style.background = isSelected ? 'var(--p-surface-2)' : 'transparent' }}
                >
                  {selectable && (
                    <td
                      onClick={e => e.stopPropagation()}
                      style={{
                        padding: '14px 14px',
                        borderBottom: i === pageRows.length - 1 ? 'none' : '1px solid var(--p-border-2)',
                        width: 40,
                        verticalAlign: 'middle',
                      }}
                    >
                      <input
                        type="checkbox"
                        aria-label="Seleccionar fila"
                        checked={selectedSet.has(id)}
                        onChange={() => toggleRow(id)}
                        onClick={e => e.stopPropagation()}
                        style={checkboxStyle}
                      />
                    </td>
                  )}
                  {columns.map(c => (
                    <td
                      key={c.key}
                      style={{
                        padding: '14px 16px',
                        borderBottom: i === pageRows.length - 1 ? 'none' : '1px solid var(--p-border-2)',
                        color: 'var(--p-text)',
                        verticalAlign: 'middle',
                      }}
                    >
                      {c.accessor(r)}
                    </td>
                  ))}
                </tr>
              )
            })}
          </tbody>
        </table>
      </TablaDesplazable>
      )}
      {pages > 1 && (
        <div style={{
          padding: '12px 18px',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          borderTop: '1px solid var(--p-border)',
          fontFamily: 'var(--font-sans)',
        }}>
          <button
            onClick={() => setPage(p => Math.max(0, p - 1))}
            disabled={page === 0}
            style={{ ...btnStyle, opacity: page === 0 ? 0.5 : 1, cursor: page === 0 ? 'not-allowed' : 'pointer' }}
          >
            <i className="fa-solid fa-chevron-left" style={{ fontSize: 10 }} /> Anterior
          </button>
          <span style={{
            color: 'var(--p-muted)',
            fontSize: 11,
            fontFamily: 'var(--font-mono)',
            fontVariantNumeric: 'tabular-nums',
          }}>
            Pág. {page + 1} / {pages} · {sorted.length} registros
          </span>
          <button
            onClick={() => setPage(p => Math.min(pages - 1, p + 1))}
            disabled={page >= pages - 1}
            style={{ ...btnStyle, opacity: page >= pages - 1 ? 0.5 : 1, cursor: page >= pages - 1 ? 'not-allowed' : 'pointer' }}
          >
            Siguiente <i className="fa-solid fa-chevron-right" style={{ fontSize: 10 }} />
          </button>
        </div>
      )}
    </div>
  )
}
