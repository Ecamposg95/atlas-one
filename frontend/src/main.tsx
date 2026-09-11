import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import './styles/atlas-one.css'
import './styles/motion.css'
import App from './App'
import { ConfirmDialogProvider } from './components/ui/ConfirmDialog'
import { applyMotionFlag } from './theme/motion'

// ── Stale chunk recovery ────────────────────────────────────────────────────
// Cuando se redeploya el frontend, los chunks viejos cacheados en el browser
// dejan de existir en el servidor. El lazy import lanza un TypeError de
// "Failed to fetch dynamically imported module". Auto-recargamos UNA vez
// (evita loop) para forzar al browser a pedir el index.html nuevo con los
// hashes actualizados.
const STALE_CHUNK_KEY = 'atlas:stale-chunk-reloaded'

const handleStaleChunk = (err: unknown) => {
  const msg = err instanceof Error ? err.message : String(err)
  if (
    /Failed to fetch dynamically imported module/i.test(msg) ||
    /Importing a module script failed/i.test(msg) ||
    /ChunkLoadError/i.test(msg)
  ) {
    if (sessionStorage.getItem(STALE_CHUNK_KEY)) return // ya recargamos antes — no loop
    sessionStorage.setItem(STALE_CHUNK_KEY, '1')
    window.location.reload()
  }
}

window.addEventListener('error', (e) => handleStaleChunk(e.error ?? e.message))
window.addEventListener('unhandledrejection', (e) => handleStaleChunk(e.reason))

// Limpiamos el flag tras 30s de uso normal — si el usuario sigue OK, el próximo
// stale chunk sí provocará reload (no quedamos baneados de por vida).
setTimeout(() => sessionStorage.removeItem(STALE_CHUNK_KEY), 30_000)

// Bandera local `atlas_ui_motion=0`: apaga las animaciones sin deploy.
applyMotionFlag(document.documentElement)

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ConfirmDialogProvider>
      <App />
    </ConfirmDialogProvider>
  </StrictMode>,
)
