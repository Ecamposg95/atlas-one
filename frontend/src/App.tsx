import { useEffect, useMemo, useState } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from './store/authStore'
import { useEnabledModulesStore } from './store/enabledModulesStore'
import { ThemeProvider } from './context/ThemeContext'
import { useKeyboardShortcuts } from './hooks/useKeyboardShortcuts'
import { useIsMobile } from './hooks/useIsMobile'
import { rutaInicioPorRol } from './utils/rutaInicio'

// Aplicar tema inicial antes del primer render — evita flash
const _savedTheme = localStorage.getItem('atlas_theme') ?? 'dark'
document.documentElement.classList.add(_savedTheme)
import { Layout } from './components/layout/Layout'
import { MobileLayout } from './components/layout/MobileLayout'
import { RequireRole } from './components/layout/RequireRole'
import { LoginPage } from './pages/Login'
import { NotFoundPage } from './pages/NotFound'

// Lazy imports — cada grupo de páginas se carga bajo demanda
import { lazy, Suspense } from 'react'
import { Spinner } from './components/ui/Spinner'

// HQ / Admin
const HQOperations    = lazy(() => import('./pages/hq/HQOperations').then(m => ({ default: m.HQOperations })))
const HQReportsHub    = lazy(() => import('./pages/hq/HQReportsHub').then(m => ({ default: m.HQReportsHub })))
const HQControl       = lazy(() => import('./pages/hq/HQControl').then(m => ({ default: m.HQControl })))
const HQSalesLog      = lazy(() => import('./pages/hq/HQSalesLog').then(m => ({ default: m.HQSalesLog })))
const HQReturns       = lazy(() => import('./pages/hq/HQReturns').then(m => ({ default: m.HQReturns })))
const HQInventory     = lazy(() => import('./pages/hq/HQInventory').then(m => ({ default: m.HQInventory })))
const HQBranches      = lazy(() => import('./pages/hq/HQBranches').then(m => ({ default: m.HQBranches })))
const HQBranchDetail  = lazy(() => import('./pages/hq/HQBranchDetail').then(m => ({ default: m.HQBranchDetail })))

// Catalog / Core
const AdminCatalog    = lazy(() => import('./pages/core/AdminCatalog').then(m => ({ default: m.AdminCatalog })))
const StoreScanner    = lazy(() => import('./pages/scanner/StoreScanner').then(m => ({ default: m.StoreScanner })))
const Departments     = lazy(() => import('./pages/core/Departments').then(m => ({ default: m.Departments })))
const Brands          = lazy(() => import('./pages/core/Brands').then(m => ({ default: m.Brands })))
const Users           = lazy(() => import('./pages/core/Users').then(m => ({ default: m.Users })))
const Organization    = lazy(() => import('./pages/core/Organization').then(m => ({ default: m.Organization })))
const Startup         = lazy(() => import('./pages/core/Startup').then(m => ({ default: m.Startup })))
const AdminProductCreate = lazy(() => import('./pages/admin/AdminProductCreate').then(m => ({ default: m.AdminProductCreate })))
const ProductForm = lazy(() => import('./pages/products/ProductForm').then(m => ({ default: m.ProductForm })))

// Ventas
const SalesHistory    = lazy(() => import('./pages/sales/SalesHistory').then(m => ({ default: m.SalesHistory })))
const Quotes          = lazy(() => import('./pages/sales/Quotes').then(m => ({ default: m.Quotes })))
const QuoteMaker      = lazy(() => import('./pages/sales/QuoteMaker').then(m => ({ default: m.QuoteMaker })))
const Returns         = lazy(() => import('./pages/sales/Returns').then(m => ({ default: m.Returns })))
const Seguimiento     = lazy(() => import('./pages/sales/Seguimiento').then(m => ({ default: m.Seguimiento })))

// Finance
const Purchases       = lazy(() => import('./pages/finance/Purchases').then(m => ({ default: m.Purchases })))
const Expenses        = lazy(() => import('./pages/finance/Expenses').then(m => ({ default: m.Expenses })))
const Reports         = lazy(() => import('./pages/finance/Reports').then(m => ({ default: m.Reports })))
const CashHistory     = lazy(() => import('./pages/finance/CashHistory').then(m => ({ default: m.CashHistory })))

// Inventory
const Inventory       = lazy(() => import('./pages/inventory/Inventory').then(m => ({ default: m.Inventory })))
const Logistics       = lazy(() => import('./pages/inventory/Logistics').then(m => ({ default: m.Logistics })))
const Boxes           = lazy(() => import('./pages/inventory/Boxes').then(m => ({ default: m.Boxes })))
const Products        = lazy(() => import('./pages/inventory/Products').then(m => ({ default: m.Products })))

// CRM / HR
const Customers       = lazy(() => import('./pages/crm/Customers').then(m => ({ default: m.Customers })))
const HR              = lazy(() => import('./pages/hr/HR').then(m => ({ default: m.HR })))
const HRMe            = lazy(() => import('./pages/hr/HRMe').then(m => ({ default: m.HRMe })))

// POS / Branch
const AtlasPOS        = lazy(() => import('./pages/pos/AtlasPOS').then(m => ({ default: m.AtlasPOS })))
const POS             = lazy(() => import('./pages/pos/POS').then(m => ({ default: m.POS })))
const PrinterSettings = lazy(() => import('./pages/pos/PrinterSettings').then(m => ({ default: m.PrinterSettings })))

// Mobile
const MobileDashboard = lazy(() => import('./pages/mobile/MobileDashboard').then(m => ({ default: m.MobileDashboard })))
const MobileQuery     = lazy(() => import('./pages/mobile/MobileQuery').then(m => ({ default: m.MobileQuery })))
const MobileSales     = lazy(() => import('./pages/mobile/MobileSales').then(m => ({ default: m.MobileSales })))
const MobileProfile   = lazy(() => import('./pages/mobile/MobileProfile').then(m => ({ default: m.MobileProfile })))
const MobileOwnerDashboard = lazy(() => import('./pages/mobile/MobileOwnerDashboard').then(m => ({ default: m.MobileOwnerDashboard })))

// Atlas One preset-aware home (2026-05-14)
const PresetHome = lazy(() => import('./pages/home/PresetHome').then(m => ({ default: m.PresetHome })))

// Atlas One stub modules (Beta — Coming Soon pages, 2026-05-14)
const AppointmentsComingSoon = lazy(() => import('./pages/coming-soon').then(m => ({ default: m.AppointmentsComingSoon })))
const CommissionsComingSoon  = lazy(() => import('./pages/coming-soon').then(m => ({ default: m.CommissionsComingSoon })))
const MembershipsComingSoon  = lazy(() => import('./pages/coming-soon').then(m => ({ default: m.MembershipsComingSoon })))
const AIComingSoon           = lazy(() => import('./pages/coming-soon').then(m => ({ default: m.AIComingSoon })))
const PurchasingComingSoon   = lazy(() => import('./pages/coming-soon').then(m => ({ default: m.PurchasingComingSoon })))

// Gastro modules (2026-06-22) — Mesas, Cocina/KDS, Recetas
const FloorPlan       = lazy(() => import('./pages/tables/FloorPlan').then(m => ({ default: m.FloorPlan })))
const KDS             = lazy(() => import('./pages/kitchen/KDS').then(m => ({ default: m.KDS })))
const Recipes         = lazy(() => import('./pages/recipes/Recipes').then(m => ({ default: m.Recipes })))
const RecipeForm      = lazy(() => import('./pages/recipes/RecipeForm').then(m => ({ default: m.RecipeForm })))
const ComandaTables   = lazy(() => import('./pages/mobile/ComandaTables').then(m => ({ default: m.ComandaTables })))
const ComandaOrder    = lazy(() => import('./pages/mobile/ComandaOrder').then(m => ({ default: m.ComandaOrder })))
const Meseros         = lazy(() => import('./pages/reports/Meseros').then(m => ({ default: m.Meseros })))
const Botellas        = lazy(() => import('./pages/bar/Botellas').then(m => ({ default: m.Botellas })))
const MenuVisual      = lazy(() => import('./pages/menu/MenuVisual').then(m => ({ default: m.MenuVisual })))

// Portal (CLIENTE)
const Portal          = lazy(() => import('./pages/portal/Portal').then(m => ({ default: m.Portal })))

// Dev-only preview (never included in production bundle)
const AtlasOnePreview = lazy(() => import('./pages/__dev__/AtlasOnePreview'))

// Platform (SUPERADMIN)
const PlatformLayout       = lazy(() => import('./pages/platform/PlatformLayout').then(m => ({ default: m.PlatformLayout })))
const PlatformMetrics      = lazy(() => import('./pages/platform/PlatformMetrics').then(m => ({ default: m.PlatformMetrics })))
const PlatformHealth       = lazy(() => import('./pages/platform/PlatformHealth').then(m => ({ default: m.PlatformHealth })))
const PlatformOrganizations= lazy(() => import('./pages/platform/PlatformOrganizations').then(m => ({ default: m.PlatformOrganizations })))
const PlatformOrgDetail    = lazy(() => import('./pages/platform/PlatformOrgDetail').then(m => ({ default: m.PlatformOrgDetail })))
const PlatformUsers        = lazy(() => import('./pages/platform/PlatformUsers').then(m => ({ default: m.PlatformUsers })))
const PlatformBranches     = lazy(() => import('./pages/platform/PlatformBranches').then(m => ({ default: m.PlatformBranches })))
const PlatformAuditLog     = lazy(() => import('./pages/platform/PlatformAuditLog').then(m => ({ default: m.PlatformAuditLog })))
const PlatformPresets      = lazy(() => import('./pages/platform/PlatformPresets').then(m => ({ default: m.PlatformPresets })))
const PlatformReports      = lazy(() => import('./pages/platform/PlatformReports').then(m => ({ default: m.PlatformReports })))
const PlatformCashAudit    = lazy(() => import('./pages/platform/PlatformCashAudit').then(m => ({ default: m.PlatformCashAudit })))
const PlatformModules      = lazy(() => import('./pages/platform/PlatformModules').then(m => ({ default: m.PlatformModules })))
const PlatformAdmins       = lazy(() => import('./pages/platform/PlatformAdmins').then(m => ({ default: m.PlatformAdmins })))
const PlatformAlerts       = lazy(() => import('./pages/platform/PlatformAlerts').then(m => ({ default: m.PlatformAlerts })))
const PlatformAnnouncements = lazy(() => import('./pages/platform/PlatformAnnouncements').then(m => ({ default: m.PlatformAnnouncements })))
const PlatformFlags        = lazy(() => import('./pages/platform/PlatformFlags').then(m => ({ default: m.PlatformFlags })))
const PlatformIncidents    = lazy(() => import('./pages/platform/PlatformIncidents').then(m => ({ default: m.PlatformIncidents })))
const PlatformApiKeys      = lazy(() => import('./pages/platform/PlatformApiKeys').then(m => ({ default: m.PlatformApiKeys })))
const MobilePlatformMonitor = lazy(() => import('./pages/platform/MobilePlatformMonitor').then(m => ({ default: m.MobilePlatformMonitor })))
const MobileOrgDetail       = lazy(() => import('./pages/platform/MobileOrgDetail').then(m => ({ default: m.MobileOrgDetail })))

function PrivateRoute({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const hydrated = useAuthStore((s) => s.hydrated)
  if (!hydrated) return <div className="flex items-center justify-center h-screen bg-slate-950"><Spinner size="lg" /></div>
  return isAuthenticated ? <>{children}</> : <Navigate to="/login" replace />
}

function SuperAdminRoute({ children }: { children: React.ReactNode }) {
  const user = useAuthStore((s) => s.user)
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const hydrated = useAuthStore((s) => s.hydrated)
  if (!hydrated) return <div className="flex items-center justify-center h-screen bg-slate-950"><Spinner size="lg" /></div>
  if (!isAuthenticated) return <Navigate to="/login" replace />
  if (user?.platform_role !== 'SUPERADMIN') return <Navigate to="/hq/operations" replace />
  return <>{children}</>
}

function PlatformRoute({ children }: { children: React.ReactNode }) {
  const user = useAuthStore((s) => s.user)
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const hydrated = useAuthStore((s) => s.hydrated)
  if (!hydrated) return <div className="flex items-center justify-center h-screen bg-slate-950"><Spinner size="lg" /></div>
  if (!isAuthenticated) return <Navigate to="/login" replace />
  if (user?.platform_role !== 'SUPERADMIN' && user?.platform_role !== 'SUPPORT') {
    return <Navigate to="/hq/operations" replace />
  }
  return <>{children}</>
}

function RoleHomeRedirect() {
  const user = useAuthStore((s) => s.user)
  const isMobile = useIsMobile()
  const { preset, loaded, load } = useEnabledModulesStore()
  useEffect(() => {
    if (!loaded) load()
  }, [loaded, load])

  // While the context is loading, hold off the redirect so HQ-role users with
  // an Atlas One preset don't briefly land on /hq/operations and flicker over
  // to /home.
  if ((user?.role === 'ADMINISTRADOR' || user?.role === 'DUEÑO') && !loaded) {
    return <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--p-muted)' }}>
      <i className="fa-solid fa-spinner fa-spin" style={{ fontSize: 22 }} />
    </div>
  }
  return <Navigate to={rutaInicioPorRol(user?.role, isMobile, preset)} replace />
}

function AtlasPOSGate({ children }: { children: React.ReactNode }) {
  const user = useAuthStore((s) => s.user)
  if (user?.role === 'ADMINISTRADOR' || user?.role === 'DUEÑO') {
    return <Navigate to="/hq/operations" replace />
  }
  return <>{children}</>
}

function PageLoader() {
  return (
    <div className="flex items-center justify-center h-full">
      <Spinner size="lg" text="Cargando..." />
    </div>
  )
}

export default function App() {
  const hydrate = useAuthStore((s) => s.hydrate)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    hydrate()
    setReady(true)
  }, [hydrate])

  // ESC global: cualquier componente (modal, panel, drawer) puede escuchar
  // `document.addEventListener('atlas:escape', handler)` para auto-cerrarse.
  // ConfirmDialog maneja su propio ESC (no hay conflicto).
  const globalShortcuts = useMemo(() => [
    {
      keys: 'Escape',
      global: true,
      skipInInput: false,
      preventDefault: false,
      handler: () => document.dispatchEvent(new CustomEvent('atlas:escape')),
    },
  ], [])
  useKeyboardShortcuts(globalShortcuts)

  if (!ready) {
    return (
      <div className="flex items-center justify-center h-screen bg-slate-950">
        <Spinner size="lg" text="Iniciando..." />
      </div>
    )
  }

  return (
    <ThemeProvider>
    <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Routes>
        {/* Público */}
        <Route path="/login" element={<LoginPage />} />

        {/* Dev-only — gated by Vite's import.meta.env.DEV (stripped in prod builds) */}
        {import.meta.env.DEV && (
          <Route
            path="/__dev__/atlas-one-preview"
            element={
              <Suspense fallback={<div style={{ padding: 40 }}>Loading…</div>}>
                <AtlasOnePreview />
              </Suspense>
            }
          />
        )}

        {/* Rutas protegidas — bajo Layout */}
        <Route
          path="/"
          element={
            <PrivateRoute>
              <Layout />
            </PrivateRoute>
          }
        >
          <Route index element={<RoleHomeRedirect />} />

          <Route path="atlas-pos" element={<AtlasPOSGate><Suspense fallback={<PageLoader />}><AtlasPOS /></Suspense></AtlasPOSGate>} />

          {/* HQ */}
          <Route path="hq">
            <Route path="operations" element={<Suspense fallback={<PageLoader />}><HQOperations /></Suspense>} />
            <Route path="reports-hub" element={<Suspense fallback={<PageLoader />}><HQReportsHub /></Suspense>} />
            <Route path="control" element={<Suspense fallback={<PageLoader />}><HQControl /></Suspense>} />
            <Route path="sales" element={<Suspense fallback={<PageLoader />}><HQSalesLog /></Suspense>} />
            <Route path="returns" element={<Suspense fallback={<PageLoader />}><HQReturns /></Suspense>} />
            <Route path="inventory" element={<Suspense fallback={<PageLoader />}><HQInventory /></Suspense>} />
            <Route path="branches" element={<Suspense fallback={<PageLoader />}><HQBranches /></Suspense>} />
            <Route path="branches/:branchId" element={<Suspense fallback={<PageLoader />}><HQBranchDetail /></Suspense>} />
          </Route>

          {/* Admin / Core — Track 3 (POS bug-fix): cajero tiene control
              avanzado del catálogo en su tienda. Backend filtra por
              organization_id + branch_id (cajero solo afecta productos
              de su sucursal vía PBS). */}
          <Route
            path="admin/catalog"
            element={
              <RequireRole roles={['ADMINISTRADOR', 'DUEÑO', 'GERENTE', 'CAJERO']}>
                <Suspense fallback={<PageLoader />}><AdminCatalog /></Suspense>
              </RequireRole>
            }
          />
          <Route
            path="admin/products/new"
            element={
              <RequireRole roles={['ADMINISTRADOR', 'DUEÑO', 'GERENTE', 'CAJERO']}>
                <Suspense fallback={<PageLoader />}><AdminProductCreate /></Suspense>
              </RequireRole>
            }
          />
          {/* Scanner de tienda — corrige precios y cuenta existencias parado en
              el pasillo. Mismo guard que admin/catalog y products/:id/edit:
              es escritura de catálogo/inventario scoped por sucursal. */}
          <Route
            path="scanner"
            element={
              <RequireRole roles={['ADMINISTRADOR', 'DUEÑO', 'GERENTE', 'CAJERO']}>
                <Suspense fallback={<PageLoader />}><StoreScanner /></Suspense>
              </RequireRole>
            }
          />
          <Route path="departments"   element={<Suspense fallback={<PageLoader />}><Departments /></Suspense>} />
          <Route path="brands"        element={<Suspense fallback={<PageLoader />}><Brands /></Suspense>} />
          <Route path="users"         element={<Suspense fallback={<PageLoader />}><Users /></Suspense>} />
          <Route path="organization"  element={<Suspense fallback={<PageLoader />}><Organization /></Suspense>} />
          <Route path="startup"       element={<Suspense fallback={<PageLoader />}><Startup /></Suspense>} />

          {/* Ventas */}
          <Route path="sales"         element={<Suspense fallback={<PageLoader />}><SalesHistory /></Suspense>} />
          <Route path="quotes"        element={<Suspense fallback={<PageLoader />}><Quotes /></Suspense>} />
          <Route path="quotes/new"    element={<Suspense fallback={<PageLoader />}><QuoteMaker /></Suspense>} />
          <Route path="returns"       element={<Suspense fallback={<PageLoader />}><Returns /></Suspense>} />
          <Route path="seguimiento"   element={<Suspense fallback={<PageLoader />}><Seguimiento /></Suspense>} />

          {/* Finanzas */}
          <Route path="purchases"    element={<Suspense fallback={<PageLoader />}><Purchases /></Suspense>} />
          <Route path="expenses"     element={<Suspense fallback={<PageLoader />}><Expenses /></Suspense>} />
          <Route path="reports"      element={<Suspense fallback={<PageLoader />}><Reports /></Suspense>} />
          <Route path="cash-history" element={<Suspense fallback={<PageLoader />}><CashHistory /></Suspense>} />

          {/* Inventario */}
          <Route path="inventory" element={<Suspense fallback={<PageLoader />}><Inventory /></Suspense>} />
          <Route path="logistics" element={<Suspense fallback={<PageLoader />}><Logistics /></Suspense>} />
          <Route path="boxes"     element={<Suspense fallback={<PageLoader />}><Boxes /></Suspense>} />
          <Route path="products"  element={<Suspense fallback={<PageLoader />}><Products /></Suspense>} />
          <Route path="products/new" element={
            <RequireRole roles={['ADMINISTRADOR', 'DUEÑO', 'GERENTE', 'CAJERO']}>
              <Suspense fallback={<PageLoader />}><ProductForm /></Suspense>
            </RequireRole>
          } />
          <Route path="products/:id/edit" element={
            <RequireRole roles={['ADMINISTRADOR', 'DUEÑO', 'GERENTE', 'CAJERO']}>
              <Suspense fallback={<PageLoader />}><ProductForm /></Suspense>
            </RequireRole>
          } />

          {/* CRM / HR */}
          <Route path="customers"  element={<Suspense fallback={<PageLoader />}><Customers /></Suspense>} />
          <Route path="hr"         element={<Suspense fallback={<PageLoader />}><HR /></Suspense>} />
          <Route path="hr/me"      element={<Suspense fallback={<PageLoader />}><HRMe /></Suspense>} />

          {/* Atlas One preset home + stub modules */}
          <Route path="home"         element={<Suspense fallback={<PageLoader />}><PresetHome /></Suspense>} />
          <Route path="appointments" element={<Suspense fallback={<PageLoader />}><AppointmentsComingSoon /></Suspense>} />
          <Route path="commissions"  element={<Suspense fallback={<PageLoader />}><CommissionsComingSoon /></Suspense>} />
          <Route path="memberships"  element={<Suspense fallback={<PageLoader />}><MembershipsComingSoon /></Suspense>} />
          {/* Gastro — Recetas (real), Mesas, Cocina/KDS */}
          <Route path="recipes"      element={<Suspense fallback={<PageLoader />}><Recipes /></Suspense>} />
          <Route path="recipes/new"  element={<Suspense fallback={<PageLoader />}><RecipeForm /></Suspense>} />
          <Route path="recipes/:id/edit" element={<Suspense fallback={<PageLoader />}><RecipeForm /></Suspense>} />
          <Route path="tables"       element={<Suspense fallback={<PageLoader />}><FloorPlan /></Suspense>} />
          <Route path="kitchen"      element={<Suspense fallback={<PageLoader />}><KDS /></Suspense>} />
          <Route path="meseros"      element={<Suspense fallback={<PageLoader />}><Meseros /></Suspense>} />
          <Route path="bar/bottles"  element={<Suspense fallback={<PageLoader />}><Botellas /></Suspense>} />
          <Route path="menu"         element={<Suspense fallback={<PageLoader />}><MenuVisual /></Suspense>} />
          <Route path="ai"           element={<Suspense fallback={<PageLoader />}><AIComingSoon /></Suspense>} />
          <Route path="purchasing"   element={<Suspense fallback={<PageLoader />}><PurchasingComingSoon /></Suspense>} />

          {/* POS */}
          <Route path="pos"             element={<Suspense fallback={<PageLoader />}><POS /></Suspense>} />
          <Route path="printer-settings" element={<Suspense fallback={<PageLoader />}><PrinterSettings /></Suspense>} />

          <Route path="*" element={<NotFoundPage />} />
        </Route>

        {/* Mobile + Portal — shell móvil propio (bottom-nav, sin sidebar) */}
        <Route
          path="/mobile"
          element={
            <PrivateRoute>
              <MobileLayout />
            </PrivateRoute>
          }
        >
          <Route path="dashboard" element={<Suspense fallback={<PageLoader />}><MobileDashboard /></Suspense>} />
          <Route path="query"     element={<Suspense fallback={<PageLoader />}><MobileQuery /></Suspense>} />
          <Route path="sales"     element={<Suspense fallback={<PageLoader />}><MobileSales /></Suspense>} />
          <Route path="profile"   element={<Suspense fallback={<PageLoader />}><MobileProfile /></Suspense>} />
          <Route path="comanda"          element={<Suspense fallback={<PageLoader />}><ComandaTables /></Suspense>} />
          <Route path="comanda/:tableId" element={<Suspense fallback={<PageLoader />}><ComandaOrder /></Suspense>} />
          <Route path="owner"     element={
            <RequireRole roles={['DUEÑO', 'ADMINISTRADOR']}>
              <Suspense fallback={<PageLoader />}><MobileOwnerDashboard /></Suspense>
            </RequireRole>
          } />
        </Route>

        {/* Portal CLIENTE — mismo shell móvil */}
        <Route
          path="/portal"
          element={
            <PrivateRoute>
              <MobileLayout />
            </PrivateRoute>
          }
        >
          <Route index element={<Suspense fallback={<PageLoader />}><Portal /></Suspense>} />
        </Route>

        {/* Platform — SUPERADMIN only, layout propio */}
        <Route
          path="/platform"
          element={
            <SuperAdminRoute>
              <Suspense fallback={<div className="flex items-center justify-center h-screen bg-slate-950"><Spinner size="lg" /></div>}>
                <PlatformLayout />
              </Suspense>
            </SuperAdminRoute>
          }
        >
          <Route index element={<Navigate to="/platform/metrics" replace />} />
          <Route path="control-tower" element={<Navigate to="/platform/metrics" replace />} />
          <Route path="cash-audit" element={<Suspense fallback={<PageLoader />}><PlatformCashAudit /></Suspense>} />
          <Route path="cash-audit/:sessionId" element={<Suspense fallback={<PageLoader />}><PlatformCashAudit /></Suspense>} />
          <Route path="metrics"       element={<Suspense fallback={<PageLoader />}><PlatformMetrics /></Suspense>} />
          <Route path="metrics-v2"    element={<Navigate to="/platform/metrics" replace />} />
          <Route path="health"        element={<Suspense fallback={<PageLoader />}><PlatformHealth /></Suspense>} />
          <Route path="alerts"        element={<Suspense fallback={<PageLoader />}><PlatformAlerts /></Suspense>} />
          <Route path="organizations" element={<Suspense fallback={<PageLoader />}><PlatformOrganizations /></Suspense>} />
          <Route path="organizations/:orgId" element={<Suspense fallback={<PageLoader />}><PlatformOrgDetail /></Suspense>} />
          <Route path="users"         element={<Suspense fallback={<PageLoader />}><PlatformUsers /></Suspense>} />
          <Route path="branches"      element={<Suspense fallback={<PageLoader />}><PlatformBranches /></Suspense>} />
          <Route path="presets"       element={<Suspense fallback={<PageLoader />}><PlatformPresets /></Suspense>} />
          <Route path="reportes"      element={<Suspense fallback={<PageLoader />}><PlatformReports /></Suspense>} />
          <Route path="modules"       element={<Suspense fallback={<PageLoader />}><PlatformModules /></Suspense>} />
          <Route path="admins"        element={<Suspense fallback={<PageLoader />}><PlatformAdmins /></Suspense>} />
          <Route path="announcements" element={<Suspense fallback={<PageLoader />}><PlatformAnnouncements /></Suspense>} />
          <Route path="flags"         element={<Suspense fallback={<PageLoader />}><PlatformFlags /></Suspense>} />
          <Route path="incidents"     element={<Suspense fallback={<PageLoader />}><PlatformIncidents /></Suspense>} />
          <Route path="api-keys"      element={<Suspense fallback={<PageLoader />}><PlatformApiKeys /></Suspense>} />
          <Route path="audit"         element={<Suspense fallback={<PageLoader />}><PlatformAuditLog /></Suspense>} />
        </Route>

        {/* Mobile platform monitor — read-only KPIs for SUPERADMIN/SUPPORT */}
        <Route
          path="/mobile/platform"
          element={
            <PlatformRoute>
              <Suspense fallback={<PageLoader />}><MobilePlatformMonitor /></Suspense>
            </PlatformRoute>
          }
        />
        <Route
          path="/mobile/platform/org/:orgId"
          element={
            <PlatformRoute>
              <Suspense fallback={<PageLoader />}><MobileOrgDetail /></Suspense>
            </PlatformRoute>
          }
        />
      </Routes>
    </BrowserRouter>
    </ThemeProvider>
  )
}
