import { useState, useEffect, FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { authApi } from '../api/auth'
import { useAuthStore } from '../store/authStore'
import { AtlasMark } from '../components/atlas-one'
import { useEsTelefono } from '../hooks/useIsMobile'
import './login.css'

/* Archivo Black solo hace falta aquí: se inyecta al montar el login para no
   sumarla a index.html (la ruta crítica del POS no la descarga). */
const FUENTE_TITULOS = 'https://fonts.googleapis.com/css2?family=Archivo+Black&display=swap'

function useFuenteTitulos() {
  useEffect(() => {
    if (document.querySelector(`link[href="${FUENTE_TITULOS}"]`)) return
    const link = document.createElement('link')
    link.rel = 'stylesheet'
    link.href = FUENTE_TITULOS
    document.head.appendChild(link)
  }, [])
}

/* Ticket térmico de ejemplo: firma visual del sitio, decorativo. */
function TicketDeEjemplo() {
  return (
    <div className="login-ticket" aria-hidden="true">
      <div className="login-ticket__papel">
        <p className="login-ticket__marca">ATLAS ONE</p>
        <p className="login-ticket__sub">TICKET DE VENTA</p>
        <div className="login-ticket__renglon"><span>FOLIO</span><span>A-1024</span></div>
        <div className="login-ticket__renglon"><span>CAJA</span><span>Abierta</span></div>
        <hr className="login-ticket__regla" />
        <div className="login-ticket__partida"><b>2</b><span>Playera básica</span><span>$398.00</span></div>
        <div className="login-ticket__partida"><b>1</b><span>Gorra</span><span>$249.00</span></div>
        <div className="login-ticket__partida"><b>1</b><span>Calcetines</span><span>$89.00</span></div>
        <hr className="login-ticket__regla" />
        <div className="login-ticket__total"><span>TOTAL</span><span>$736.00</span></div>
        <p className="login-ticket__gracias">Gracias por su compra</p>
        <div className="login-ticket__codigo" />
        <p className="login-ticket__gracias">atlasone.com.mx</p>
      </div>
    </div>
  )
}

export function LoginPage() {
  const [isLoading, setIsLoading] = useState(false)
  const [isSuccess, setIsSuccess] = useState(false)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')

  const navigate = useNavigate()
  const setAuth = useAuthStore((s) => s.setAuth)
  const setBranch = useAuthStore((s) => s.setBranch)
  const esTelefono = useEsTelefono()
  useFuenteTitulos()

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

  return (
    <div className={`login${isSuccess ? ' is-success' : ''}`}>
      <header className="login-barra">
        <div className="login-marca">
          <AtlasMark size={24} color="currentColor" />
          <span>ATLAS<span className="login-marca__punto">·</span>ONE</span>
        </div>
      </header>

      <div className="login-reja">
        <section className="login-saludo">
          <p className="login-cejilla">Software de operación</p>
          <h1 className="login-titular">
            Un punto de venta por <em>cada giro.</em>
          </h1>
          {!esTelefono && (
            <>
              <p className="login-entrada">Atlas ONE llega configurado para tu negocio.</p>
              <a className="login-enlace" href="https://atlasone.com.mx">Conoce Atlas ONE →</a>
            </>
          )}
        </section>

        <div className="login-lado">
          {!esTelefono && <TicketDeEjemplo />}
          <main className="login-tarjeta">
            <h2 className="login-tarjeta__titulo">Entra a tu tienda</h2>

            <form className="login-form" onSubmit={handleSubmit}>
              <div className="login-campo">
                <label htmlFor="login-user">Usuario</label>
                <input
                  id="login-user"
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  autoComplete="username"
                  autoCapitalize="none"
                  spellCheck={false}
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

              <button type="submit" className="login-boton" disabled={isLoading}>
                {isLoading ? 'Verificando…' : 'Entrar'}
              </button>
            </form>

            <p className="login-ayuda">
              ¿Problemas para entrar? Pide ayuda al administrador de tu negocio.
            </p>
          </main>
        </div>
      </div>

      <footer className="login-pie">Atlas ONE — Atlas Tech</footer>
    </div>
  )
}
