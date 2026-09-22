import { useState, useEffect, useRef, FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { authApi } from '../api/auth'
import { useAuthStore } from '../store/authStore'
import { AtlasMark } from '../components/atlas-one'
import './login.css'

const HERO_MESSAGES = [
  { title: 'Ventas más fluidas.',    emphasis: 'Negocio ágil.' },
  { title: 'Control de inventario.', emphasis: 'Todo en orden.' },
  { title: 'Inteligencia en caja.',  emphasis: 'Cierre perfecto.' },
  { title: 'Toda tu operación.',     emphasis: 'En una sola plataforma.' },
]

const HERO_ROTATE_MS = 5200
const HERO_FADE_MS = 450

/* Arco hairline — eco estático del dial: ticks de instrumento y un segmento
   índigo en las 12, recortado por el borde derecho del viewport. */
function HairlineArc() {
  const ticks = []
  for (let deg = 0; deg < 360; deg += 5) {
    const major = deg % 30 === 0
    const rad = (deg * Math.PI) / 180
    const r1 = 430
    const r2 = major ? 412 : 421
    ticks.push(
      <line
        key={deg}
        x1={450 + Math.cos(rad) * r1}
        y1={450 + Math.sin(rad) * r1}
        x2={450 + Math.cos(rad) * r2}
        y2={450 + Math.sin(rad) * r2}
      />
    )
  }
  return (
    <svg className="arc" viewBox="0 0 900 900" aria-hidden="true">
      <g className="arc-spin">
        <circle cx="450" cy="450" r="392" fill="none" />
        <g className="arc-ticks">{ticks}</g>
      </g>
      {/* Segmento acento fijo en las 12 — no gira con el dial */}
      <path
        className="arc-accent"
        d="M 397.6 20.4 A 430 430 0 0 1 502.4 20.4"
        fill="none"
      />
    </svg>
  )
}

export function LoginPage() {
  const [isRevealed, setIsRevealed] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [isSuccess, setIsSuccess] = useState(false)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')

  // Rotación del titular con fundido
  const [heroIndex, setHeroIndex] = useState(0)
  const [heroFading, setHeroFading] = useState(false)

  const userInputRef = useRef<HTMLInputElement>(null)
  const formPanelRef = useRef<HTMLElement>(null)

  const navigate = useNavigate()
  const setAuth = useAuthStore((s) => s.setAuth)
  const setBranch = useAuthStore((s) => s.setBranch)

  useEffect(() => {
    const id = setInterval(() => {
      setHeroFading(true)
      setTimeout(() => {
        setHeroIndex((i) => (i + 1) % HERO_MESSAGES.length)
        setHeroFading(false)
      }, HERO_FADE_MS)
    }, HERO_ROTATE_MS)
    return () => clearInterval(id)
  }, [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isRevealed && !isSuccess) setIsRevealed(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [isRevealed, isSuccess])

  const handleReveal = () => {
    setIsRevealed(true)
    setTimeout(() => userInputRef.current?.focus(), 450)
  }

  // Clic fuera del formulario → regresa al hero
  const handleSceneClick = (e: React.MouseEvent) => {
    if (!isRevealed || isSuccess) return
    if (formPanelRef.current && !formPanelRef.current.contains(e.target as Node)) {
      setIsRevealed(false)
    }
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setIsLoading(true)
    setError('')
    try {
      const data = await authApi.login(username, password)
      setAuth(data.user, data.access_token, data.organization)
      // Sin sucursal en la respuesta hay que limpiar la que haya quedado en
      // localStorage de una sesión anterior (ver authStore#setAuth).
      setBranch(data.branch ?? null)
      setIsSuccess(true)
      setTimeout(() => {
        if (data.user.platform_role === 'SUPERADMIN') { navigate('/platform/metrics'); return }
        const role = data.user.role
        if (['VENDEDOR', 'SOPORTE_OPERATIVO'].includes(role)) navigate('/mobile/dashboard')
        else if (['CAJERO', 'GERENTE'].includes(role)) navigate('/atlas-pos')
        else if (role === 'CLIENTE') navigate('/portal')
        // Admin/Dueño → raíz: RoleHomeRedirect enruta por preset (gastro → /home
        // con el Home del día; sin preset Atlas One → /hq/operations).
        else navigate('/')
      }, 600)
    } catch {
      setError('Usuario o contraseña incorrectos. Intenta de nuevo.')
      setIsLoading(false)
    }
  }

  const msg = HERO_MESSAGES[heroIndex]
  const sceneClass = [
    'login-scene',
    isRevealed && 'is-revealed',
    isSuccess && 'is-success',
  ].filter(Boolean).join(' ')

  return (
    <div className={sceneClass} onClick={handleSceneClick}>
      {/* Auroras de fondo — deriva lenta detrás de todo */}
      <div className="aurora-field" aria-hidden="true">
        <div className="aurora au-1" />
        <div className="aurora au-2" />
        <div className="aurora au-3" />
      </div>
      <HairlineArc />

      <header className="scene-top">
        <div className="scene-brand">
          <AtlasMark size={26} color="#EDEDF8" accent="#6C6CFF" />
          <span className="scene-brand-name">Atlas One</span>
        </div>
        <span className="scene-tag">Suite comercial · v2.5</span>
      </header>

      {/* ── Paso 1: hero ── */}
      <section className="hero">
        <p className="hero-eyebrow">Tu operación, en un solo lugar</p>
        <h1 className={`hero-headline${heroFading ? ' is-fading' : ''}`}>
          <span className="hh-title">{msg.title}</span>
          <em className="hh-emphasis">{msg.emphasis}</em>
        </h1>
        <p className="hero-description">
          Ventas, inventario y caja de tu negocio,
          conectados en una sola plataforma.
        </p>
        <button type="button" className="reveal-cta" onClick={handleReveal}>
          Iniciar sesión
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <line x1="5" y1="12" x2="19" y2="12" /><polyline points="12 5 19 12 12 19" />
          </svg>
        </button>
      </section>

      {/* ── Paso 2: formulario ── */}
      <main className="panel" ref={formPanelRef} onClick={(e) => e.stopPropagation()}>
        <h2 className="panel-title">Bienvenido de nuevo</h2>
        <p className="panel-subtitle">Entra con tu cuenta de Atlas One.</p>

        <form className="login-form" onSubmit={handleSubmit}>
          <div className="field">
            <label htmlFor="login-user">Correo o usuario</label>
            <input
              id="login-user"
              ref={userInputRef}
              type="text"
              placeholder="tucorreo@atlasone.com.mx"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              required
            />
          </div>
          <div className="field">
            <label htmlFor="login-pass">Contraseña</label>
            <div className="field-password">
              <input
                id="login-pass"
                type={showPassword ? 'text' : 'password'}
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                required
              />
              <button
                type="button"
                className="pw-toggle"
                onClick={() => setShowPassword((v) => !v)}
                aria-label={showPassword ? 'Ocultar contraseña' : 'Mostrar contraseña'}
              >
                {showPassword ? (
                  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
                    <line x1="1" y1="1" x2="23" y2="23" />
                  </svg>
                ) : (
                  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8Z" />
                    <circle cx="12" cy="12" r="3" />
                  </svg>
                )}
              </button>
            </div>
          </div>

          {error && <p className="form-error" role="alert">{error}</p>}

          <button type="submit" className="submit-btn" disabled={isLoading}>
            {isLoading ? 'Verificando…' : 'Entrar'}
          </button>
        </form>

        <p className="panel-footer">
          ¿Problemas para entrar? Pide ayuda al administrador de tu negocio.
        </p>
      </main>

      <footer className="scene-foot">
        <span>atlastech.mx</span>
        <span>© {new Date().getFullYear()} Atlas Tech</span>
      </footer>
    </div>
  )
}
