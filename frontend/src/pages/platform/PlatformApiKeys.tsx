import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  apiKeysApi,
  platformApi,
  ApiKey,
  ApiKeyCreateResponse,
  ApiKeyScope,
  API_KEY_SCOPES,
  PlatformOrg,
} from '../../api/platform'
import { toast } from '../../store/toastStore'
import { KPICardV2 } from '../../components/platform/v2/KPICardV2'
import { DataTable, DataTableColumn } from '../../components/platform/DataTable'
import { SideDrawer } from '../../components/platform/SideDrawer'
import { ConfirmModal } from '../../components/platform/ConfirmModal'
import '../../styles/platform-v2.css'

// ── Constants ────────────────────────────────────────────────────────────────

type ActiveFilter = 'active' | 'revoked' | 'all'

const ACTIVE_FILTERS: { key: ActiveFilter; label: string }[] = [
  { key: 'active',  label: 'Activas' },
  { key: 'revoked', label: 'Revocadas' },
  { key: 'all',     label: 'Todas' },
]

const SCOPE_LABEL: Record<string, string> = {
  'catalog:read': 'Leer catálogo (tienda en línea)',
  'leads:write':  'Registrar contactos (tienda en línea)',
}

// ── Utilities ────────────────────────────────────────────────────────────────

function relativeTime(iso: string | null): string {
  if (!iso) return '—'
  const then = new Date(iso).getTime()
  if (!Number.isFinite(then)) return '—'
  const diffMs = Date.now() - then
  const sec = Math.floor(diffMs / 1000)
  if (sec < 45) return 'hace un momento'
  const min = Math.floor(sec / 60)
  if (min < 60) return `hace ${min} min`
  const hr = Math.floor(min / 60)
  if (hr < 24) return `hace ${hr} h`
  const day = Math.floor(hr / 24)
  if (day < 7) return `hace ${day} d`
  const week = Math.floor(day / 7)
  if (week < 5) return `hace ${week} sem`
  return new Date(iso).toLocaleDateString('es-MX', { day: '2-digit', month: 'short', year: 'numeric' })
}

// ── Page ─────────────────────────────────────────────────────────────────────

export function PlatformApiKeys() {
  const [keys, setKeys] = useState<ApiKey[]>([])
  const [orgs, setOrgs] = useState<PlatformOrg[]>([])
  const [loading, setLoading] = useState(true)

  // Filters
  const [activeFilter, setActiveFilter] = useState<ActiveFilter>('active')
  const [orgFilter, setOrgFilter] = useState<number | ''>('')

  // Create drawer
  const [createOpen, setCreateOpen] = useState(false)
  const [createOrgId, setCreateOrgId] = useState<number | ''>('')
  const [createName, setCreateName] = useState('')
  const [createScopes, setCreateScopes] = useState<ApiKeyScope[]>([])
  const [saving, setSaving] = useState(false)

  // Full-key reveal modal (one-time)
  const [fullKey, setFullKey] = useState<ApiKeyCreateResponse | null>(null)
  const [copied, setCopied] = useState(false)

  // Revoke confirm
  const [toRevoke, setToRevoke] = useState<ApiKey | null>(null)
  const [revoking, setRevoking] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [rows, orgsList] = await Promise.all([
        apiKeysApi.list(),
        platformApi.getOrgs().catch(() => [] as PlatformOrg[]),
      ])
      setKeys(Array.isArray(rows) ? rows : [])
      setOrgs(Array.isArray(orgsList) ? orgsList : [])
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } }
      toast.error(e?.response?.data?.detail || 'No se pudieron cargar las API keys')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  // ── Derived ────────────────────────────────────────────────────────────

  const filtered = useMemo(() => {
    return keys.filter(k => {
      if (activeFilter === 'active' && k.revoked_at) return false
      if (activeFilter === 'revoked' && !k.revoked_at) return false
      if (orgFilter !== '' && k.organization_id !== orgFilter) return false
      return true
    })
  }, [keys, activeFilter, orgFilter])

  const kpis = useMemo(() => {
    const now = Date.now()
    const sevenDaysAgo = now - 7 * 24 * 60 * 60 * 1000
    const thirtyDaysAgo = now - 30 * 24 * 60 * 60 * 1000
    let active = 0
    let usedLast7d = 0
    let revoked30d = 0
    for (const k of keys) {
      if (!k.revoked_at) active += 1
      if (k.last_used_at && new Date(k.last_used_at).getTime() >= sevenDaysAgo) usedLast7d += 1
      if (k.revoked_at && new Date(k.revoked_at).getTime() >= thirtyDaysAgo) revoked30d += 1
    }
    return { active, usedLast7d, revoked30d }
  }, [keys])

  // ── Handlers ───────────────────────────────────────────────────────────

  const openCreate = () => {
    setCreateOrgId(orgs.length === 1 ? orgs[0].id : '')
    setCreateName('')
    setCreateScopes([])
    setCreateOpen(true)
  }

  const closeCreate = () => {
    if (saving) return
    setCreateOpen(false)
  }

  const toggleScope = (s: ApiKeyScope) => {
    setCreateScopes(prev => prev.includes(s) ? prev.filter(x => x !== s) : [...prev, s])
  }

  const submitCreate = async () => {
    if (createOrgId === '' || !Number.isFinite(createOrgId)) {
      toast.error('Selecciona una organización')
      return
    }
    const nameTrim = createName.trim()
    if (!nameTrim) { toast.error('El nombre es requerido'); return }

    setSaving(true)
    try {
      const res = await apiKeysApi.create({
        organization_id: Number(createOrgId),
        name: nameTrim,
        scopes: createScopes.length ? createScopes : undefined,
      })
      toast.success('API key creada')
      setCreateOpen(false)
      setFullKey(res)
      setCopied(false)
      // Refresh list in background — the reveal modal is the primary UI now.
      load()
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } }
      toast.error(e?.response?.data?.detail || 'No se pudo crear la API key')
    } finally {
      setSaving(false)
    }
  }

  const copyFullKey = async () => {
    if (!fullKey) return
    try {
      await navigator.clipboard.writeText(fullKey.full_key)
      setCopied(true)
      toast.success('Token copiado al portapapeles')
    } catch {
      toast.error('No se pudo copiar automáticamente — selecciona y copia manualmente')
    }
  }

  const confirmRevoke = async () => {
    if (!toRevoke) return
    setRevoking(true)
    try {
      const updated = await apiKeysApi.revoke(toRevoke.id)
      setKeys(prev => prev.map(k => k.id === updated.id ? updated : k))
      toast.success('API key revocada')
      setToRevoke(null)
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } }
      toast.error(e?.response?.data?.detail || 'No se pudo revocar')
    } finally {
      setRevoking(false)
    }
  }

  // ── DataTable columns ──────────────────────────────────────────────────

  const columns: DataTableColumn<ApiKey>[] = [
    {
      key: 'org',
      label: 'Organization',
      sortable: true,
      sortValue: (r) => (r.org_name || '').toLowerCase(),
      accessor: (r) => (
        <Link
          to={`/platform/organizations/${r.organization_id}`}
          style={{
            color: 'var(--p-text)',
            fontSize: 13,
            fontWeight: 600,
            textDecoration: 'none',
          }}
          onClick={(e) => e.stopPropagation()}
        >
          {r.org_name || `#${r.organization_id}`}
        </Link>
      ),
    },
    {
      key: 'name',
      label: 'Name',
      sortable: true,
      sortValue: (r) => r.name.toLowerCase(),
      accessor: (r) => (
        <span style={{ color: 'var(--p-text)', fontSize: 13 }}>{r.name}</span>
      ),
    },
    {
      key: 'prefix',
      label: 'Prefix',
      width: '160px',
      accessor: (r) => (
        <code
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            padding: '2px 8px',
            borderRadius: 4,
            background: 'var(--p-surface-2)',
            color: 'var(--p-muted)',
            border: '1px solid var(--p-border)',
          }}
        >
          atlas_{r.prefix}…
        </code>
      ),
    },
    {
      key: 'scopes',
      label: 'Scopes',
      accessor: (r) => (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
          {(r.scopes && r.scopes.length > 0) ? r.scopes.map(s => (
            <span
              key={s}
              title={SCOPE_LABEL[s as ApiKeyScope] || s}
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 10,
                padding: '2px 8px',
                borderRadius: 999,
                background: 'var(--p-accent-soft)',
                color: 'var(--p-accent)',
                border: '1px solid var(--p-accent-line)',
                fontWeight: 600,
              }}
            >
              {s}
            </span>
          )) : (
            <span style={{ color: 'var(--p-hint)', fontSize: 11, fontFamily: 'var(--font-mono)' }}>—</span>
          )}
        </div>
      ),
    },
    {
      key: 'last_used',
      label: 'Last used',
      sortable: true,
      sortValue: (r) => r.last_used_at ? new Date(r.last_used_at).getTime() : 0,
      width: '140px',
      accessor: (r) => (
        <span
          title={r.last_used_at ? new Date(r.last_used_at).toLocaleString() : 'Nunca usada'}
          style={{ color: 'var(--p-muted)', fontSize: 12, fontFamily: 'var(--font-mono)' }}
        >
          {r.last_used_at ? relativeTime(r.last_used_at) : 'Nunca'}
        </span>
      ),
    },
    {
      key: 'created',
      label: 'Created',
      sortable: true,
      sortValue: (r) => r.created_at ? new Date(r.created_at).getTime() : 0,
      width: '140px',
      accessor: (r) => (
        <span
          title={r.created_at ? new Date(r.created_at).toLocaleString() : ''}
          style={{ color: 'var(--p-muted)', fontSize: 12, fontFamily: 'var(--font-mono)' }}
        >
          {relativeTime(r.created_at)}
        </span>
      ),
    },
    {
      key: 'status',
      label: 'Status',
      sortable: true,
      sortValue: (r) => r.revoked_at ? 1 : 0,
      width: '110px',
      accessor: (r) => {
        const revoked = !!r.revoked_at
        return (
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              padding: '2px 10px',
              borderRadius: 999,
              background: revoked ? 'rgba(239,68,68,0.10)' : 'rgba(34,197,94,0.10)',
              color: revoked ? 'var(--p-danger)' : 'var(--p-success)',
              border: '1px solid ' + (revoked ? 'rgba(239,68,68,0.25)' : 'rgba(34,197,94,0.25)'),
              fontFamily: 'var(--font-mono)',
              fontSize: 10,
              fontWeight: 600,
              textTransform: 'uppercase',
              letterSpacing: '0.08em',
            }}
          >
            <span
              aria-hidden
              style={{
                width: 6, height: 6, borderRadius: '50%',
                background: revoked ? 'var(--p-danger)' : 'var(--p-success)',
              }}
            />
            {revoked ? 'Revocada' : 'Activa'}
          </span>
        )
      },
    },
    {
      key: 'actions',
      label: '',
      width: '120px',
      accessor: (r) => (
        r.revoked_at ? (
          <span style={{ color: 'var(--p-hint)', fontSize: 11, fontFamily: 'var(--font-mono)' }}>—</span>
        ) : (
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); setToRevoke(r) }}
            style={{
              background: 'transparent',
              border: '1px solid var(--p-border)',
              color: 'var(--p-danger)',
              padding: '4px 10px',
              borderRadius: 6,
              fontSize: 11,
              fontWeight: 600,
              cursor: 'pointer',
              fontFamily: 'var(--font-sans)',
            }}
          >
            <i className="fa-solid fa-ban" style={{ fontSize: 10, marginRight: 6 }} />
            Revocar
          </button>
        )
      ),
    },
  ]

  // ── CSV export (never includes hashes) ─────────────────────────────────

  const csvRow = (r: ApiKey): Record<string, string | number> => ({
    id: r.id,
    organization_id: r.organization_id,
    org_name: r.org_name ?? '',
    name: r.name,
    prefix: `atlas_${r.prefix}`,
    scopes: (r.scopes ?? []).join('|'),
    last_used_at: r.last_used_at ?? '',
    last_used_ip: r.last_used_ip ?? '',
    created_at: r.created_at ?? '',
    revoked_at: r.revoked_at ?? '',
  })

  const searchKeys = (r: ApiKey): string =>
    `${r.name} ${r.prefix} ${r.org_name ?? ''}`

  // ── Render ─────────────────────────────────────────────────────────────

  return (
    <>
      <main className="pv2-main">
        {/* Breadcrumb */}
        <div className="crumb">
          <span>Platform</span>
          <span className="sep">/</span>
          <span className="now">API keys</span>
        </div>

        {/* Head */}
        <div className="page-head">
          <div>
            <h1>API keys</h1>
            <div className="sub">Tokens server-to-server por organización</div>
          </div>
          <div className="right" style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
            <div role="group" aria-label="Filtro por estado" style={pillGroupStyle}>
              {ACTIVE_FILTERS.map(chip => {
                const isActive = activeFilter === chip.key
                return (
                  <button
                    key={chip.key}
                    type="button"
                    aria-pressed={isActive}
                    onClick={() => setActiveFilter(chip.key)}
                    style={{
                      ...pillStyle,
                      background: isActive ? 'var(--p-accent-soft)' : 'transparent',
                      color: isActive ? 'var(--p-accent)' : 'var(--p-muted)',
                      borderColor: isActive ? 'var(--p-accent-line)' : 'transparent',
                    }}
                  >
                    {chip.label}
                  </button>
                )
              })}
            </div>
            <select
              value={orgFilter}
              onChange={(e) => setOrgFilter(e.target.value === '' ? '' : Number(e.target.value))}
              style={selectStyle}
              aria-label="Filtrar por organización"
            >
              <option value="">Todas las organizaciones</option>
              {orgs.map(o => (
                <option key={o.id} value={o.id}>{o.name}</option>
              ))}
            </select>
            <button
              type="button"
              className="btn primary"
              onClick={openCreate}
              aria-label="Nueva API key"
            >
              <i className="fa-solid fa-plus" />
              Nueva API key
            </button>
          </div>
        </div>

        {/* KPIs */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 14 }}>
          <KPICardV2 label="Keys activas" value={kpis.active} icon="fa-key" />
          <KPICardV2 label="Usadas últimos 7d" value={kpis.usedLast7d} icon="fa-bolt" />
          <KPICardV2 label="Revocadas 30d" value={kpis.revoked30d} icon="fa-ban" />
        </div>

        {/* Table */}
        {loading ? (
          <div style={{ color: 'var(--p-muted)', fontSize: 13 }}>
            <i className="fa-solid fa-circle-notch fa-spin" /> Cargando…
          </div>
        ) : (
          <DataTable<ApiKey>
            data={filtered}
            columns={columns}
            rowKey={(r) => r.id}
            searchable
            searchKeys={searchKeys}
            pageSize={25}
            emptyMessage="Sin API keys"
            csvFilename="api-keys.csv"
            csvRow={csvRow}
          />
        )}
      </main>

      {/* Create drawer */}
      <SideDrawer
        open={createOpen}
        title="Nueva API key"
        subtitle="Genera un token server-to-server para una organización"
        onClose={closeCreate}
        width={520}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <div style={fieldStyle}>
            <label style={labelStyle}>Organización</label>
            <select
              value={createOrgId}
              onChange={(e) => setCreateOrgId(e.target.value === '' ? '' : Number(e.target.value))}
              style={inputStyle}
              disabled={saving}
            >
              <option value="">Selecciona una organización…</option>
              {orgs.map(o => (
                <option key={o.id} value={o.id}>{o.name}</option>
              ))}
            </select>
          </div>

          <div style={fieldStyle}>
            <label style={labelStyle}>Nombre (descriptivo)</label>
            <input
              type="text"
              value={createName}
              onChange={(e) => setCreateName(e.target.value)}
              placeholder="Ej. Integración ERP principal"
              maxLength={120}
              style={inputStyle}
              disabled={saving}
            />
          </div>

          <div style={fieldStyle}>
            <label style={labelStyle}>Scopes (opcional)</label>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {API_KEY_SCOPES.map(s => {
                const selected = createScopes.includes(s)
                return (
                  <button
                    key={s}
                    type="button"
                    onClick={() => toggleScope(s)}
                    disabled={saving}
                    title={SCOPE_LABEL[s]}
                    style={{
                      padding: '5px 12px',
                      borderRadius: 999,
                      border: '1px solid ' + (selected ? 'var(--p-accent)' : 'var(--p-border)'),
                      background: selected ? 'var(--p-accent-soft)' : 'var(--p-surface-2)',
                      color: selected ? 'var(--p-accent)' : 'var(--p-muted)',
                      fontSize: 11,
                      fontFamily: 'var(--font-mono)',
                      fontWeight: 600,
                      cursor: saving ? 'not-allowed' : 'pointer',
                    }}
                  >
                    {s}
                  </button>
                )
              })}
            </div>
            <div style={{ fontSize: 11, color: 'var(--p-hint)', marginTop: 6 }}>
              Catálogo y contactos son los permisos de la tienda en línea; la llave solo funciona si la org tiene ese módulo encendido.
            </div>
          </div>

          <div
            style={{
              marginTop: 8,
              padding: 12,
              borderRadius: 8,
              border: '1px solid var(--p-border)',
              background: 'var(--p-surface-2)',
              color: 'var(--p-muted)',
              fontSize: 12,
              lineHeight: 1.5,
            }}
          >
            <i className="fa-solid fa-shield-halved" style={{ marginRight: 6, color: 'var(--p-accent)' }} />
            El secreto solo se mostrará <strong style={{ color: 'var(--p-text)' }}>una vez</strong> al crear la key. Guárdalo en un
            password manager. Nunca lo almacenamos en claro — solo un hash SHA-256.
          </div>
        </div>

        <div
          style={{
            marginTop: 16,
            display: 'flex',
            justifyContent: 'flex-end',
            gap: 10,
            paddingTop: 14,
            borderTop: '1px solid var(--p-border)',
          }}
        >
          <button
            type="button"
            onClick={closeCreate}
            disabled={saving}
            style={buttonSecondaryStyle}
          >
            Cancelar
          </button>
          <button
            type="button"
            onClick={submitCreate}
            disabled={saving}
            style={buttonPrimaryStyle}
          >
            {saving && <i className="fa-solid fa-circle-notch fa-spin" style={{ fontSize: 11 }} />}
            <i className="fa-solid fa-key" style={{ fontSize: 11 }} />
            {saving ? 'Creando…' : 'Generar API key'}
          </button>
        </div>
      </SideDrawer>

      {/* Full-key reveal modal (one-time) */}
      {fullKey && (
        <FullKeyRevealModal
          payload={fullKey}
          copied={copied}
          onCopy={copyFullKey}
          onDismiss={() => { setFullKey(null); setCopied(false) }}
        />
      )}

      {/* Revoke confirm */}
      <ConfirmModal
        open={!!toRevoke}
        title="Revocar API key"
        message={
          'Esta key dejará de autenticar inmediatamente después de revocarla. ' +
          'Esta acción se puede auditar pero no se puede deshacer. ' +
          'Escribe el prefix para confirmar.'
        }
        resourceName={toRevoke?.prefix ?? ''}
        destructive
        onClose={() => !revoking && setToRevoke(null)}
        onConfirm={confirmRevoke}
        busy={revoking}
      />
    </>
  )
}

// ── Full-key reveal modal ────────────────────────────────────────────────────

function FullKeyRevealModal({
  payload,
  copied,
  onCopy,
  onDismiss,
}: {
  payload: ApiKeyCreateResponse
  copied: boolean
  onCopy: () => void
  onDismiss: () => void
}) {
  return (
    <div
      style={{
        position: 'fixed', inset: 0,
        background: 'rgba(0,0,0,0.75)',
        backdropFilter: 'blur(4px)',
        zIndex: 1200,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontFamily: 'var(--font-sans)',
      }}
    >
      <div
        style={{
          background: 'var(--p-surface)',
          border: '1px solid var(--p-accent-line)',
          borderRadius: 14,
          padding: '26px 28px 22px',
          width: 560,
          maxWidth: '94vw',
          boxShadow: '0 20px 60px rgba(0,0,0,0.55)',
          color: 'var(--p-text)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14 }}>
          <div
            style={{
              width: 38, height: 38, borderRadius: 10,
              background: 'var(--p-accent-soft)',
              color: 'var(--p-accent)',
              display: 'grid', placeItems: 'center',
              flexShrink: 0,
              fontSize: 16,
            }}
          >
            <i className="fa-solid fa-key" />
          </div>
          <div style={{ minWidth: 0 }}>
            <h3
              style={{
                margin: 0,
                fontFamily: 'var(--font-display)',
                fontSize: 19,
                letterSpacing: '-0.02em',
                fontWeight: 600,
                lineHeight: 1.2,
              }}
            >
              API key creada
            </h3>
            <div style={{ fontSize: 12, color: 'var(--p-muted)', marginTop: 2 }}>
              {payload.org_name || `Org #${payload.organization_id}`} · {payload.name}
            </div>
          </div>
        </div>

        <div
          role="alert"
          style={{
            marginBottom: 14,
            padding: '10px 14px',
            borderRadius: 8,
            border: '1px solid rgba(245,158,11,0.35)',
            background: 'rgba(245,158,11,0.10)',
            color: 'var(--p-warning)',
            fontSize: 12,
            lineHeight: 1.5,
            display: 'flex',
            gap: 10,
            alignItems: 'flex-start',
          }}
        >
          <i className="fa-solid fa-triangle-exclamation" style={{ fontSize: 13, marginTop: 2 }} />
          <div>
            Esta es la <strong>única vez</strong> que verás este token. Guárdalo ahora en un password manager seguro —
            nunca lo volveremos a mostrar.
          </div>
        </div>

        <label
          style={{
            display: 'block',
            fontSize: 10,
            letterSpacing: '0.12em',
            textTransform: 'uppercase',
            color: 'var(--p-muted)',
            fontWeight: 600,
            marginBottom: 6,
          }}
        >
          Token completo
        </label>
        <div
          style={{
            display: 'flex',
            gap: 8,
            alignItems: 'stretch',
            marginBottom: 14,
          }}
        >
          <input
            readOnly
            value={payload.full_key}
            onFocus={(e) => e.currentTarget.select()}
            style={{
              flex: 1,
              background: 'var(--p-surface-2)',
              color: 'var(--p-text)',
              border: '1px solid var(--p-border)',
              padding: '10px 12px',
              borderRadius: 8,
              fontSize: 13,
              fontFamily: 'var(--font-mono)',
              outline: 'none',
              minWidth: 0,
            }}
          />
          <button
            type="button"
            onClick={onCopy}
            style={{
              background: copied ? 'var(--p-success)' : 'var(--p-accent)',
              color: '#fff',
              border: '1px solid ' + (copied ? 'var(--p-success)' : 'var(--p-accent)'),
              padding: '10px 16px',
              borderRadius: 8,
              fontSize: 13,
              fontWeight: 600,
              cursor: 'pointer',
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              whiteSpace: 'nowrap',
              fontFamily: 'var(--font-sans)',
            }}
          >
            <i className={'fa-solid ' + (copied ? 'fa-check' : 'fa-copy')} />
            {copied ? 'Copiado' : 'Copiar'}
          </button>
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <button
            type="button"
            onClick={onDismiss}
            disabled={!copied}
            style={{
              background: copied ? 'var(--p-surface-2)' : 'var(--p-border)',
              color: copied ? 'var(--p-text)' : 'var(--p-hint)',
              border: '1px solid var(--p-border)',
              padding: '10px 18px',
              borderRadius: 8,
              fontSize: 13,
              fontWeight: 600,
              cursor: copied ? 'pointer' : 'not-allowed',
              opacity: copied ? 1 : 0.5,
              fontFamily: 'var(--font-sans)',
            }}
          >
            {copied ? 'He copiado la key' : 'Copia primero la key'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Styles ───────────────────────────────────────────────────────────────────

const pillGroupStyle: React.CSSProperties = {
  display: 'inline-flex',
  background: 'var(--p-surface)',
  border: '1px solid var(--p-border)',
  borderRadius: 999,
  padding: 3,
  gap: 2,
}

const pillStyle: React.CSSProperties = {
  border: '1px solid transparent',
  padding: '4px 12px',
  borderRadius: 999,
  fontSize: 11,
  fontWeight: 600,
  cursor: 'pointer',
  fontFamily: 'inherit',
  letterSpacing: '0.04em',
  transition: 'background 0.15s ease, color 0.15s ease',
}

const selectStyle: React.CSSProperties = {
  background: 'var(--p-surface-2)',
  border: '1px solid var(--p-border)',
  color: 'var(--p-text)',
  padding: '7px 10px',
  borderRadius: 8,
  fontSize: 12,
  fontFamily: 'inherit',
  height: 34,
  minWidth: 0,
  maxWidth: 220,
}

const inputStyle: React.CSSProperties = {
  width: '100%',
  background: 'var(--p-surface-2)',
  color: 'var(--p-text)',
  border: '1px solid var(--p-border)',
  borderRadius: 6,
  padding: '8px 10px',
  fontSize: 13,
  fontFamily: 'var(--font-sans)',
  outline: 'none',
  boxSizing: 'border-box',
}

const labelStyle: React.CSSProperties = {
  display: 'block',
  fontSize: 11,
  textTransform: 'uppercase',
  letterSpacing: '0.08em',
  color: 'var(--p-muted)',
  fontWeight: 600,
  marginBottom: 6,
}

const fieldStyle: React.CSSProperties = { marginBottom: 14 }

const buttonSecondaryStyle: React.CSSProperties = {
  background: 'var(--p-surface-2)',
  color: 'var(--p-text)',
  border: '1px solid var(--p-border)',
  padding: '8px 16px',
  borderRadius: 8,
  cursor: 'pointer',
  fontSize: 13,
  fontWeight: 500,
  fontFamily: 'var(--font-sans)',
}

const buttonPrimaryStyle: React.CSSProperties = {
  background: 'var(--p-accent)',
  color: '#fff',
  border: '1px solid var(--p-accent)',
  padding: '8px 18px',
  borderRadius: 8,
  cursor: 'pointer',
  fontSize: 13,
  fontWeight: 600,
  display: 'inline-flex',
  alignItems: 'center',
  gap: 6,
  fontFamily: 'var(--font-sans)',
}

export default PlatformApiKeys
