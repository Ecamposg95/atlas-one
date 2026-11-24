import { useEffect, useMemo, useState } from 'react'
import {
  platformApi,
  type IndustryPreset,
  type Module as PlatformModule,
} from '../../api/platform'
import { toast } from '../../store/toastStore'

// ─── Types ───────────────────────────────────────────────────────────────────

interface Props {
  open: boolean
  onClose: () => void
  onSuccess: (orgId: number) => void
}

type StepKey = 1 | 2 | 3 | 4

type StepStatus = 'pending' | 'running' | 'done' | 'failed'

interface SubmitStepState {
  key: 'org' | 'modules' | 'branch' | 'admin'
  label: string
  status: StepStatus
  detail?: string
}

interface IdentityForm {
  name: string
  legal_name: string
  tax_id: string
  email: string
  phone: string
  industry_type: string
  timezone: string
}

interface BranchForm {
  name: string
  address: string
  phone: string
  can_sell: boolean
}

interface AdminForm {
  username: string
  full_name: string
  email: string
  password: string
}

// ─── Shared inline styles (design tokens only) ───────────────────────────────

const inputStyle: React.CSSProperties = {
  width: '100%',
  background: 'var(--p-surface-2)',
  color: 'var(--p-text)',
  border: '1px solid var(--p-border)',
  borderRadius: 6,
  padding: '9px 11px',
  fontSize: 13,
  outline: 'none',
  boxSizing: 'border-box',
  fontFamily: 'var(--font-sans)',
}

const labelStyle: React.CSSProperties = {
  display: 'block',
  fontSize: 11,
  color: 'var(--p-muted)',
  textTransform: 'uppercase',
  letterSpacing: '0.08em',
  fontWeight: 600,
  marginBottom: 5,
}

const helpTextStyle: React.CSSProperties = {
  fontSize: 11,
  color: 'var(--p-hint)',
  margin: '6px 0 0',
  lineHeight: 1.5,
}

const errorTextStyle: React.CSSProperties = {
  fontSize: 11,
  color: 'var(--p-danger)',
  margin: '4px 0 0',
}

const sectionTitleStyle: React.CSSProperties = {
  margin: 0,
  fontFamily: 'var(--font-display)',
  fontSize: 15,
  fontWeight: 600,
  color: 'var(--p-text)',
  letterSpacing: '-0.01em',
}

// ─── Step header ─────────────────────────────────────────────────────────────

function StepHeader({ step }: { step: StepKey }) {
  const items: Array<{ n: StepKey; label: string }> = [
    { n: 1, label: 'Identidad' },
    { n: 2, label: 'Módulos' },
    { n: 3, label: 'Sucursal' },
    { n: 4, label: 'Admin' },
  ]
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        flexWrap: 'wrap',
        marginTop: 10,
      }}
    >
      {items.map((it, idx) => {
        const done = step > it.n
        const current = step === it.n
        const color = current
          ? 'var(--p-accent)'
          : done
          ? 'var(--p-text)'
          : 'var(--p-hint)'
        const bg = current
          ? 'var(--p-accent-soft)'
          : done
          ? 'var(--p-surface-2)'
          : 'transparent'
        return (
          <div key={it.n} style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 6,
                padding: '4px 10px',
                borderRadius: 999,
                background: bg,
                color,
                border: `1px solid ${current ? 'var(--p-accent-line, var(--p-accent))' : 'var(--p-border)'}`,
                fontSize: 11,
                fontWeight: 600,
                letterSpacing: '0.02em',
                fontFamily: 'var(--font-sans)',
              }}
            >
              <span
                style={{
                  width: 18,
                  height: 18,
                  borderRadius: '50%',
                  background: current ? 'var(--p-accent)' : done ? 'var(--p-text)' : 'var(--p-surface-2)',
                  color: current || done ? '#fff' : 'var(--p-hint)',
                  display: 'grid',
                  placeItems: 'center',
                  fontSize: 10,
                  fontWeight: 600,
                }}
              >
                {done ? <i className="fa-solid fa-check" style={{ fontSize: 9 }} /> : it.n}
              </span>
              {it.label}
            </span>
            {idx < items.length - 1 && (
              <span style={{ color: 'var(--p-hint)', fontSize: 11 }}>→</span>
            )}
          </div>
        )
      })}
    </div>
  )
}

// ─── Component ───────────────────────────────────────────────────────────────

export function PlatformOrgWizard({ open, onClose, onSuccess }: Props) {
  // Navigation
  const [step, setStep] = useState<StepKey>(1)
  const [submitting, setSubmitting] = useState(false)
  const [confirmClose, setConfirmClose] = useState(false)

  // Data sources
  const [presets, setPresets] = useState<IndustryPreset[]>([])
  const [catalog, setCatalog] = useState<PlatformModule[]>([])
  const [loadingMeta, setLoadingMeta] = useState(false)

  // Form state
  const [identity, setIdentity] = useState<IdentityForm>({
    name: '',
    legal_name: '',
    tax_id: '',
    email: '',
    phone: '',
    industry_type: 'ATLAS_POS',
    timezone: 'America/Mexico_City',
  })
  const [selectedModules, setSelectedModules] = useState<Set<string>>(new Set())
  const [modulesTouched, setModulesTouched] = useState(false)
  const [branch, setBranch] = useState<BranchForm>({
    name: 'Matriz',
    address: '',
    phone: '',
    can_sell: true,
  })
  const [admin, setAdmin] = useState<AdminForm>({
    username: '',
    full_name: '',
    email: '',
    password: '',
  })

  // Per-step submit progress
  const [progress, setProgress] = useState<SubmitStepState[]>([])

  // ── Reset on open ─────────────────────────────────────────────────────────
  useEffect(() => {
    if (!open) return
    setStep(1)
    setSubmitting(false)
    setConfirmClose(false)
    setIdentity({
      name: '',
      legal_name: '',
      tax_id: '',
      email: '',
      phone: '',
      industry_type: 'ATLAS_POS',
      timezone: 'America/Mexico_City',
    })
    setSelectedModules(new Set())
    setModulesTouched(false)
    setBranch({ name: 'Matriz', address: '', phone: '', can_sell: true })
    setAdmin({ username: '', full_name: '', email: '', password: '' })
    setProgress([])
    setLoadingMeta(true)
    Promise.all([
      platformApi.getPresets().catch(() => [] as IndustryPreset[]),
      platformApi.getModulesCatalog().catch(() => [] as PlatformModule[]),
    ])
      .then(([p, c]: [IndustryPreset[], PlatformModule[]]) => {
        setPresets(p)
        setCatalog(c)
        // If current industry is not in presets, fall back to first available
        if (p.length > 0 && !p.find((x: IndustryPreset) => x.industry_type === 'ATLAS_POS')) {
          setIdentity((prev) => ({ ...prev, industry_type: p[0].industry_type }))
        }
      })
      .finally(() => setLoadingMeta(false))
  }, [open])

  // ── When industry changes, refresh preset-derived module selection ────────
  const activePreset = useMemo(
    () => presets.find((p) => p.industry_type === identity.industry_type) || null,
    [presets, identity.industry_type],
  )

  useEffect(() => {
    if (!open) return
    if (!activePreset) return
    // Reset module selection to preset defaults whenever industry changes
    setSelectedModules(new Set(activePreset.modules))
    setModulesTouched(false)
  }, [open, activePreset?.id])

  // ── Validation ────────────────────────────────────────────────────────────
  const identityValid = identity.name.trim().length > 0
  const branchValid = branch.name.trim().length > 0
  const adminUsernameErr = admin.username.trim().length === 0 ? 'Requerido' : null
  const adminFullNameErr = admin.full_name.trim().length === 0 ? 'Requerido' : null
  const adminPasswordErr =
    admin.password.length === 0
      ? 'Requerido'
      : admin.password.length < 8
      ? 'Mínimo 8 caracteres'
      : null
  const adminValid = !adminUsernameErr && !adminFullNameErr && !adminPasswordErr

  const currentStepValid =
    step === 1
      ? identityValid
      : step === 2
      ? selectedModules.size > 0
      : step === 3
      ? branchValid
      : adminValid

  const isDirty =
    identity.name.trim() !== '' ||
    identity.legal_name.trim() !== '' ||
    identity.email.trim() !== '' ||
    branch.name.trim() !== 'Matriz' ||
    branch.address.trim() !== '' ||
    admin.username.trim() !== '' ||
    admin.full_name.trim() !== '' ||
    admin.password.length > 0 ||
    modulesTouched

  // ── Keyboard ──────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        requestClose()
      } else if (e.key === 'Enter') {
        // Avoid interfering with textareas or select
        const tag = (e.target as HTMLElement | null)?.tagName
        if (tag === 'TEXTAREA' || tag === 'SELECT') return
        if (!currentStepValid || submitting) return
        e.preventDefault()
        if (step < 4) {
          setStep((s) => (s + 1) as StepKey)
        } else {
          void handleSubmit()
        }
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, step, currentStepValid, submitting, identity, branch, admin, selectedModules])

  // ── Close handling ────────────────────────────────────────────────────────
  const requestClose = () => {
    if (submitting) return
    if (isDirty) {
      setConfirmClose(true)
    } else {
      onClose()
    }
  }

  const forceClose = () => {
    setConfirmClose(false)
    onClose()
  }

  // ── Module toggle ─────────────────────────────────────────────────────────
  const toggleModule = (key: string) => {
    setModulesTouched(true)
    setSelectedModules((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const resetModulesToPreset = () => {
    if (!activePreset) return
    setSelectedModules(new Set(activePreset.modules))
    setModulesTouched(false)
  }

  // ── Submit flow ───────────────────────────────────────────────────────────
  const updateProgress = (key: SubmitStepState['key'], patch: Partial<SubmitStepState>) => {
    setProgress((prev) => prev.map((p) => (p.key === key ? { ...p, ...patch } : p)))
  }

  const handleSubmit = async () => {
    if (!adminValid || !identityValid || !branchValid) return
    setSubmitting(true)

    const initial: SubmitStepState[] = [
      { key: 'org', label: 'Crear organización', status: 'pending' },
      { key: 'modules', label: 'Aplicar módulos', status: 'pending' },
      { key: 'branch', label: 'Crear sucursal HQ', status: 'pending' },
      { key: 'admin', label: 'Asignar admin', status: 'pending' },
    ]
    setProgress(initial)

    let orgId: number | null = null

    // Step 1: create org (backend auto-applies preset based on industry_type)
    updateProgress('org', { status: 'running' })
    try {
      const created = await platformApi.createOrg({
        name: identity.name.trim(),
        legal_name: identity.legal_name.trim() || null,
        tax_id: identity.tax_id.trim() || null,
        email: identity.email.trim() || null,
        phone: identity.phone.trim() || null,
        industry_type: identity.industry_type,
        timezone: identity.timezone.trim() || 'America/Mexico_City',
      })
      orgId = created.id
      updateProgress('org', { status: 'done', detail: `#${created.id}` })
    } catch (err) {
      const detail = extractErr(err) || 'Error al crear organización'
      updateProgress('org', { status: 'failed', detail })
      toast.error(detail)
      setSubmitting(false)
      return
    }

    // Step 2: reconcile modules with preset defaults if user customized
    if (modulesTouched && activePreset) {
      updateProgress('modules', { status: 'running' })
      try {
        const presetSet = new Set(activePreset.modules)
        const toggles: Array<Promise<unknown>> = []
        // Modules in preset but not selected → disable
        presetSet.forEach((key) => {
          if (!selectedModules.has(key)) {
            toggles.push(platformApi.toggleModule(orgId as number, key, false))
          }
        })
        // Modules selected but not in preset → enable
        selectedModules.forEach((key) => {
          if (!presetSet.has(key)) {
            toggles.push(platformApi.toggleModule(orgId as number, key, true))
          }
        })
        if (toggles.length > 0) {
          await Promise.all(toggles)
        }
        updateProgress('modules', {
          status: 'done',
          detail: `${selectedModules.size} módulos`,
        })
      } catch (err) {
        const detail = extractErr(err) || 'Error al ajustar módulos'
        updateProgress('modules', { status: 'failed', detail })
        toast.error(detail)
        setSubmitting(false)
        return
      }
    } else {
      updateProgress('modules', {
        status: 'done',
        detail: `preset (${selectedModules.size})`,
      })
    }

    // Step 3: create HQ branch
    updateProgress('branch', { status: 'running' })
    try {
      await platformApi.createBranch({
        organization_id: orgId as number,
        name: branch.name.trim(),
        address: branch.address.trim() || null,
        phone: branch.phone.trim() || null,
        branch_type: 'HQ',
        can_sell: branch.can_sell,
      })
      updateProgress('branch', { status: 'done' })
    } catch (err) {
      const detail = extractErr(err) || 'Error al crear sucursal'
      updateProgress('branch', { status: 'failed', detail })
      toast.error(detail)
      setSubmitting(false)
      return
    }

    // Step 4: assign admin
    updateProgress('admin', { status: 'running' })
    try {
      await platformApi.addAdmin(orgId as number, {
        username: admin.username.trim(),
        password: admin.password,
        full_name: admin.full_name.trim() || undefined,
        email: admin.email.trim() || undefined,
      })
      updateProgress('admin', { status: 'done' })
    } catch (err) {
      const detail = extractErr(err) || 'Error al crear admin'
      updateProgress('admin', { status: 'failed', detail })
      toast.error(detail)
      setSubmitting(false)
      return
    }

    toast.success(`Organización "${identity.name}" creada`)
    setSubmitting(false)
    onSuccess(orgId as number)
  }

  if (!open) return null

  // ── Step renderers ────────────────────────────────────────────────────────
  const renderIdentity = () => (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
      <div style={{ gridColumn: '1 / -1' }}>
        <label style={labelStyle}>Nombre comercial *</label>
        <input
          autoFocus
          value={identity.name}
          onChange={(e) => setIdentity({ ...identity, name: e.target.value })}
          style={inputStyle}
          placeholder="Ej. Café del Centro"
        />
        {!identityValid && identity.name.length > 0 && (
          <p style={errorTextStyle}>El nombre no puede estar vacío</p>
        )}
      </div>
      <div>
        <label style={labelStyle}>Razón social</label>
        <input
          value={identity.legal_name}
          onChange={(e) => setIdentity({ ...identity, legal_name: e.target.value })}
          style={inputStyle}
        />
      </div>
      <div>
        <label style={labelStyle}>RFC</label>
        <input
          value={identity.tax_id}
          onChange={(e) => setIdentity({ ...identity, tax_id: e.target.value })}
          style={inputStyle}
        />
      </div>
      <div>
        <label style={labelStyle}>Email</label>
        <input
          type="email"
          value={identity.email}
          onChange={(e) => setIdentity({ ...identity, email: e.target.value })}
          style={inputStyle}
        />
      </div>
      <div>
        <label style={labelStyle}>Teléfono</label>
        <input
          value={identity.phone}
          onChange={(e) => setIdentity({ ...identity, phone: e.target.value })}
          style={inputStyle}
        />
      </div>
      <div>
        <label style={labelStyle}>Industria</label>
        <select
          value={identity.industry_type}
          onChange={(e) => setIdentity({ ...identity, industry_type: e.target.value })}
          style={inputStyle}
        >
          {presets.length === 0 && <option value="ATLAS_POS">AtlasPOS</option>}
          {presets.map((p) => (
            <option key={p.industry_type} value={p.industry_type}>
              {p.display_name}
            </option>
          ))}
        </select>
      </div>
      <div>
        <label style={labelStyle}>Timezone</label>
        <input
          value={identity.timezone}
          onChange={(e) => setIdentity({ ...identity, timezone: e.target.value })}
          style={inputStyle}
        />
      </div>
    </div>
  )

  const renderModules = () => {
    // Union of preset + catalog so user can add/remove. Group visually.
    const presetKeys = new Set(activePreset?.modules ?? [])
    // Build a stable list from catalog. Fallback: preset modules even if not in catalog.
    const catalogMap = new Map(catalog.map((m) => [m.key, m]))
    activePreset?.modules.forEach((k) => {
      if (!catalogMap.has(k)) {
        catalogMap.set(k, {
          key: k,
          name: k,
          description: null,
          scope: 'ORG',
          status: 'ACTIVE',
        })
      }
    })
    const items = Array.from(catalogMap.values()).sort((a, b) => a.name.localeCompare(b.name))

    return (
      <div>
        <div
          style={{
            background: 'var(--p-surface-2)',
            border: '1px solid var(--p-border)',
            borderRadius: 8,
            padding: '10px 12px',
            marginBottom: 14,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 10,
          }}
        >
          <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: 12, color: 'var(--p-text)', fontWeight: 600 }}>
              Preset: {activePreset?.display_name || identity.industry_type}
            </div>
            <div style={{ fontSize: 11, color: 'var(--p-hint)', marginTop: 2 }}>
              Esta configuración se aplica automáticamente al crear la organización.
            </div>
          </div>
          {modulesTouched && (
            <button
              onClick={resetModulesToPreset}
              type="button"
              style={{
                background: 'transparent',
                color: 'var(--p-accent)',
                border: '1px solid var(--p-border)',
                padding: '5px 10px',
                borderRadius: 6,
                fontSize: 11,
                fontWeight: 600,
                cursor: 'pointer',
                fontFamily: 'var(--font-sans)',
                whiteSpace: 'nowrap',
              }}
            >
              <i className="fa-solid fa-rotate-left" style={{ marginRight: 5 }} />
              Restaurar preset
            </button>
          )}
        </div>

        {loadingMeta ? (
          <div style={{ color: 'var(--p-muted)', fontSize: 12, padding: 12 }}>
            <i className="fa-solid fa-spinner fa-spin" style={{ marginRight: 6 }} />
            Cargando módulos…
          </div>
        ) : items.length === 0 ? (
          <p style={{ color: 'var(--p-muted)', fontSize: 12 }}>
            No hay módulos en el catálogo.
          </p>
        ) : (
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: '1fr 1fr',
              gap: 6,
              maxHeight: 360,
              overflowY: 'auto',
              padding: 2,
            }}
          >
            {items.map((m) => {
              const on = selectedModules.has(m.key)
              const inPreset = presetKeys.has(m.key)
              return (
                <label
                  key={m.key}
                  style={{
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: 8,
                    padding: '8px 10px',
                    borderRadius: 6,
                    background: on ? 'var(--p-accent-soft)' : 'var(--p-surface-2)',
                    border: `1px solid ${on ? 'var(--p-accent)' : 'var(--p-border)'}`,
                    cursor: 'pointer',
                    fontSize: 12,
                    color: 'var(--p-text)',
                  }}
                >
                  <input
                    type="checkbox"
                    checked={on}
                    onChange={() => toggleModule(m.key)}
                    style={{ marginTop: 2, accentColor: 'var(--p-accent)' }}
                  />
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ fontWeight: 600, display: 'flex', gap: 6, alignItems: 'center' }}>
                      <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {m.name}
                      </span>
                      {inPreset && (
                        <span
                          style={{
                            fontSize: 9,
                            padding: '1px 5px',
                            borderRadius: 999,
                            background: 'var(--p-accent-soft)',
                            color: 'var(--p-accent)',
                            fontWeight: 600,
                            letterSpacing: '0.04em',
                            textTransform: 'uppercase',
                          }}
                        >
                          preset
                        </span>
                      )}
                    </div>
                    <div
                      style={{
                        fontSize: 10,
                        color: 'var(--p-hint)',
                        fontFamily: 'var(--font-mono)',
                        marginTop: 2,
                      }}
                    >
                      {m.key}
                    </div>
                  </div>
                </label>
              )
            })}
          </div>
        )}
      </div>
    )
  }

  const renderBranch = () => (
    <div>
      <p style={{ fontSize: 12, color: 'var(--p-muted)', margin: '0 0 14px' }}>
        Toda organización necesita al menos una sucursal. La primera será la matriz (HQ).
      </p>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <div style={{ gridColumn: '1 / -1' }}>
          <label style={labelStyle}>Nombre *</label>
          <input
            autoFocus
            value={branch.name}
            onChange={(e) => setBranch({ ...branch, name: e.target.value })}
            style={inputStyle}
          />
        </div>
        <div style={{ gridColumn: '1 / -1' }}>
          <label style={labelStyle}>Dirección</label>
          <input
            value={branch.address}
            onChange={(e) => setBranch({ ...branch, address: e.target.value })}
            style={inputStyle}
          />
        </div>
        <div>
          <label style={labelStyle}>Teléfono</label>
          <input
            value={branch.phone}
            onChange={(e) => setBranch({ ...branch, phone: e.target.value })}
            style={inputStyle}
          />
        </div>
        <div>
          <label style={labelStyle}>Tipo</label>
          <input value="HQ" readOnly style={{ ...inputStyle, opacity: 0.6 }} />
        </div>
        <div style={{ gridColumn: '1 / -1' }}>
          <label
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              fontSize: 12,
              color: 'var(--p-text)',
              cursor: 'pointer',
              marginTop: 4,
            }}
          >
            <input
              type="checkbox"
              checked={branch.can_sell}
              onChange={(e) => setBranch({ ...branch, can_sell: e.target.checked })}
              style={{ accentColor: 'var(--p-accent)' }}
            />
            Habilitar ventas en esta sucursal
          </label>
        </div>
      </div>
    </div>
  )

  const renderAdmin = () => (
    <div>
      <p style={{ fontSize: 12, color: 'var(--p-muted)', margin: '0 0 14px' }}>
        Este usuario será el dueño (OWNER) de la organización y podrá crear más usuarios.
      </p>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <div>
          <label style={labelStyle}>Usuario *</label>
          <input
            autoFocus
            value={admin.username}
            onChange={(e) => setAdmin({ ...admin, username: e.target.value })}
            style={inputStyle}
            autoComplete="off"
          />
          {adminUsernameErr && admin.username.length > 0 && (
            <p style={errorTextStyle}>{adminUsernameErr}</p>
          )}
        </div>
        <div>
          <label style={labelStyle}>Nombre completo *</label>
          <input
            value={admin.full_name}
            onChange={(e) => setAdmin({ ...admin, full_name: e.target.value })}
            style={inputStyle}
          />
          {adminFullNameErr && admin.full_name.length > 0 && (
            <p style={errorTextStyle}>{adminFullNameErr}</p>
          )}
        </div>
        <div style={{ gridColumn: '1 / -1' }}>
          <label style={labelStyle}>Email</label>
          <input
            type="email"
            value={admin.email}
            onChange={(e) => setAdmin({ ...admin, email: e.target.value })}
            style={inputStyle}
          />
        </div>
        <div style={{ gridColumn: '1 / -1' }}>
          <label style={labelStyle}>Contraseña * (mínimo 8 caracteres)</label>
          <input
            type="password"
            value={admin.password}
            onChange={(e) => setAdmin({ ...admin, password: e.target.value })}
            style={inputStyle}
            autoComplete="new-password"
          />
          {adminPasswordErr && admin.password.length > 0 && (
            <p style={errorTextStyle}>{adminPasswordErr}</p>
          )}
        </div>
        <div style={{ gridColumn: '1 / -1' }}>
          <label style={labelStyle}>Rol</label>
          <input value="ADMINISTRADOR (OWNER)" readOnly style={{ ...inputStyle, opacity: 0.6 }} />
          <p style={helpTextStyle}>Rol asignado por default al crear desde el wizard.</p>
        </div>
      </div>
    </div>
  )

  // ── Progress panel (step 4 during submit) ─────────────────────────────────
  const renderProgress = () => {
    if (progress.length === 0) return null
    return (
      <div
        style={{
          marginTop: 18,
          border: '1px solid var(--p-border)',
          borderRadius: 8,
          background: 'var(--p-surface-2)',
          padding: '10px 12px',
        }}
      >
        <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--p-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 6 }}>
          Progreso
        </div>
        {progress.map((p) => {
          const icon =
            p.status === 'done'
              ? 'fa-circle-check'
              : p.status === 'running'
              ? 'fa-circle-notch fa-spin'
              : p.status === 'failed'
              ? 'fa-circle-xmark'
              : 'fa-circle'
          const color =
            p.status === 'done'
              ? 'var(--p-accent)'
              : p.status === 'running'
              ? 'var(--p-text)'
              : p.status === 'failed'
              ? 'var(--p-danger)'
              : 'var(--p-hint)'
          return (
            <div
              key={p.key}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                fontSize: 12,
                color: 'var(--p-text)',
                padding: '4px 0',
              }}
            >
              <i className={`fa-solid ${icon}`} style={{ color, width: 14 }} />
              <span style={{ flex: 1 }}>{p.label}</span>
              {p.detail && (
                <span style={{ fontSize: 11, color: 'var(--p-hint)', fontFamily: 'var(--font-mono)' }}>
                  {p.detail}
                </span>
              )}
            </div>
          )
        })}
      </div>
    )
  }

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <>
      {/* Backdrop */}
      <div
        onClick={requestClose}
        style={{
          position: 'fixed',
          inset: 0,
          background: 'rgba(0,0,0,0.65)',
          backdropFilter: 'blur(3px)',
          zIndex: 1000,
        }}
      />

      {/* Drawer-style panel */}
      <div
        style={{
          position: 'fixed',
          top: 0,
          right: 0,
          height: '100vh',
          width: 560,
          maxWidth: '100vw',
          background: 'var(--p-surface)',
          borderLeft: '1px solid var(--p-border)',
          boxShadow: '-20px 0 60px rgba(0,0,0,0.45)',
          zIndex: 1001,
          display: 'flex',
          flexDirection: 'column',
          fontFamily: 'var(--font-sans)',
          color: 'var(--p-text)',
        }}
      >
        {/* Header */}
        <div
          style={{
            padding: '18px 24px 14px',
            borderBottom: '1px solid var(--p-border)',
            background: 'var(--p-surface)',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
            <div style={{ minWidth: 0 }}>
              <h2
                style={{
                  fontFamily: 'var(--font-display)',
                  fontSize: 20,
                  letterSpacing: '-0.02em',
                  fontWeight: 600,
                  color: 'var(--p-text)',
                  margin: 0,
                  lineHeight: 1.2,
                }}
              >
                Nueva organización
              </h2>
              <p style={{ margin: '4px 0 0', fontSize: 12, color: 'var(--p-muted)' }}>
                Crear organización, módulos, sucursal y primer admin en un solo flujo.
              </p>
            </div>
            <button
              onClick={requestClose}
              aria-label="Cerrar"
              disabled={submitting}
              style={{
                background: 'var(--p-surface-2)',
                border: '1px solid var(--p-border)',
                color: 'var(--p-muted)',
                width: 28,
                height: 28,
                borderRadius: 6,
                fontSize: 13,
                cursor: submitting ? 'not-allowed' : 'pointer',
                display: 'grid',
                placeItems: 'center',
                flexShrink: 0,
                opacity: submitting ? 0.4 : 1,
              }}
            >
              <i className="fa-solid fa-xmark" />
            </button>
          </div>
          <StepHeader step={step} />
        </div>

        {/* Body */}
        <div style={{ padding: '18px 24px', flex: 1, overflowY: 'auto' }}>
          <h3 style={sectionTitleStyle}>
            {step === 1
              ? 'Identidad'
              : step === 2
              ? 'Módulos habilitados'
              : step === 3
              ? 'Sucursal HQ'
              : 'Primer administrador'}
          </h3>
          <div style={{ marginTop: 14 }}>
            {step === 1 && renderIdentity()}
            {step === 2 && renderModules()}
            {step === 3 && renderBranch()}
            {step === 4 && renderAdmin()}
          </div>
          {step === 4 && renderProgress()}
        </div>

        {/* Footer */}
        <div
          style={{
            padding: '14px 24px',
            borderTop: '1px solid var(--p-border)',
            display: 'flex',
            gap: 10,
            justifyContent: 'space-between',
            alignItems: 'center',
            background: 'var(--p-sidebar)',
          }}
        >
          <button
            onClick={() => setStep((s) => (s > 1 ? ((s - 1) as StepKey) : s))}
            disabled={step === 1 || submitting}
            style={{
              background: 'var(--p-surface)',
              color: 'var(--p-text)',
              border: '1px solid var(--p-border)',
              padding: '8px 16px',
              borderRadius: 8,
              cursor: step === 1 || submitting ? 'not-allowed' : 'pointer',
              fontSize: 13,
              fontFamily: 'var(--font-sans)',
              fontWeight: 500,
              opacity: step === 1 || submitting ? 0.4 : 1,
            }}
          >
            <i className="fa-solid fa-arrow-left" style={{ marginRight: 6 }} />
            Atrás
          </button>

          <div style={{ display: 'flex', gap: 10 }}>
            <button
              onClick={requestClose}
              disabled={submitting}
              style={{
                background: 'transparent',
                color: 'var(--p-muted)',
                border: '1px solid var(--p-border)',
                padding: '8px 14px',
                borderRadius: 8,
                cursor: submitting ? 'not-allowed' : 'pointer',
                fontSize: 13,
                fontFamily: 'var(--font-sans)',
                fontWeight: 500,
                opacity: submitting ? 0.5 : 1,
              }}
            >
              Cancelar
            </button>
            {step < 4 ? (
              <button
                onClick={() => setStep((s) => (s + 1) as StepKey)}
                disabled={!currentStepValid || submitting}
                style={{
                  background: 'var(--p-accent)',
                  color: '#fff',
                  fontWeight: 600,
                  padding: '8px 20px',
                  border: '1px solid var(--p-accent)',
                  borderRadius: 8,
                  cursor: currentStepValid && !submitting ? 'pointer' : 'not-allowed',
                  opacity: currentStepValid && !submitting ? 1 : 0.5,
                  fontSize: 13,
                  fontFamily: 'var(--font-sans)',
                }}
              >
                Siguiente
                <i className="fa-solid fa-arrow-right" style={{ marginLeft: 6 }} />
              </button>
            ) : (
              <button
                onClick={handleSubmit}
                disabled={!currentStepValid || submitting}
                style={{
                  background: 'var(--p-accent)',
                  color: '#fff',
                  fontWeight: 600,
                  padding: '8px 20px',
                  border: '1px solid var(--p-accent)',
                  borderRadius: 8,
                  cursor: currentStepValid && !submitting ? 'pointer' : 'not-allowed',
                  opacity: currentStepValid && !submitting ? 1 : 0.5,
                  fontSize: 13,
                  fontFamily: 'var(--font-sans)',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 6,
                }}
              >
                {submitting && <i className="fa-solid fa-circle-notch fa-spin" style={{ fontSize: 11 }} />}
                {submitting ? 'Creando…' : 'Crear organización'}
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Confirm-close modal */}
      {confirmClose && (
        <div
          onClick={() => setConfirmClose(false)}
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.65)',
            backdropFilter: 'blur(3px)',
            zIndex: 1200,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontFamily: 'var(--font-sans)',
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              background: 'var(--p-surface)',
              border: '1px solid var(--p-border)',
              borderRadius: 14,
              padding: '22px 24px 20px',
              width: 400,
              maxWidth: '92vw',
              color: 'var(--p-text)',
              boxShadow: '0 20px 60px rgba(0,0,0,0.45)',
            }}
          >
            <h3
              style={{
                margin: 0,
                fontFamily: 'var(--font-display)',
                fontSize: 17,
                fontWeight: 600,
                letterSpacing: '-0.01em',
              }}
            >
              ¿Descartar cambios?
            </h3>
            <p style={{ color: 'var(--p-muted)', fontSize: 13, margin: '8px 0 18px', lineHeight: 1.5 }}>
              Se perderán los datos capturados en el wizard. Esta acción no puede deshacerse.
            </p>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
              <button
                onClick={() => setConfirmClose(false)}
                style={{
                  background: 'var(--p-surface-2)',
                  color: 'var(--p-text)',
                  border: '1px solid var(--p-border)',
                  padding: '8px 16px',
                  borderRadius: 8,
                  cursor: 'pointer',
                  fontSize: 13,
                  fontFamily: 'var(--font-sans)',
                  fontWeight: 500,
                }}
              >
                Seguir editando
              </button>
              <button
                onClick={forceClose}
                style={{
                  background: 'var(--p-danger)',
                  color: '#fff',
                  fontWeight: 600,
                  border: '1px solid var(--p-danger)',
                  padding: '8px 18px',
                  borderRadius: 8,
                  cursor: 'pointer',
                  fontSize: 13,
                  fontFamily: 'var(--font-sans)',
                }}
              >
                Descartar
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

// ─── Utils ───────────────────────────────────────────────────────────────────

function extractErr(err: unknown): string | null {
  if (typeof err === 'object' && err !== null) {
    const anyErr = err as { response?: { data?: { detail?: unknown } }; message?: string }
    const detail = anyErr.response?.data?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0] as { msg?: string }
      if (first?.msg) return first.msg
    }
    if (anyErr.message) return anyErr.message
  }
  return null
}
