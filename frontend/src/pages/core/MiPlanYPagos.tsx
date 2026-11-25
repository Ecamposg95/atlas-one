import { useEffect, useState } from 'react'
import {
  suscripcionesApi, ETIQUETA_CARGO, ETIQUETA_ESTADO, ETIQUETA_METODO, fechaCorta, num,
  type Cargo, type EstadoCargo, type EstadoSuscripcion, type MiSuscripcion,
} from '../../api/suscripciones'
import { useEsTelefono } from '../../hooks/useIsMobile'
import { formatCurrency } from '../../utils/currency'
import { Badge } from '../../components/ui/Badge'
import { DaxCard } from '../../components/ui/DaxCard'
import { ListaTarjetas } from '../../components/ui/ListaTarjetas'
import { Spinner } from '../../components/ui/Spinner'
import { TarjetaFila } from '../../components/ui/TarjetaFila'

/**
 * Pestaña "Mi plan y pagos" de `/configuracion?tab=plan` (administrador y
 * dueño). Solo lectura: lo que Atlas le cobra a la tienda, su uso contra los
 * topes del plan y el historial de cargos y pagos que registra plataforma.
 * No es CRM Cobranza (lo que la tienda le fía a sus clientes).
 */
type Variante = 'green' | 'red' | 'yellow' | 'blue' | 'slate'

const TONO_ESTADO: Record<EstadoSuscripcion, Variante> = {
  al_corriente: 'green', por_vencer: 'yellow', vencida: 'red', suspendida: 'red', cortesia: 'blue',
}
const TONO_CARGO: Record<EstadoCargo, Variante> = { pendiente: 'yellow', pagado: 'green', cancelado: 'slate' }

const AVISO: Partial<Record<EstadoSuscripcion, string>> = {
  por_vencer: 'Tu renovación está cerca. Si ya pagaste, en cuanto lo registremos lo verás aquí.',
  vencida: 'Tienes un pago vencido. Si ya lo hiciste, envíanos tu comprobante para registrarlo.',
  suspendida: 'Tu suscripción está marcada como suspendida. Escríbenos para regularizarla.',
  cortesia: 'Tu plan es de cortesía: no genera cargos.',
}

function Uso({ etiqueta, usados, tope }: { etiqueta: string; usados: number; tope: number | null }) {
  const lleno = tope != null && usados >= tope
  return (
    <div>
      <p className="text-xs text-dax-muted">{etiqueta}</p>
      <p className={`text-lg font-black tabular-nums ${lleno ? 'text-dax-warning' : 'text-dax-text'}`}>
        {usados} <span className="text-sm font-semibold text-dax-muted">de {tope ?? 'sin tope'}</span>
      </p>
    </div>
  )
}

function Pagos({ cargo }: { cargo: Cargo }) {
  if (cargo.pagos.length === 0) return <span className="text-dax-faint">Sin pagos</span>
  return (
    <ul className="space-y-0.5">
      {cargo.pagos.map((p) => (
        <li key={p.id} className="text-xs text-dax-muted">
          {fechaCorta(p.fecha_pago)} · {ETIQUETA_METODO[p.metodo] ?? p.metodo}
          {p.referencia ? ` · ${p.referencia}` : ''} · <span className="text-dax-text font-semibold">{formatCurrency(num(p.importe))}</span>
        </li>
      ))}
    </ul>
  )
}

const estadoCargo = (c: Cargo) => (
  <Badge variant={c.vencido ? 'red' : TONO_CARGO[c.estado]}>{c.vencido ? 'Vencido' : ETIQUETA_CARGO[c.estado]}</Badge>
)
const periodo = (c: Cargo) => `${fechaCorta(c.periodo_desde)} – ${fechaCorta(c.periodo_hasta)}`

export function MiPlanYPagos() {
  const esTelefono = useEsTelefono()
  const [datos, setDatos] = useState<MiSuscripcion | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let vivo = true
    suscripcionesApi.mia()
      .then((d) => { if (vivo) setDatos(d) })
      .catch((e) => { if (vivo) setError(e?.response?.data?.detail || 'No se pudo cargar tu plan.') })
    return () => { vivo = false }
  }, [])

  if (error) return <DaxCard><p className="text-sm text-dax-danger" role="alert">{error}</p></DaxCard>
  if (!datos) return <Spinner text="Cargando tu plan…" />

  const { plan, uso, suscripcion: sus, cargos } = datos
  const porPeriodo = sus?.periodicidad === 'anual' ? 'al año' : 'al mes'

  return (
    <div className="space-y-4" data-testid="mi-plan-y-pagos">
      <DaxCard>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs text-dax-muted">Tu plan</p>
            <p className="text-2xl font-black text-dax-text">{plan.nombre}</p>
          </div>
          {sus && <Badge variant={TONO_ESTADO[sus.estado]}>{ETIQUETA_ESTADO[sus.estado]}</Badge>}
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mt-4">
          <div>
            <p className="text-xs text-dax-muted">Precio</p>
            <p className="text-lg font-black tabular-nums text-dax-text">
              {formatCurrency(num(sus ? sus.precio_mxn : plan.precio_lista_mxn))}{' '}
              <span className="text-sm font-semibold text-dax-muted">{porPeriodo}</span>
            </p>
          </div>
          <div>
            <p className="text-xs text-dax-muted">Próxima renovación</p>
            <p className="text-lg font-black text-dax-text">{sus ? fechaCorta(sus.proxima_renovacion) : '—'}</p>
          </div>
          <Uso etiqueta="Usuarios activos" usados={uso.usuarios_activos} tope={plan.max_usuarios} />
          <Uso etiqueta="Sucursales que venden" usados={uso.sucursales_venta} tope={plan.max_sucursales_venta} />
        </div>

        {!sus && (
          <p className="text-sm text-dax-muted mt-4">
            Todavía no hay una suscripción registrada para tu tienda. Cuando la demos de alta verás aquí tu renovación y tus pagos.
          </p>
        )}
        {sus && AVISO[sus.estado] && (
          <p className={`text-sm mt-4 ${sus.estado === 'vencida' || sus.estado === 'suspendida' ? 'text-dax-danger' : 'text-dax-muted'}`}>
            {AVISO[sus.estado]}
          </p>
        )}
        <p className="text-xs text-dax-faint mt-3">Para cambiar de plan o aclarar un pago, escríbenos; aquí solo se consulta.</p>
      </DaxCard>

      {sus && (sus.rfc || sus.razon_social || sus.correo_facturacion) && (
        <DaxCard>
          <p className="text-sm font-black text-dax-text mb-2">Datos de facturación</p>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-sm">
            <div><p className="text-xs text-dax-muted">RFC</p><p className="text-dax-text">{sus.rfc || '—'}</p></div>
            <div><p className="text-xs text-dax-muted">Razón social</p><p className="text-dax-text">{sus.razon_social || '—'}</p></div>
            <div><p className="text-xs text-dax-muted">Correo</p><p className="text-dax-text break-words">{sus.correo_facturacion || '—'}</p></div>
          </div>
        </DaxCard>
      )}

      <div>
        <p className="text-sm font-black text-dax-text mb-2">Historial de cargos y pagos</p>
        {esTelefono ? (
          <ListaTarjetas vacio={cargos.length === 0} textoVacio="Aún no hay cargos.">
            {cargos.map((c) => (
              <TarjetaFila
                key={c.id}
                titulo={periodo(c)}
                subtitulo={`Vence ${fechaCorta(c.vence_el)}`}
                importe={formatCurrency(num(c.importe))}
                estado={estadoCargo(c)}
                datos={[
                  { etiqueta: 'Pagado', valor: formatCurrency(num(c.pagado)) },
                  { etiqueta: 'Saldo', valor: formatCurrency(num(c.saldo)) },
                  { etiqueta: 'Pagos', valor: <Pagos cargo={c} /> },
                ]}
              />
            ))}
          </ListaTarjetas>
        ) : cargos.length === 0 ? (
          <DaxCard><p className="text-sm text-dax-muted text-center">Aún no hay cargos.</p></DaxCard>
        ) : (
          <DaxCard padding={false} className="overflow-x-auto">
            <table className="dax-table">
              <thead>
                <tr>
                  <th>Periodo</th><th>Vence</th><th className="text-right">Importe</th>
                  <th className="text-right">Pagado</th><th className="text-right">Saldo</th><th>Estado</th><th>Pagos</th>
                </tr>
              </thead>
              <tbody>
                {cargos.map((c) => (
                  <tr key={c.id}>
                    <td className="whitespace-nowrap">{periodo(c)}</td>
                    <td className="whitespace-nowrap">{fechaCorta(c.vence_el)}</td>
                    <td className="text-right tabular-nums">{formatCurrency(num(c.importe))}</td>
                    <td className="text-right tabular-nums">{formatCurrency(num(c.pagado))}</td>
                    <td className="text-right tabular-nums">{formatCurrency(num(c.saldo))}</td>
                    <td>{estadoCargo(c)}</td>
                    <td><Pagos cargo={c} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </DaxCard>
        )}
      </div>
    </div>
  )
}
