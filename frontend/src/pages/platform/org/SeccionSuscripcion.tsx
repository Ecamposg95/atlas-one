import { useEffect, useState } from 'react'
import {
  suscripcionesApi, ESTADOS, ETIQUETA_CARGO, ETIQUETA_ESTADO, ETIQUETA_METODO, METODOS, fechaCorta, num,
  type Cargo, type EstadoSuscripcion, type MetodoPago, type Periodicidad, type SuscripcionDetalle,
  type SuscripcionEntrada,
} from '../../../api/suscripciones'
import type { Plan } from '../../../api/platform'
import { useAuthStore } from '../../../store/authStore'
import { toast } from '../../../store/toastStore'
import { formatCurrency } from '../../../utils/currency'
import { Modal } from '../../../components/ui/Modal'

/**
 * Sección "Suscripción" de la ficha de la organización (plataforma): lo que
 * Atlas le cobra a la tienda. Alta/edición, cargos por periodo y registro
 * manual de pagos. Escribe solo SUPERADMIN; SUPPORT la ve en solo lectura.
 * `suspendida` es informativa: no bloquea ningún acceso.
 */
const COLOR_ESTADO: Record<EstadoSuscripcion, string> = {
  al_corriente: 'var(--p-success)',
  por_vencer: 'var(--p-warning)',
  vencida: 'var(--p-danger)',
  suspendida: 'var(--p-danger)',
  cortesia: 'var(--p-accent)',
}

export function PildoraEstado({ estado }: { estado: EstadoSuscripcion }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 11, fontWeight: 600, padding: '3px 8px',
      borderRadius: 999, border: '1px solid var(--p-border)', background: 'var(--p-surface-2)',
      color: COLOR_ESTADO[estado] ?? 'var(--p-muted)', whiteSpace: 'nowrap',
    }}>
      <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'currentColor' }} />
      {ETIQUETA_ESTADO[estado] ?? estado}
    </span>
  )
}

const tarjeta: React.CSSProperties = {
  background: 'var(--p-surface)', border: '1px solid var(--p-border)', borderRadius: 6, padding: '1rem 1.25rem',
}
const titulo: React.CSSProperties = {
  fontSize: '0.7rem', color: 'var(--p-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', fontWeight: 600, margin: 0,
}
const boton: React.CSSProperties = {
  background: 'var(--p-surface-2)', color: 'var(--p-text)', border: '1px solid var(--p-border)', padding: '6px 12px',
  borderRadius: 4, fontSize: 12, fontWeight: 600, cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 6,
}
const botonPrincipal: React.CSSProperties = {
  ...boton, background: 'var(--p-teal)', color: 'var(--dax-on-accent)', border: 'none',
}
const celdaCabeza: React.CSSProperties = {
  padding: '8px 10px', textAlign: 'left', color: 'var(--p-muted)', fontSize: '0.7rem', textTransform: 'uppercase',
  letterSpacing: '0.08em', fontWeight: 600, borderBottom: '1px solid var(--p-border)', whiteSpace: 'nowrap',
}
const celda: React.CSSProperties = {
  padding: '8px 10px', borderBottom: '1px solid var(--p-border)', color: 'var(--p-text)', fontSize: 13, verticalAlign: 'top',
}
const dato = (etiqueta: string, valor: React.ReactNode) => (
  <div key={etiqueta} style={{ minWidth: 0 }}>
    <div style={{ fontSize: 11, color: 'var(--p-muted)' }}>{etiqueta}</div>
    <div style={{ fontSize: 13, color: 'var(--p-text)', overflowWrap: 'anywhere' }}>{valor}</div>
  </div>
)

const hoyLocal = () => {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
const detalleError = (e: any, respaldo: string) => {
  const d = e?.response?.data?.detail
  if (typeof d === 'string') return d
  if (Array.isArray(d) && d[0]?.msg) return String(d[0].msg)
  return respaldo
}

interface Formulario {
  plan: string; precio_mxn: string; periodicidad: Periodicidad; dia_corte: string
  fecha_inicio: string; proxima_renovacion: string; estado: EstadoSuscripcion
  notas: string; rfc: string; razon_social: string; correo_facturacion: string
}

function Campo({ etiqueta, children }: { etiqueta: string; children: React.ReactNode }) {
  return (
    <label className="block text-xs font-semibold text-dax-muted">
      {etiqueta}
      <span className="block mt-1">{children}</span>
    </label>
  )
}

export function SeccionSuscripcion({
  orgId, plans, onPlanCambiado,
}: {
  orgId: number
  plans: Plan[]
  /** El plan de la suscripción mueve `organization.plan`: la ficha se recarga. */
  onPlanCambiado?: () => void
}) {
  const puedeEscribir = useAuthStore((s) => s.user?.platform_role) === 'SUPERADMIN'
  const [datos, setDatos] = useState<SuscripcionDetalle | null>(null)
  const [error, setError] = useState('')
  const [ocupado, setOcupado] = useState(false)
  const [form, setForm] = useState<Formulario | null>(null)
  const [pagoDe, setPagoDe] = useState<Cargo | null>(null)
  const [pago, setPago] = useState({ importe: '', metodo: 'transferencia' as MetodoPago, fecha_pago: '', referencia: '', notas: '' })
  const [cancelarDe, setCancelarDe] = useState<Cargo | null>(null)
  const [motivo, setMotivo] = useState('')

  useEffect(() => {
    let vivo = true
    setDatos(null); setError('')
    suscripcionesApi.detalle(orgId)
      .then((d) => { if (vivo) setDatos(d) })
      .catch((e) => { if (vivo) setError(detalleError(e, 'No se pudo cargar la suscripción')) })
    return () => { vivo = false }
  }, [orgId])

  const sus = datos?.suscripcion ?? null
  const precioLista = (clave: string) => String(plans.find((p) => p.clave === clave)?.precio_mxn ?? 0)

  const abrirFormulario = () => {
    const plan = sus?.plan ?? datos?.plan_organizacion ?? 'FREE'
    setForm({
      plan,
      precio_mxn: sus ? String(num(sus.precio_mxn)) : precioLista(plan),
      periodicidad: sus?.periodicidad ?? 'mensual',
      dia_corte: sus ? String(sus.dia_corte) : '',
      fecha_inicio: sus?.fecha_inicio ?? hoyLocal(),
      proxima_renovacion: sus?.proxima_renovacion ?? '',
      estado: sus?.estado ?? 'al_corriente',
      notas: sus?.notas ?? '', rfc: sus?.rfc ?? '', razon_social: sus?.razon_social ?? '',
      correo_facturacion: sus?.correo_facturacion ?? '',
    })
  }

  const ejecutar = async (accion: () => Promise<SuscripcionDetalle | void>, exito: string, respaldo: string) => {
    setOcupado(true)
    try {
      const d = await accion()
      if (d) setDatos(d)
      toast.success(exito)
      return true
    } catch (e) {
      toast.error(detalleError(e, respaldo))
      return false
    } finally {
      setOcupado(false)
    }
  }

  const guardar = async () => {
    if (!form) return
    const cuerpo: SuscripcionEntrada = {
      plan: form.plan, precio_mxn: form.precio_mxn || '0', periodicidad: form.periodicidad,
      notas: form.notas, rfc: form.rfc, razon_social: form.razon_social, correo_facturacion: form.correo_facturacion,
    }
    if (form.dia_corte) cuerpo.dia_corte = Number(form.dia_corte)
    if (form.fecha_inicio) cuerpo.fecha_inicio = form.fecha_inicio
    if (form.proxima_renovacion) cuerpo.proxima_renovacion = form.proxima_renovacion
    // El estado solo viaja cuando se pone o se quita uno manual: los demás los calcula el servidor.
    const manual = form.estado === 'suspendida' || form.estado === 'cortesia'
    if (manual || sus?.estado_manual) cuerpo.estado = form.estado
    const planAntes = sus?.plan ?? datos?.plan_organizacion
    const ok = await ejecutar(() => suscripcionesApi.guardar(orgId, cuerpo), sus ? 'Suscripción actualizada' : 'Suscripción dada de alta', 'No se pudo guardar la suscripción')
    if (ok) {
      setForm(null)
      if (form.plan !== planAntes) onPlanCambiado?.()
    }
  }

  const generarCargo = () => ejecutar(async () => {
    const r = await suscripcionesApi.generarCargo(orgId)
    if (!r.creado) toast.info('El cargo de ese periodo ya existía.')
    return suscripcionesApi.detalle(orgId)
  }, 'Cargo del periodo listo', 'No se pudo generar el cargo')

  const abrirPago = (c: Cargo) => {
    setPagoDe(c)
    setPago({ importe: String(num(c.saldo)), metodo: 'transferencia', fecha_pago: hoyLocal(), referencia: '', notas: '' })
  }
  const registrarPago = async () => {
    if (!pagoDe) return
    const ok = await ejecutar(() => suscripcionesApi.registrarPago(pagoDe.id, {
      importe: pago.importe, metodo: pago.metodo, fecha_pago: pago.fecha_pago || undefined,
      referencia: pago.referencia || undefined, notas: pago.notas || undefined,
    }), 'Pago registrado', 'No se pudo registrar el pago')
    if (ok) setPagoDe(null)
  }
  const cancelarCargo = async () => {
    if (!cancelarDe) return
    const ok = await ejecutar(() => suscripcionesApi.cancelarCargo(cancelarDe.id, motivo || undefined), 'Cargo cancelado', 'No se pudo cancelar el cargo')
    if (ok) { setCancelarDe(null); setMotivo('') }
  }

  const cambiar = <K extends keyof Formulario>(k: K, v: Formulario[K]) => setForm((f) => (f ? { ...f, [k]: v } : f))

  return (
    <section style={tarjeta} data-testid="seccion-suscripcion">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12, flexWrap: 'wrap', gap: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <p style={titulo}>Suscripción</p>
          {sus && <PildoraEstado estado={sus.estado} />}
        </div>
        {puedeEscribir && datos && (
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {sus && (
              <button type="button" style={boton} disabled={ocupado} onClick={generarCargo}>
                <i className="fa-solid fa-file-invoice-dollar" aria-hidden="true" /> Generar cargo
              </button>
            )}
            <button type="button" style={sus ? boton : botonPrincipal} disabled={ocupado} onClick={abrirFormulario}>
              <i className={`fa-solid ${sus ? 'fa-pen' : 'fa-plus'}`} aria-hidden="true" /> {sus ? 'Editar' : 'Dar de alta'}
            </button>
          </div>
        )}
      </div>

      {error ? (
        <p style={{ margin: 0, fontSize: 12, color: 'var(--p-danger)' }} role="alert">{error}</p>
      ) : !datos ? (
        <p style={{ margin: 0, fontSize: 12, color: 'var(--p-muted)' }}>Cargando suscripción…</p>
      ) : !sus ? (
        <p style={{ margin: 0, fontSize: 12, color: 'var(--p-muted)' }}>
          Esta organización todavía no tiene suscripción. Mientras no se dé de alta no entra en la cartera ni en el ingreso recurrente.
        </p>
      ) : (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 12 }}>
            {dato('Plan', sus.plan_nombre)}
            {dato('Precio pactado', (
              <>
                {formatCurrency(num(sus.precio_mxn))} {sus.periodicidad === 'anual' ? 'al año' : 'al mes'}
                {num(sus.precio_mxn) !== num(sus.precio_lista_mxn) && (
                  <span style={{ color: 'var(--p-muted)', fontSize: 11 }}> (lista {formatCurrency(num(sus.precio_lista_mxn))})</span>
                )}
              </>
            ))}
            {dato('Día de corte', sus.dia_corte)}
            {dato('Inicio', fechaCorta(sus.fecha_inicio))}
            {dato('Próxima renovación', fechaCorta(sus.proxima_renovacion))}
            {dato('Facturación', [sus.rfc, sus.razon_social, sus.correo_facturacion].filter(Boolean).join(' · ') || '—')}
          </div>
          {sus.notas && <p style={{ margin: '10px 0 0', fontSize: 12, color: 'var(--p-muted)', whiteSpace: 'pre-wrap' }}>{sus.notas}</p>}
          {sus.estado === 'suspendida' && (
            <p style={{ margin: '10px 0 0', fontSize: 12, color: 'var(--p-muted)' }}>
              Suspendida es informativa en esta versión: la tienda sigue entrando y vendiendo.
            </p>
          )}

          <p style={{ ...titulo, marginTop: 16, marginBottom: 6 }}>Cargos</p>
          {datos.cargos.length === 0 ? (
            <p style={{ margin: 0, fontSize: 12, color: 'var(--p-muted)' }}>Sin cargos todavía.</p>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr>
                    {['Periodo', 'Vence', 'Importe', 'Saldo', 'Estado', 'Pagos', ''].map((c) => <th key={c} style={celdaCabeza}>{c}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {datos.cargos.map((c) => (
                    <tr key={c.id} data-testid={`cargo-${c.id}`}>
                      <td style={{ ...celda, whiteSpace: 'nowrap' }}>{fechaCorta(c.periodo_desde)} – {fechaCorta(c.periodo_hasta)}</td>
                      <td style={{ ...celda, whiteSpace: 'nowrap', color: c.vencido ? 'var(--p-danger)' : 'var(--p-text)' }}>{fechaCorta(c.vence_el)}</td>
                      <td style={{ ...celda, fontVariantNumeric: 'tabular-nums' }}>{formatCurrency(num(c.importe))}</td>
                      <td style={{ ...celda, fontVariantNumeric: 'tabular-nums' }}>{formatCurrency(num(c.saldo))}</td>
                      <td style={{ ...celda, color: c.estado === 'pagado' ? 'var(--p-success)' : c.estado === 'cancelado' ? 'var(--p-muted)' : c.vencido ? 'var(--p-danger)' : 'var(--p-warning)' }}>
                        {c.vencido ? 'Vencido' : ETIQUETA_CARGO[c.estado]}
                        {c.motivo_cancelacion && <div style={{ fontSize: 11, color: 'var(--p-muted)' }}>{c.motivo_cancelacion}</div>}
                      </td>
                      <td style={{ ...celda, fontSize: 12 }}>
                        {c.pagos.length === 0 ? <span style={{ color: 'var(--p-muted)' }}>—</span> : c.pagos.map((p) => (
                          <div key={p.id}>
                            {fechaCorta(p.fecha_pago)} · {ETIQUETA_METODO[p.metodo] ?? p.metodo}{p.referencia ? ` · ${p.referencia}` : ''} · <strong>{formatCurrency(num(p.importe))}</strong>
                            {p.registrado_por && <span style={{ color: 'var(--p-muted)' }}> · {p.registrado_por}</span>}
                          </div>
                        ))}
                      </td>
                      <td style={{ ...celda, whiteSpace: 'nowrap', textAlign: 'right' }}>
                        {puedeEscribir && c.estado === 'pendiente' && (
                          <span style={{ display: 'inline-flex', gap: 6 }}>
                            <button type="button" style={botonPrincipal} disabled={ocupado} onClick={() => abrirPago(c)}>Registrar pago</button>
                            {c.pagos.length === 0 && (
                              <button type="button" style={boton} disabled={ocupado} onClick={() => { setCancelarDe(c); setMotivo('') }}>Cancelar</button>
                            )}
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      <Modal
        open={form !== null}
        onClose={() => setForm(null)}
        title={sus ? 'Editar suscripción' : 'Dar de alta la suscripción'}
        size="lg"
        closeOnBackdrop={false}
        footer={<>
          <button type="button" className="dax-btn-secondary" onClick={() => setForm(null)}>Cancelar</button>
          <button type="button" className="dax-btn-primary" disabled={ocupado} onClick={guardar}>Guardar</button>
        </>}
      >
        {form && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Campo etiqueta="Plan">
              <select className="dax-input" value={form.plan} aria-label="Plan"
                onChange={(e) => setForm((f) => (f ? { ...f, plan: e.target.value, precio_mxn: sus ? f.precio_mxn : precioLista(e.target.value) } : f))}>
                {plans.map((p) => <option key={p.clave} value={p.clave}>{`${p.nombre} · lista $${p.precio_mxn.toLocaleString('es-MX')}`}</option>)}
              </select>
            </Campo>
            <Campo etiqueta="Precio pactado (MXN por periodo)">
              <input className="dax-input" type="number" min="0" step="0.01" inputMode="decimal" aria-label="Precio pactado"
                value={form.precio_mxn} onChange={(e) => cambiar('precio_mxn', e.target.value)} />
            </Campo>
            <Campo etiqueta="Periodicidad">
              <select className="dax-input" value={form.periodicidad} aria-label="Periodicidad" onChange={(e) => cambiar('periodicidad', e.target.value as Periodicidad)}>
                <option value="mensual">Mensual</option>
                <option value="anual">Anual</option>
              </select>
            </Campo>
            <Campo etiqueta="Día de corte (1 a 28)">
              <input className="dax-input" type="number" min="1" max="28" aria-label="Día de corte" placeholder="El día del inicio"
                value={form.dia_corte} onChange={(e) => cambiar('dia_corte', e.target.value)} />
            </Campo>
            <Campo etiqueta="Fecha de inicio">
              <input className="dax-input" type="date" aria-label="Fecha de inicio" value={form.fecha_inicio} onChange={(e) => cambiar('fecha_inicio', e.target.value)} />
            </Campo>
            <Campo etiqueta="Próxima renovación">
              <input className="dax-input" type="date" aria-label="Próxima renovación" value={form.proxima_renovacion} onChange={(e) => cambiar('proxima_renovacion', e.target.value)} />
            </Campo>
            <Campo etiqueta="Estado">
              <select className="dax-input" value={form.estado} aria-label="Estado" onChange={(e) => cambiar('estado', e.target.value as EstadoSuscripcion)}>
                {ESTADOS.map((e) => (
                  <option key={e} value={e}>
                    {e === 'suspendida' || e === 'cortesia' ? `${ETIQUETA_ESTADO[e]} (manual)` : `${ETIQUETA_ESTADO[e]} (automático)`}
                  </option>
                ))}
              </select>
            </Campo>
            <Campo etiqueta="RFC">
              <input className="dax-input" maxLength={13} aria-label="RFC" value={form.rfc} onChange={(e) => cambiar('rfc', e.target.value)} />
            </Campo>
            <Campo etiqueta="Razón social">
              <input className="dax-input" aria-label="Razón social" value={form.razon_social} onChange={(e) => cambiar('razon_social', e.target.value)} />
            </Campo>
            <Campo etiqueta="Correo de facturación">
              <input className="dax-input" type="email" aria-label="Correo de facturación" value={form.correo_facturacion} onChange={(e) => cambiar('correo_facturacion', e.target.value)} />
            </Campo>
            <div className="sm:col-span-2">
              <Campo etiqueta="Notas internas (la tienda no las ve)">
                <textarea className="dax-input" rows={2} aria-label="Notas internas" value={form.notas} onChange={(e) => cambiar('notas', e.target.value)} />
              </Campo>
            </div>
            <p className="sm:col-span-2 text-xs text-dax-muted">
              Cambiar el plan aquí también cambia el plan de la organización. Los estados automáticos los calcula el sistema con las fechas y los cargos;
              suspendida y cortesía se quedan hasta que se quiten a mano y no bloquean ningún acceso.
            </p>
          </div>
        )}
      </Modal>

      <Modal
        open={pagoDe !== null}
        onClose={() => setPagoDe(null)}
        title="Registrar pago"
        closeOnBackdrop={false}
        footer={<>
          <button type="button" className="dax-btn-secondary" onClick={() => setPagoDe(null)}>Cancelar</button>
          <button type="button" className="dax-btn-primary" disabled={ocupado || !(num(pago.importe) > 0)} onClick={registrarPago}>Registrar pago</button>
        </>}
      >
        {pagoDe && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <p className="sm:col-span-2 text-sm text-dax-muted">
              Periodo {fechaCorta(pagoDe.periodo_desde)} – {fechaCorta(pagoDe.periodo_hasta)} · saldo{' '}
              <strong className="text-dax-text">{formatCurrency(num(pagoDe.saldo))}</strong>
            </p>
            <Campo etiqueta="Importe">
              <input className="dax-input" type="number" min="0.01" step="0.01" inputMode="decimal" aria-label="Importe del pago"
                value={pago.importe} onChange={(e) => setPago({ ...pago, importe: e.target.value })} />
            </Campo>
            <Campo etiqueta="Método">
              <select className="dax-input" aria-label="Método de pago" value={pago.metodo} onChange={(e) => setPago({ ...pago, metodo: e.target.value as MetodoPago })}>
                {METODOS.map((m) => <option key={m} value={m}>{ETIQUETA_METODO[m]}</option>)}
              </select>
            </Campo>
            <Campo etiqueta="Fecha del pago">
              <input className="dax-input" type="date" aria-label="Fecha del pago" value={pago.fecha_pago} onChange={(e) => setPago({ ...pago, fecha_pago: e.target.value })} />
            </Campo>
            <Campo etiqueta="Referencia">
              <input className="dax-input" aria-label="Referencia" placeholder="Folio SPEI, ficha…" maxLength={120}
                value={pago.referencia} onChange={(e) => setPago({ ...pago, referencia: e.target.value })} />
            </Campo>
            <div className="sm:col-span-2">
              <Campo etiqueta="Notas internas">
                <textarea className="dax-input" rows={2} aria-label="Notas del pago" value={pago.notas} onChange={(e) => setPago({ ...pago, notas: e.target.value })} />
              </Campo>
            </div>
            {num(pago.importe) > num(pagoDe.saldo) && (
              <p className="sm:col-span-2 text-xs text-dax-danger" role="alert">El importe es mayor al saldo del cargo.</p>
            )}
          </div>
        )}
      </Modal>

      <Modal
        open={cancelarDe !== null}
        onClose={() => setCancelarDe(null)}
        title="Cancelar cargo"
        size="sm"
        footer={<>
          <button type="button" className="dax-btn-secondary" onClick={() => setCancelarDe(null)}>Volver</button>
          <button type="button" className="dax-btn-danger" disabled={ocupado} onClick={cancelarCargo}>Cancelar cargo</button>
        </>}
      >
        {cancelarDe && (
          <div className="space-y-3">
            <p className="text-sm text-dax-muted">
              Se cancela el cargo de {formatCurrency(num(cancelarDe.importe))} del periodo que empieza el {fechaCorta(cancelarDe.periodo_desde)}. Queda en el historial.
            </p>
            <Campo etiqueta="Motivo">
              <input className="dax-input" aria-label="Motivo de la cancelación" maxLength={255} value={motivo} onChange={(e) => setMotivo(e.target.value)} />
            </Campo>
          </div>
        )}
      </Modal>
    </section>
  )
}
