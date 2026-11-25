import { useState, useEffect, useRef, FormEvent, MouseEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { authApi } from '../api/auth'
import { useAuthStore } from '../store/authStore'
import './login.css'

/* Inter solo hace falta aquí: se inyecta al montar el login para no
   sumarla a index.html (la ruta crítica del POS no la descarga). */
const FUENTE_LOGIN = 'https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500&display=swap'

function useFuenteLogin() {
  useEffect(() => {
    if (document.querySelector(`link[href="${FUENTE_LOGIN}"]`)) return
    const link = document.createElement('link')
    link.rel = 'stylesheet'
    link.href = FUENTE_LOGIN
    document.head.appendChild(link)
  }, [])
}

/* Marca de Atlas Tech (la "A" en el círculo). Vive aquí porque solo el login
   la usa; el resto de la app sigue con AtlasMark. */
function MarcaAtlas() {
  return (
    <svg viewBox="0 0 375.71 340" fill="currentColor" aria-hidden="true">
      <polygon points="252.36 236.3 195.47 110.84 140.66 236.21 98.8 235.8 174.88 71.93 216.92 71.85 295.23 235.73 252.36 236.3" />
      <polygon points="235.1 264.18 156.85 264.18 169.04 236.37 222.59 236.45 235.1 264.18" />
      <path d="M322.77,271.46c-5.63,7.02-12.31,13.43-18.68,19.74-31,30.74-75.65,46.25-119.14,44.73-92.04-3.23-164.14-80-162.22-171.68C24.29,89.2,76.26,23.61,149.63,4.95,164.96,1.05,180.47-.39,196.78.09c49.74,1.45,95.91,25.54,126.33,64.35,47.43,60.52,48.14,146.58-.34,207.02ZM285.77,268.38c61.55-58.4,56.66-157.12-9.84-209.36-54.27-42.64-132.41-38.36-181.82,10.11-54.43,53.4-55.5,140.38-2.56,195.07,52.52,54.26,139.28,56.32,194.22,4.19Z" />
    </svg>
  )
}

/* Atardecer de fondo: cielo, tres colinas, la sombra de un árbol y grano. Decorativo. */
function Paisaje() {
  return (
    <div aria-hidden="true">
      <div className="login-cielo" />
      <svg className="login-colinas" viewBox="0 0 1440 600" preserveAspectRatio="none">
        <defs>
          <linearGradient id="login-colina-1" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#B8431A" /><stop offset=".5" stopColor="#5A1D0C" /><stop offset="1" stopColor="#1A0B07" />
          </linearGradient>
          <linearGradient id="login-colina-2" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#6B260F" /><stop offset=".45" stopColor="#2A120A" /><stop offset="1" stopColor="#0E0806" />
          </linearGradient>
          <linearGradient id="login-colina-3" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#2B170D" /><stop offset=".5" stopColor="#0E0907" /><stop offset="1" stopColor="#050505" />
          </linearGradient>
        </defs>
        <path fill="url(#login-colina-1)" d="M0 250 C240 170 480 240 720 215 S1200 90 1440 170 V600 H0Z" />
        <path fill="url(#login-colina-2)" d="M0 380 C300 300 600 410 900 345 S1300 300 1440 350 V600 H0Z" />
        <path fill="url(#login-colina-3)" d="M0 500 C260 430 520 525 820 480 S1250 450 1440 500 V600 H0Z" />
      </svg>
      <div className="login-arbol" />
      <div className="login-grano" />
    </div>
  )
}

/* Terminal encendida sobre la colina: firma visual del login, decorativa. */
function TerminalEncendida() {
  return (
    <div aria-hidden="true">
      <div className="login-loma" />
      <div className="login-sombra" />
      <div className="login-terminal">
        <div className="login-terminal__carcasa">
          <div className="login-terminal__pantalla"><MarcaAtlas />Atlas <span>ONE</span></div>
          <div className="login-terminal__ranura" />
        </div>
      </div>
    </div>
  )
}

export function LoginPage() {
  const [isLoading, setIsLoading] = useState(false)
  const [isSuccess, setIsSuccess] = useState(false)
  // Portada primero: el formulario entra al oprimir «Iniciar sesión».
  const [isRevealed, setIsRevealed] = useState(false)
  const panelRef = useRef<HTMLDivElement>(null)
  const usuarioRef = useRef<HTMLInputElement>(null)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')

  const navigate = useNavigate()
  const setAuth = useAuthStore((s) => s.setAuth)
  const setBranch = useAuthStore((s) => s.setBranch)
  useFuenteLogin()

  const revelar = () => {
    setIsRevealed(true)
    // El foco entra cuando la tarjeta ya viene llegando (preventScroll: sigue en transición).
    setTimeout(() => usuarioRef.current?.focus({ preventScroll: true }), 350)
  }

  // Clic fuera de la tarjeta: de vuelta a la portada (salvo a media entrada).
  const alTocarFondo = (e: MouseEvent) => {
    if (!isRevealed || isLoading || isSuccess) return
    if (panelRef.current && !panelRef.current.contains(e.target as Node)) setIsRevealed(false)
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
        if (role === 'SOPORTE_OPERATIVO') navigate('/mobile/dashboard')
        else if (['CAJERO', 'GERENTE', 'VENDEDOR'].includes(role)) navigate('/atlas-pos')
        else if (role === 'CLIENTE') navigate('/portal')
        // Admin/Dueño → raíz: RoleHomeRedirect enruta por preset (gastro → /home
        // con el Home del día; sin preset Atlas One → /hq/operations).
        else navigate('/')
      }, 750)
    } catch {
      setError('Usuario o contraseña incorrectos. Intenta de nuevo.')
      setIsLoading(false)
    }
  }

  return (
    <div className={`login${isRevealed ? ' is-revealed' : ''}${isSuccess ? ' is-success' : ''}`} onClick={alTocarFondo}>
      <Paisaje />
      {/* Al entrar amanece: la luz del horizonte crece mientras el panel se va. Decorativo. */}
      <div className="login-amanecer" aria-hidden="true" />

      {/* Portada: lo primero que se ve. Al revelar se desvanece hacia la izquierda. */}
      <div className="login-portada" {...(isRevealed ? { inert: '' } : {})}>
        <div className="login-portada__marca">
          <MarcaAtlas />
          Atlas <span>ONE</span>
        </div>
        <p className="login-portada__cejilla">Punto de venta · Inventario · Caja</p>
        <p className="login-portada__titular">
          Tu negocio, <em>al día.</em>
        </p>
        <p className="login-portada__bajada">
          Cobra rápido, lleva tu inventario y cierra el día con las cuentas claras.
        </p>
        <button type="button" className="login-portada__boton" onClick={(e) => { e.stopPropagation(); revelar() }} autoFocus>
          Iniciar sesión
        </button>
      </div>

      <div className="login-panel" ref={panelRef} {...(isRevealed ? {} : { inert: '' })}>
        {/* Va primero en el DOM (lleva el h1) y a la derecha en escritorio (grid-area). */}
        <section className="login-vista">
          <TerminalEncendida />
          <div className="login-lema">
            <p className="login-cejilla">Software de operación</p>
            <h1 className="login-titular">
              Un punto de venta por <em>cada giro.</em>
            </h1>
          </div>
        </section>

        <main className="login-columna">
          <div className="login-marca">
            <MarcaAtlas />
            Atlas <span>ONE</span>
          </div>

          <div className="login-acceso">
            <div>
              <h2 className="login-titulo">Entra a tu tienda</h2>
              <p className="login-bajada">Atlas ONE llega configurado para tu negocio.</p>
            </div>

            <form className="login-form" onSubmit={handleSubmit}>
              <div className="login-campo">
                <label htmlFor="login-user">Usuario</label>
                <input
                  id="login-user"
                  ref={usuarioRef}
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  autoComplete="username"
                  autoCapitalize="none"
                  spellCheck={false}
                  placeholder="Tu usuario"
                  required
                />
              </div>
              <div className="login-campo">
                <label htmlFor="login-pass">Contraseña</label>
                <div className="login-campo__clave">
                  <input
                    id="login-pass"
                    type={showPassword ? 'text' : 'password'}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    autoComplete="current-password"
                    placeholder="Tu contraseña"
                    required
                  />
                  <button
                    type="button"
                    className="login-ojo"
                    onClick={() => setShowPassword((v) => !v)}
                    aria-label={showPassword ? 'Ocultar contraseña' : 'Mostrar contraseña'}
                  >
                    {showPassword ? (
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                        <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
                        <line x1="1" y1="1" x2="23" y2="23" />
                      </svg>
                    ) : (
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8Z" />
                        <circle cx="12" cy="12" r="3" />
                      </svg>
                    )}
                  </button>
                </div>
              </div>

              {error && <p className="login-error" role="alert">{error}</p>}

              <button
                type="submit"
                className={`login-boton${isSuccess ? ' is-listo' : ''}`}
                disabled={isLoading}
                aria-busy={isLoading && !isSuccess}
              >
                {isLoading && !isSuccess && <span className="login-boton__giro" aria-hidden="true" />}
                {isSuccess && (
                  <svg className="login-boton__palomita" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <path d="M5 12.5l4.5 4.5L19 7.5" />
                  </svg>
                )}
                {isSuccess ? 'Bienvenido' : isLoading ? 'Verificando…' : 'Entrar'}
              </button>
            </form>

            <p className="login-ayuda">
              ¿Problemas para entrar? Pide ayuda al administrador de tu negocio.
            </p>
          </div>

          <footer className="login-pie">
            <span>Atlas ONE — Atlas Tech</span>
            <a href="https://atlasone.com.mx">Conoce Atlas ONE ↗</a>
          </footer>
        </main>
      </div>
    </div>
  )
}
