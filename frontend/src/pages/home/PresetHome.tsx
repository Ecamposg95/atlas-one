import { useEffect } from 'react'
import { Link, Navigate } from 'react-router-dom'
import { useEnabledModulesStore } from '../../store/enabledModulesStore'
import { useAuthStore } from '../../store/authStore'
import { rolesConAcceso } from '../../components/layout/navConfig'
import { GastroHomeDay } from './GastroHomeDay'

/**
 * Home distinta por preset (Atlas One verticals).
 *
 * - ATLAS_ONE_BEAUTY     → BeautyHome
 * - ATLAS_ONE_GASTRO     → GastroHome
 * - ATLAS_ONE_RETAIL     → RetailHome
 * - ATLAS_ONE_SERVICES   → ServicesHome
 * - ATLAS_ONE_ENTERPRISE → EnterpriseHome
 * - Anything else (incl. ATLAS_POS, null) → redirect to /hq/operations
 *
 * Widgets are intentionally lightweight placeholders that CTA into the
 * relevant modules. Real KPIs land when each vertical builds its own widget.
 */
export function PresetHome() {
  const { user, org } = useAuthStore()
  const { preset, loaded, load } = useEnabledModulesStore()

  useEffect(() => {
    if (!loaded) load()
  }, [loaded, load])

  if (!loaded) {
    return (
      <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--p-muted)' }}>
        <i className="fa-solid fa-spinner fa-spin" style={{ fontSize: 22 }} />
        <p style={{ marginTop: 12, fontSize: 13 }}>Cargando inicio...</p>
      </div>
    )
  }

  const greeting = user?.full_name?.split(' ')[0] || user?.username || ''
  const orgName = org?.name || ''
  // Cobrar es de la cajera: el administrador ya no tiene `/pos` y ofrecerle
  // "Ir al POS" aquí lo mandaría a una ruta que su propia guarda le rebota.
  // Se deriva de ROLE_ROUTES para no tener una segunda lista que mantener.
  const puedeCobrar = !!user?.role && rolesConAcceso('/pos').includes(user.role)
  const home = { greeting, orgName, puedeCobrar }

  switch (preset) {
    // Taxonomy v2 (2026-05-15)
    case 'ATLAS_ONE_BARBER':
      return <BarberHome {...home} />
    case 'ATLAS_ONE_BEAUTY_WELLNESS':
      return <BeautyWellnessHome {...home} />
    case 'ATLAS_ONE_HEALTH':
      return <HealthHome {...home} />
    case 'ATLAS_ONE_RESTAURANT':
      return <RestaurantHome {...home} />
    case 'ATLAS_ONE_CAFE':
      return <CafeHome {...home} />
    case 'ATLAS_ONE_BAR':
      return <BarHome {...home} />
    // Atlas One verticals (v1)
    case 'ATLAS_ONE_RETAIL':
      return <RetailHome {...home} />
    case 'ATLAS_ONE_SERVICES':
      return <ServicesHome {...home} />
    case 'ATLAS_ONE_ENTERPRISE':
      return <EnterpriseHome {...home} />
    // Legacy aliases — orgs created before taxonomy v2 still land on
    // a coherent home instead of redirecting to /hq/operations.
    case 'ATLAS_ONE_BEAUTY':
      return <BeautyWellnessHome {...home} />
    case 'ATLAS_ONE_GASTRO':
      return <RestaurantHome {...home} />
    default:
      return <Navigate to="/hq/operations" replace />
  }
}

// ── Shared shell ────────────────────────────────────────────────────────────

interface HomeProps {
  greeting: string
  orgName: string
  /** ¿Este rol puede abrir el punto de venta? (ver ROLE_ROUTES). */
  puedeCobrar: boolean
}

function HomeShell({
  greeting,
  orgName,
  title,
  subtitle,
  accent,
  children,
}: Omit<HomeProps, 'puedeCobrar'> & {
  title: string
  subtitle: string
  accent: string
  children: React.ReactNode
}) {
  return (
    <div style={{ padding: '2rem', maxWidth: 1200, margin: '0 auto' }}>
      <header style={{ marginBottom: 24 }}>
        <p style={{
          margin: 0,
          fontSize: 11,
          color: 'var(--p-muted)',
          textTransform: 'uppercase',
          letterSpacing: '0.08em',
          fontWeight: 600,
        }}>
          {orgName} · {title}
        </p>
        <h1 style={{ margin: '4px 0 8px', fontSize: '1.6rem', fontWeight: 700 }}>
          {greeting ? `Hola, ${greeting}` : 'Bienvenido'}
        </h1>
        <p style={{ margin: 0, color: 'var(--p-muted)', fontSize: 14 }}>{subtitle}</p>
        <span style={{
          display: 'inline-block',
          marginTop: 8,
          padding: '2px 10px',
          borderRadius: 4,
          background: `${accent}22`,
          color: accent,
          fontSize: 11,
          fontWeight: 700,
          letterSpacing: '0.04em',
          textTransform: 'uppercase',
        }}>
          {title}
        </span>
      </header>
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
        gap: 16,
      }}>
        {children}
      </div>
    </div>
  )
}

interface WidgetProps {
  icon: string
  title: string
  description: string
  cta: string
  ctaUrl: string
  beta?: boolean
}

function Widget({ icon, title, description, cta, ctaUrl, beta }: WidgetProps) {
  return (
    <div style={{
      background: 'var(--p-surface)',
      border: '1px solid var(--p-border)',
      borderRadius: 6,
      padding: 16,
      display: 'flex',
      flexDirection: 'column',
      gap: 10,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <span style={{
          width: 32, height: 32, borderRadius: 6,
          background: 'rgba(0,201,177,0.12)',
          color: 'var(--p-teal)',
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: 14,
        }}>
          <i className={`fa-solid ${icon}`} />
        </span>
        <strong style={{ fontSize: 13 }}>{title}</strong>
        {beta && (
          <span style={{
            marginLeft: 'auto',
            fontSize: 9,
            padding: '1px 6px',
            borderRadius: 3,
            fontWeight: 700,
            letterSpacing: '0.04em',
            background: 'rgba(245,158,11,0.18)',
            color: 'var(--p-warning)',
          }}>
            BETA
          </span>
        )}
      </div>
      <p style={{ margin: 0, fontSize: 12, color: 'var(--p-muted)', lineHeight: 1.5, flex: 1 }}>{description}</p>
      <Link
        to={ctaUrl}
        style={{
          fontSize: 12,
          color: 'var(--p-teal)',
          textDecoration: 'none',
          fontWeight: 600,
          marginTop: 'auto',
        }}
      >
        {cta} <i className="fa-solid fa-arrow-right" style={{ fontSize: 10, marginLeft: 4 }} />
      </Link>
    </div>
  )
}

// ── Per-preset homes ────────────────────────────────────────────────────────

function BarberHome({ greeting, orgName, puedeCobrar }: HomeProps) {
  return (
    <HomeShell
      greeting={greeting}
      orgName={orgName}
      title="Atlas One Barber"
      subtitle="Agenda de cortes, paquetes prepagados y comisiones del equipo."
      accent="#0891b2"
    >
      <Widget icon="fa-calendar" title="Agenda de hoy" description="Cortes y barbas agendadas, sillas disponibles." cta="Abrir agenda" ctaUrl="/appointments" beta />
      <Widget icon="fa-id-card" title="Paquetes prepagados" description="Bonos de N cortes y vencimientos próximos." cta="Ver paquetes" ctaUrl="/memberships" beta />
      <Widget icon="fa-percent" title="Comisiones del turno" description="Resumen por barbero al cierre del día." cta="Ver comisiones" ctaUrl="/commissions" beta />
      <Widget icon="fa-address-book" title="Clientes recurrentes" description="Historial de cortes y preferencias." cta="Ver clientes" ctaUrl="/customers" />
      {puedeCobrar && <Widget icon="fa-cash-register" title="Cobrar" description="Cobrar servicio o paquete en silla." cta="Ir al POS" ctaUrl="/pos" />}
      <Widget icon="fa-chart-pie" title="Reportes" description="Ingreso por barbero, servicios top." cta="Ver reportes" ctaUrl="/reports" />
    </HomeShell>
  )
}

function BeautyWellnessHome({ greeting, orgName, puedeCobrar }: HomeProps) {
  return (
    <HomeShell
      greeting={greeting}
      orgName={orgName}
      title="Atlas One Beauty & Wellness"
      subtitle="Agenda, servicios, comisiones y clientes en un solo lugar."
      accent="#ec4899"
    >
      <Widget icon="fa-calendar" title="Citas de hoy" description="Agenda del día por profesional y cabina." cta="Abrir agenda" ctaUrl="/appointments" beta />
      <Widget icon="fa-id-card" title="Membresías activas" description="Saldo de paquetes y vencimientos próximos." cta="Ver membresías" ctaUrl="/memberships" beta />
      <Widget icon="fa-percent" title="Comisiones del turno" description="Resumen de comisiones al cierre." cta="Ver comisiones" ctaUrl="/commissions" beta />
      <Widget icon="fa-address-book" title="Clientes" description="Historial, preferencias y frecuencia." cta="Ver clientes" ctaUrl="/customers" />
      {puedeCobrar && <Widget icon="fa-cash-register" title="Vender" description="Cobrar servicio o producto." cta="Ir al POS" ctaUrl="/pos" />}
      <Widget icon="fa-chart-pie" title="Reportes" description="Servicios top, ticket promedio." cta="Ver reportes" ctaUrl="/reports" />
    </HomeShell>
  )
}

function HealthHome({ greeting, orgName, puedeCobrar }: HomeProps) {
  return (
    <HomeShell
      greeting={greeting}
      orgName={orgName}
      title="Atlas One Health"
      subtitle="Pacientes, agenda, planes de tratamiento y cobros."
      accent="#06b6d4"
    >
      <Widget icon="fa-calendar" title="Consultas de hoy" description="Agenda por consultorio y profesional." cta="Abrir agenda" ctaUrl="/appointments" beta />
      <Widget icon="fa-user-injured" title="Pacientes" description="Historial clínico, notas y contactos." cta="Ver pacientes" ctaUrl="/customers" />
      <Widget icon="fa-id-card" title="Planes de tratamiento" description="Paquetes prepagados y avance por paciente." cta="Ver planes" ctaUrl="/memberships" beta />
      <Widget icon="fa-percent" title="Comisiones" description="Pago por consulta o sesión." cta="Ver comisiones" ctaUrl="/commissions" beta />
      {puedeCobrar && <Widget icon="fa-cash-register" title="Cobrar" description="Cobro de consulta o paquete." cta="Ir al POS" ctaUrl="/pos" />}
      <Widget icon="fa-chart-pie" title="Reportes" description="Consultas atendidas, ingresos por profesional." cta="Ver reportes" ctaUrl="/reports" />
    </HomeShell>
  )
}

function RestaurantHome({ greeting, orgName, puedeCobrar }: HomeProps) {
  return (
    <GastroHomeDay
      greeting={greeting}
      orgName={orgName}
      title="Atlas One Restaurant"
      subtitle="Cocina en vivo, mesas, recetas y meseros — el pulso del día."
      accent="#e2531b"
      topLabel="Platillos top"
      actions={[
        { icon: 'fa-utensils', label: 'Cocina · KDS', to: '/kitchen' },
        { icon: 'fa-chair', label: 'Plano de mesas', to: '/tables' },
        ...(puedeCobrar ? [{ icon: 'fa-cash-register', label: 'Cobrar mesa', to: '/pos' }] : []),
        { icon: 'fa-book', label: 'Recetas', to: '/recipes', beta: true },
        { icon: 'fa-percent', label: 'Comisiones', to: '/commissions', beta: true },
        { icon: 'fa-chart-pie', label: 'Reportes', to: '/reports' },
      ]}
    />
  )
}

function CafeHome({ greeting, orgName, puedeCobrar }: HomeProps) {
  return (
    <GastroHomeDay
      greeting={greeting}
      orgName={orgName}
      title="Atlas One Café"
      subtitle="Mostrador rápido, cocina y caja para café/bakery."
      accent="#8b4a2b"
      topLabel="Productos top"
      actions={[
        { icon: 'fa-coffee', label: 'Mostrador · KDS', to: '/kitchen' },
        ...(puedeCobrar ? [{ icon: 'fa-cash-register', label: 'Cobrar', to: '/pos' }] : []),
        { icon: 'fa-vault', label: 'Caja del día', to: '/cash-history' },
        { icon: 'fa-boxes', label: 'Inventario', to: '/inventory' },
        { icon: 'fa-address-book', label: 'Frecuentes', to: '/customers' },
        { icon: 'fa-chart-pie', label: 'Reportes', to: '/reports' },
      ]}
    />
  )
}

function BarHome({ greeting, orgName, puedeCobrar }: HomeProps) {
  return (
    <GastroHomeDay
      greeting={greeting}
      orgName={orgName}
      title="Atlas One Bar"
      subtitle="Barra, mesas, turnos e inventario líquido — control de la noche."
      accent="#7c3aed"
      topLabel="Bebidas top"
      actions={[
        { icon: 'fa-martini-glass', label: 'Barra · comandas', to: '/tables' },
        ...(puedeCobrar ? [{ icon: 'fa-cash-register', label: 'Cobrar tab', to: '/pos' }] : []),
        { icon: 'fa-boxes', label: 'Inventario líquido', to: '/inventory' },
        { icon: 'fa-book', label: 'Cocteles · recetas', to: '/recipes', beta: true },
        { icon: 'fa-percent', label: 'Comisiones', to: '/commissions', beta: true },
        { icon: 'fa-chart-pie', label: 'Reportes', to: '/reports' },
      ]}
    />
  )
}

function RetailHome({ greeting, orgName }: HomeProps) {
  return (
    <HomeShell
      greeting={greeting}
      orgName={orgName}
      title="Atlas One Retail"
      subtitle="Inventario, compras, sucursales y caja multi-tienda."
      accent="#3366ff"
    >
      <Widget icon="fa-boxes" title="Inventario" description="Stock por sucursal y movimientos del día." cta="Ver inventario" ctaUrl="/inventory" />
      <Widget icon="fa-truck" title="Compras" description="Órdenes a proveedores y recepciones." cta="Ver compras" ctaUrl="/purchasing" beta />
      <Widget icon="fa-store" title="Sucursales" description="Resumen de cada sucursal y catálogo habilitado." cta="Ver sucursales" ctaUrl="/hq/branches" />
      <Widget icon="fa-tag" title="Promociones" description="Promos activas, descuentos por temporada." cta="Ver promos" ctaUrl="/admin/catalog" />
      <Widget icon="fa-file-invoice-dollar" title="Cotizaciones" description="Presupuestos abiertos y conversión a venta." cta="Ver cotizaciones" ctaUrl="/quotes" />
      <Widget icon="fa-chart-pie" title="Reportes" description="Margen, rotación, productos top." cta="Ver reportes" ctaUrl="/hq/reports-hub" />
    </HomeShell>
  )
}

function ServicesHome({ greeting, orgName }: HomeProps) {
  return (
    <HomeShell
      greeting={greeting}
      orgName={orgName}
      title="Atlas One Services"
      subtitle="Órdenes de trabajo, agenda, cotizaciones y técnicos."
      accent="#33cc99"
    >
      <Widget icon="fa-screwdriver-wrench" title="Órdenes de trabajo" description="OT abiertas, en proceso y entregadas." cta="Ver OT" ctaUrl="/seguimiento" />
      <Widget icon="fa-calendar" title="Agenda de servicio" description="Citas de hoy y disponibilidad de técnicos." cta="Abrir agenda" ctaUrl="/appointments" beta />
      <Widget icon="fa-file-invoice-dollar" title="Cotizaciones" description="Presupuestos pendientes de aprobación." cta="Ver cotizaciones" ctaUrl="/quotes" />
      <Widget icon="fa-percent" title="Comisiones" description="Comisiones por técnico y servicio." cta="Ver comisiones" ctaUrl="/commissions" beta />
      <Widget icon="fa-address-book" title="Clientes" description="Historial de servicios por cliente." cta="Ver clientes" ctaUrl="/customers" />
      <Widget icon="fa-chart-pie" title="Reportes" description="Tiempos, OT por técnico, ingresos." cta="Ver reportes" ctaUrl="/reports" />
    </HomeShell>
  )
}

function EnterpriseHome({ greeting, orgName }: HomeProps) {
  return (
    <HomeShell
      greeting={greeting}
      orgName={orgName}
      title="Atlas One Enterprise"
      subtitle="Toda la operación a la vista: multi-sucursal, IA, integraciones."
      accent="#aa44ff"
    >
      <Widget icon="fa-gauge-high" title="Control Tower" description="KPIs ejecutivos y salud de la plataforma." cta="Ir a operaciones" ctaUrl="/hq/operations" />
      <Widget icon="fa-microchip" title="Copiloto IA" description="Predicciones, automatizaciones y resúmenes." cta="Abrir IA" ctaUrl="/ai" beta />
      <Widget icon="fa-truck" title="Compras" description="OC, proveedores y cuentas por pagar." cta="Ver compras" ctaUrl="/purchasing" beta />
      <Widget icon="fa-industry" title="Manufactura" description="Producción y consumo de insumos." cta="Ver manufactura" ctaUrl="/inventory" />
      <Widget icon="fa-users-gear" title="RRHH" description="Asistencia, nómina, vacaciones." cta="Ir a RRHH" ctaUrl="/hr" />
      <Widget icon="fa-chart-line" title="Reportes ejecutivos" description="Vista global multi-sucursal." cta="Ver reportes" ctaUrl="/hq/reports-hub" />
    </HomeShell>
  )
}
