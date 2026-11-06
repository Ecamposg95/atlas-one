# Atlas BOS — Roles y Módulos

Referencia de todos los tipos de usuario del sistema, su contexto operativo y los módulos a los que tienen acceso.

---

## Niveles del sistema

```
[ PLATAFORMA ]  →  SUPERADMIN  (PaaS — gestión de tenants)
[ APLICACIÓN ]  →  7 roles de negocio  (Atlas POS preset)
```

---

## Nivel Plataforma

### SUPERADMIN
Acceso exclusivo a la consola `/platform/*`. No pertenece a ninguna organización.

| Módulo | URL |
|--------|-----|
| Métricas globales | `/platform/metrics` |
| Organizaciones | `/platform/organizations` |
| Usuarios de plataforma | `/platform/users` |
| Admins | `/platform/admins` |
| Sucursales globales | `/platform/branches` |
| Presets | `/platform/presets` |

---

## Nivel Aplicación (Atlas POS)

Contextos operativos:
- **HQ** — sede central, visibilidad global de la organización
- **BRANCH** — sucursal específica (tienda, almacén, oficina)
- **MOBILE** — acceso desde dispositivo móvil

---

### ADMINISTRADOR
**Contexto:** HQ · Redirige a `/command-center` al login

| Grupo | Módulo | URL |
|-------|--------|-----|
| Inicio | Panel de Control | `/command-center` |
| Catálogo | Productos (Admin) | `/admin/catalog` |
| Catálogo | Departamentos | `/departments` |
| Catálogo | Marcas & Empaques | `/brands` |
| Ventas | Ventas HQ | `/hq/sales` |
| Ventas | Cotizaciones | `/quotes` |
| Ventas | Nueva Cotización | `/quotes/new` |
| Ventas | Pedidos | `/seguimiento` |
| Ventas | Devoluciones | `/returns` |
| Finanzas | Compras | `/purchases` |
| Finanzas | Gastos | `/expenses` |
| Inventario | Inventario | `/inventory` |
| Inventario | Inventario por Sucursal | `/hq/inventory` |
| Inventario | Logística | `/logistics` |
| Clientes | Clientes / CRM | `/customers` |
| Organización | Empresa y Sucursales | `/organization` |
| Organización | Sucursales HQ | `/hq/branches` |
| Organización | Usuarios | `/users` |
| Organización | Recursos Humanos | `/hr` |
| — | Mi Expediente | `/hr/me` |

---

### DUEÑO
**Contexto:** HQ · Redirige a `/command-center` al login · Alcance reducido vs. Administrador

| Grupo | Módulo | URL |
|-------|--------|-----|
| Catálogo | Productos (Admin) | `/admin/catalog` |
| Ventas | Ventas HQ | `/hq/sales` |
| Ventas | Cotizaciones | `/quotes` |
| Ventas | Nueva Cotización | `/quotes/new` |
| Ventas | Pedidos | `/seguimiento` |
| Ventas | Devoluciones | `/returns` |
| Finanzas | Compras | `/purchases` |
| Finanzas | Gastos | `/expenses` |
| Inventario | Inventario | `/inventory` |
| Inventario | Logística | `/logistics` |
| Clientes | Clientes / CRM | `/customers` |
| — | Mi Expediente | `/hr/me` |

> El Dueño **no tiene acceso** a: Departamentos, Marcas, Inventario por Sucursal, Sucursales HQ, Usuarios, RRHH, Empresa y Sucursales.

---

### GERENTE
**Contexto:** BRANCH · Redirige a `/dataxpos` al login

| Grupo | Módulo | URL |
|-------|--------|-----|
| POS | Punto de Venta | `/pos` |
| POS | Historial Ventas | `/sales` |
| POS | Cortes de Caja | `/cash-history` |
| POS | Pedidos Móviles | `/pos/inbox` |
| POS | Consulta Productos | `/products` |
| POS | Devoluciones | `/returns` |
| POS | Reportes | `/api/reports/sales-summary` |
| — | Mi Expediente | `/hr/me` |

---

### CAJERO
**Contexto:** BRANCH · Redirige a `/pos` al login (módulo principal)

| Grupo | Módulo | URL |
|-------|--------|-----|
| POS | **Punto de Venta** | `/pos` |
| POS | Historial Ventas | `/sales` |
| POS | Cortes de Caja | `/cash-history` |
| POS | Pedidos Móviles | `/pos/inbox` |
| POS | Consulta Productos | `/products` |
| POS | Devoluciones | `/returns` |
| POS | Configuración | `/configuracion` |
| — | Mi Expediente | `/hr/me` |

> El Cajero **no tiene acceso** a Reportes. Puede ver productos pero no editarlos (solo consulta).

---

### VENDEDOR
**Contexto:** MOBILE · Interfaz optimizada para celular

| Módulo | URL |
|--------|-----|
| Dashboard Móvil | `/mobile/dashboard` |
| Consulta Móvil | `/mobile/query` |
| Venta Móvil | `/mobile/sales` |
| Perfil Móvil | `/mobile/profile` |
| Mi Expediente | `/hr/me` |

---

### SOPORTE_OPERATIVO
**Contexto:** MOBILE · Solo consulta, sin capacidad de venta

| Módulo | URL |
|--------|-----|
| Dashboard Móvil | `/mobile/dashboard` |
| Consulta Móvil | `/mobile/query` |
| Perfil Móvil | `/mobile/profile` |
| Mi Expediente | `/hr/me` |

> No tiene acceso a `Venta Móvil`. Solo consulta de información.

---

### CLIENTE
**Contexto:** Portal web

| Módulo | URL |
|--------|-----|
| Portal Clientes | `/portal/dashboard` |

---

## Tabla comparativa rápida

| Módulo | ADMIN | DUEÑO | GERENTE | CAJERO | VENDEDOR | SOPORTE | CLIENTE |
|--------|:-----:|:-----:|:-------:|:------:|:--------:|:-------:|:-------:|
| Panel de Control HQ | ✓ | — | — | — | — | — | — |
| Productos (Admin) | ✓ | ✓ | — | — | — | — | — |
| Departamentos | ✓ | — | — | — | — | — | — |
| Marcas & Empaques | ✓ | — | — | — | — | — | — |
| Ventas HQ | ✓ | ✓ | — | — | — | — | — |
| Cotizaciones | ✓ | ✓ | — | — | — | — | — |
| Pedidos | ✓ | ✓ | — | — | — | — | — |
| Devoluciones | ✓ | ✓ | ✓ | ✓ | — | — | — |
| Compras | ✓ | ✓ | — | — | — | — | — |
| Gastos | ✓ | ✓ | — | — | — | — | — |
| Inventario | ✓ | ✓ | — | — | — | — | — |
| Inv. por Sucursal | ✓ | — | — | — | — | — | — |
| Logística | ✓ | ✓ | — | — | — | — | — |
| Clientes / CRM | ✓ | ✓ | — | — | — | — | — |
| Empresa / Org | ✓ | — | — | — | — | — | — |
| Sucursales HQ | ✓ | — | — | — | — | — | — |
| Usuarios | ✓ | — | — | — | — | — | — |
| RRHH | ✓ | — | — | — | — | — | — |
| Mi Expediente | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — |
| POS | — | — | ✓ | ✓ | — | — | — |
| Historial Ventas | — | — | ✓ | ✓ | — | — | — |
| Cortes de Caja | — | — | ✓ | ✓ | — | — | — |
| Pedidos Móviles | — | — | ✓ | ✓ | — | — | — |
| Consulta Productos | — | — | ✓ | ✓ | — | — | — |
| Config. Impresora | — | — | — | ✓ | — | — | — |
| Reportes Sucursal | — | — | ✓ | — | — | — | — |
| Dashboard Móvil | — | — | — | — | ✓ | ✓ | — |
| Consulta Móvil | — | — | — | — | ✓ | ✓ | — |
| Venta Móvil | — | — | — | — | ✓ | — | — |
| Portal Clientes | — | — | — | — | — | — | ✓ |

---

## Notas de implementación

- La fuente de verdad es `app/core/role_permissions.py` → `DATAXPOS_ROLE_VIEWS`
- El archivo `app/core/role_matrix.py` es **legacy** — no usar
- RBAC se aplica en dos capas: UI (sidebar/launcher) y API (routers)
- `branch_id = None` = usuario HQ con visibilidad global de la organización
- `branch_id != None` = usuario de sucursal, datos filtrados por su sucursal
