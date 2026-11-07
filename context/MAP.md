# MAP.md — Mapeo de Componentes Atlas BOS

> Este archivo conecta la Arquitectura Conceptual (Engines) con la Implementación Física actual (Layered: Routers/Models).

---

## 1. Nucleus (Core & Org)
**Responsabilidad**: Tenancy, Usuarios, Seguridad, Configuración Global.

| Entidad | Router (`app/routers/`) | Model (`app/models/`) | Notas |
|---|---|---|---|
| **Organizational** | `organization.py`, `branches.py` | `organization.py` | Tenant root. |
| **Identity** | `auth.py`, `users.py` | `users.py` | Auth & Permissions. |
| **Platform** | `platform.py` | `platform.py` | Superadmin console. |
| **Modules** | `org_capabilities.py` | `modules.py` | Feature flags / Presets. |

---

## 2. Resource Engine (Catálogos)
**Responsabilidad**: Definición de cosas que se venden, compran o inventarían.

| Entidad | Router (`app/routers/`) | Model (`app/models/`) | Notas |
|---|---|---|---|
| **Products** | `products.py` | `products.py` | Items principales. |
| **Classifiers** | `brands.py`, `departments.py` | *En products.py* | Metadatos. |
| **Pricing** | `commercial.py` | *En products.py* | Listas de precios. |

---

## 3. Transaction Engine (Ventas & Caja)
**Responsabilidad**: Intercambio de valor. Flujo `DRAFT -> PAID`.

| Entidad | Router (`app/routers/`) | Model (`app/models/`) | Notas |
|---|---|---|---|
| **Sales** | `sales.py` | `sales.py` | Tickets y Ordenes. |
| **Quotes** | `quotes.py` | *En sales.py* | Cotizaciones. |
| **Returns** | `returns.py` | `returns.py` | Logística inversa. |
| **Cash** | `cash.py` | `cash.py` | Cortes de caja. |
| **Print** | `printer.py` | `print_job.py` | Hardware adapters. |

---

## 4. Inventory Engine (Logística)
**Responsabilidad**: Existencias, movimientos y ubicación.

| Entidad | Router (`app/routers/`) | Model (`app/models/`) | Notas |
|---|---|---|---|
| **Stock** | `inventory.py` | `inventory.py` | Kardex. |
| **Transfers** | `transfers.py` | `logistics.py` | Movimientos entre branches. |
| **Supply** | `purchases.py` | `abasto.py` | Compras. |

---

## 5. Relationship Engine (CRM/HR)
**Responsabilidad**: Personas y entidades externas.

| Entidad | Router (`app/routers/`) | Model (`app/models/`) | Notas |
|---|---|---|---|
| **Customers** | `customers.py` | *En sales.py?* | Clientes. |
| **CRM** | `crm.py` | `crm.py` | Pipeline. |
| **Staff** | `hr.py` | `hr.py` | Empleados & Comisiones. |

---

## 6. Future / Moonshot
*   `app/services/`: Lógica de negocio pesada que debe migrar a "Agents".

---

## 7. Frontend React SPA

> Toda la UI activa vive en `frontend/src/`. Los templates Jinja2 en `app/templates/` son legacy.

### 7.1 Entry Points

| Archivo | Rol |
|---------|-----|
| `frontend/src/main.tsx` | Punto de entrada React |
| `frontend/src/App.tsx` | Definicion de rutas (React Router v6, lazy loading) |
| `frontend/src/components/layout/Layout.tsx` | Shell principal (Sidebar + Header + Outlet) |
| `frontend/src/components/layout/Sidebar.tsx` | Navegacion lateral con `ROLE_ROUTES` y `ALL_NAV` |

### 7.2 Paginas por Engine

| Engine (Backend) | Paginas (`frontend/src/pages/`) | Rutas |
|---|---|---|
| **Nucleus: HQ** | `hq/HQOperations`, `HQReportsHub`, `HQControl`, `HQSalesLog`, `HQReturns`, `HQInventory`, `HQBranches`, `HQBranchDetail` | `/hq/*` |
| **Nucleus: Admin** | `core/AdminCatalog`, `Users`, `Organization`, `Departments`, `Brands` | `/admin/catalog`, `/users`, `/organization`, `/departments`, `/brands` |
| **Transaction: POS** | `pos/POS`, `pos/DataXPOS`, `pos/Configuracion` | `/pos`, `/dataxpos`, `/configuracion` |
| **Transaction: Ventas** | `sales/SalesHistory`, `Quotes`, `QuoteMaker`, `Returns`, `Seguimiento` | `/sales`, `/quotes`, `/quotes/new`, `/returns`, `/seguimiento` |
| **Transaction: Finanzas** | `finance/CashHistory`, `Reports`, `Purchases`, `Expenses` | `/cash-history`, `/reports`, `/purchases`, `/expenses` |
| **Inventory** | `inventory/Inventory`, `Logistics`, `Boxes`, `Products` | `/inventory`, `/logistics`, `/boxes`, `/products` |
| **Relationship** | `crm/Customers`, `hr/HR`, `hr/HRMe` | `/customers`, `/hr`, `/hr/me` |
| **Mobile** | `mobile/MobileDashboard`, `MobileQuery`, `MobileSales`, `MobileProfile` | `/mobile/*` |
| **Portal** | `portal/Portal` | `/portal` |
| **Platform** | `platform/PlatformMetrics`, `PlatformOrganizations`, `PlatformOrgDetail`, `PlatformUsers`, `PlatformBranches`, `PlatformPresets`, `PlatformModules`, `PlatformAdmins`, `PlatformAuditLog` | `/platform/*` |

### 7.3 Capa API (`frontend/src/api/`)

| Cliente API | Router(s) Backend |
|---|---|
| `client.ts` | Base Axios (interceptores JWT + org header) |
| `auth.ts` | `auth.py` |
| `sales.ts` | `sales.py` |
| `cash.ts` | `cash.py` |
| `products.ts` | `products.py`, `brands.py`, `departments.py`, `commercial.py` |
| `customers.ts` | `customers.py` |
| `inventory.ts` | `inventory.py` |
| `quotes.ts` | `quotes.py` |
| `returns.ts` | `returns.py` |
| `reports.ts` | `reports.py` |
| `purchases.ts` | `purchases.py` |
| `expenses.ts` | `expenses.py` |
| `hr.ts` | `hr.py` |
| `users.ts` | `users.py` |
| `organization.ts` | `organization.py`, `branches.py` |
| `platform.ts` | `platform.py` |
| `portal.ts` | `portal.py` |
| `printer.ts` | `printer.py` |

### 7.4 Estado Global (`frontend/src/store/`)

| Store | Contenido |
|---|---|
| `authStore.ts` | Sesion de usuario, token JWT, org, branch. Hidrata desde `localStorage`. |
| `posStore.ts` | Carrito, sesion de caja, cliente, pedidos pendientes, estado de procesamiento. |

### 7.5 Componentes Compartidos (`frontend/src/components/`)

| Directorio | Contenido |
|---|---|
| `layout/` | `Layout.tsx` (shell), `Sidebar.tsx` (nav con `ROLE_ROUTES`) |
| `pos/` | `CartPanel`, `CustomerSelector`, `PendingOrders`, `ProductSearch` |
| `pos/modals/` | 6 modales: `CashPayment`, `CardPayment`, `TransferPayment`, `MixedPayment`, `Return`, `Session` |
| `ui/` | `Badge`, `Button`, `DaxCard`, `Spinner` |

### 7.6 Types (`frontend/src/types/`)

| Archivo | Interfaces |
|---|---|
| `auth.ts` | `User`, `Organization`, `Branch`, `Role`, `PlatformRole` |
| `cash.ts` | `CashSession` |
| `products.ts` | Tipos de producto, variante, stock |
| `sales.ts` | `CartItem`, `SalesDocument`, `Payment`, `DocType`, `DocStatus` |
