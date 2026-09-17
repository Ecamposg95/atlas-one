import { useAuthStore } from '../../store/authStore'

/**
 * Aviso de que otra pestaña cambió la sesión bajo los pies de ésta.
 *
 * Importa porque en una terminal compartida (el caso de cualquier mostrador)
 * basta con que alguien abra otra pestaña y entre con su usuario para que
 * localStorage quede con SU token. El interceptor de `api/client.ts` lee
 * `atlas_token` de localStorage en cada request, así que desde ese momento
 * esta pestaña ya cobra como el otro usuario —en su sucursal y en su turno de
 * caja— mientras la pantalla sigue mostrando el nombre anterior, que vive en
 * el store en memoria.
 *
 * Avisa, no bloquea: cortar la pestaña en medio de una venta sería peor. Lo
 * que hace falta es que la cajera se entere y vuelva a entrar.
 */
export function ForeignSessionBanner() {
  const foreignSession = useAuthStore((s) => s.foreignSession)
  const dismiss = useAuthStore((s) => s.dismissForeignSession)
  const user = useAuthStore((s) => s.user)

  if (!foreignSession) return null

  return (
    <div
      role="alert"
      aria-live="assertive"
      className="flex items-center justify-between gap-3 px-4 py-2 text-xs font-semibold border-b"
      style={{
        background: 'var(--dax-warning-soft)',
        borderBottomColor: 'var(--dax-warning)',
        color: 'var(--dax-text)',
      }}
    >
      <span className="flex items-center gap-2 min-w-0">
        <i className="fa-solid fa-user-lock flex-shrink-0" style={{ color: 'var(--dax-warning)' }} />
        <span className="truncate">
          Alguien inició sesión con otro usuario en esta computadora. La pantalla
          sigue mostrando a <b>{user?.username ?? 'tu usuario'}</b>, pero las ventas
          que hagas ahora se registran con la sesión del otro usuario. Vuelve a
          entrar antes de seguir cobrando.
        </span>
      </span>
      <button
        onClick={dismiss}
        className="flex-shrink-0 px-2 py-1 rounded min-h-[32px]"
        style={{ background: 'var(--dax-elevated)' }}
        aria-label="Ocultar el aviso"
      >
        Entendido
      </button>
    </div>
  )
}
