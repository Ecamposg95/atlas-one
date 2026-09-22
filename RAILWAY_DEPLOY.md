# Guía de Despliegue — Atlas API en Railway

> ⚠️ **Histórica, ya no describe producción.** Desde el 2026-09-22, producción es el
> VPS IONOS (`https://app.atlasone.com.mx`), desplegado automáticamente por CI/CD en
> cada push a `main` — ver [`docs/DEPLOY.md`](docs/DEPLOY.md). Railway dejó de servir a
> Novedades Kaory ese día; el proyecto de Railway sigue existiendo (por `rmazh`, ver
> [`docs/infra/deployment-map.md`](docs/infra/deployment-map.md)) pero **no** es la
> puerta de Atlas One. Se conserva esta guía porque el significado de cada variable de
> entorno y el comportamiento de `railway_init.py` siguen siendo los mismos en el VPS —
> solo cambió dónde se capturan las variables y quién dispara el build.

## Requisitos Previos

- Cuenta en [Railway](https://railway.app)
- Repositorio GitHub conectado a Railway
- PostgreSQL provisionado en Railway (o externo)

---

## 1. Crear Proyecto en Railway

1. Ir a [railway.app/new](https://railway.app/new)
2. Seleccionar **"Deploy from GitHub Repo"**
3. Conectar el repositorio `Atlas-API`
4. Railway detecta automáticamente el builder (hoy **Railpack**, antes Nixpacks)

---

## 2. Provisionar Base de Datos PostgreSQL

### Opción A: PostgreSQL en Railway (recomendado)
1. En el proyecto, click **"+ New"** → **"Database"** → **"PostgreSQL"**
2. Railway crea la instancia y genera automáticamente la variable `DATABASE_URL`
3. En el servicio de Atlas-API, ir a **Variables** → verificar que `DATABASE_URL` apunte al PostgreSQL interno

### Opción B: PostgreSQL Externo
1. En **Variables** del servicio, agregar manualmente:
   ```
   DATABASE_URL=postgresql://usuario:password@host:5432/nombre_db
   ```

> **Nota:** Si la URL empieza con `postgres://` (sin `ql`), la app la convierte automáticamente a `postgresql://`.

---

## 3. Configurar Variables de Entorno

En el servicio de Atlas-API → **Variables**, agregar:

| Variable | Obligatoria | Valor | Descripción |
|----------|-------------|-------|-------------|
| `DATABASE_URL` | Sí | `postgresql://...` | Conexión a PostgreSQL |
| `SECRET_KEY` | **Sí en producción** | `openssl rand -hex 32` | Firma los JWT. Ver la advertencia abajo |
| `LOG_LEVEL` | No | `INFO` | **En MAYÚSCULAS.** Con `info` uvicorn muere con `ValueError: Unknown level` |
| `INIT_USERS_ON_BOOT` | No | `true` | Solo primera vez: crea datos de prueba (QA org, usuarios, productos) |
| `CLOUDINARY_URL` | No | `cloudinary://...` | Sin ella las imágenes van a disco local en `app/static/` |
| `CLOUDINARY_CLOUD_NAME` | No | `tu_cloud_name` | Para subir imágenes de productos |
| `CLOUDINARY_UPLOAD_PRESET` | No | `tu_preset` | Preset de Cloudinary (unsigned) |

> ### ⚠️ `SECRET_KEY` sin definir en producción
>
> `app/core/security/config.py` cae a
> `_DEFAULT_SECRET = "atlas_erp_secret_key_change_me_in_prod"` cuando la variable
> no existe. **Producción hoy no la define**, así que los JWT de un negocio real
> se firman con un secreto que está en este repositorio: cualquiera con acceso al
> código puede falsificar una sesión válida.
>
> Se corrige agregando la variable en Railway. Al hacerlo se invalidan las
> sesiones abiertas y los usuarios tendrán que volver a entrar, así que conviene
> fuera del horario de la tienda.

---

## 4. Proceso de Build

Railway usa **Railpack** (sucesor de Nixpacks). `nixpacks.toml` se conserva como
referencia del toolchain; el `Dockerfile` de la raíz es para el VPS y **no debe
llegar a `main`**, porque Railway lo prioriza sobre Railpack:

```
Python 3.11
+ build-essential, pkg-config
+ libcairo2-dev, libpango1.0-dev (para PDF)
+ libpq-dev (para PostgreSQL)
```

**Build sequence:**
1. Detecta Python 3.11
2. Instala paquetes del sistema (cairo, pango, PostgreSQL headers)
3. Crea virtualenv en `/opt/venv`
4. `pip install -r requirements.txt` (~80 paquetes)
5. Copia código a `/app`

**Tiempo estimado de build:** 90-120 segundos

---

## 5. Proceso de Startup

Al iniciar, Railway ejecuta (definido en `railway.json`):

```bash
python scripts/railway_init.py && uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

### `railway_init.py` hace (en orden):

| Paso | Acción | Idempotente |
|------|--------|-------------|
| 1 | `Base.metadata.create_all()` — Crea tablas si no existen | Sí |
| 2 | Migraciones incrementales — Agrega columnas nuevas (verifica antes de agregar) | Sí |
| 3 | Crea usuario `superadmin` (pass: `784512`) si no existe | Sí |
| 4 | Crea organización "Rmazh" (DATAXPOS) si no existe | Sí |
| 5 | Vincula superadmin a la organización | Sí |
| 6 | Habilita módulos DATAXPOS para la organización | Sí |
| 7 | Crea preset de industria DATAXPOS | Sí |

> **Todas las operaciones son idempotentes** — se pueden ejecutar múltiples veces sin duplicar datos.

### Después de `railway_init.py`:
- Uvicorn arranca en el `$PORT` asignado por Railway
- Healthcheck: Railway verifica que el servicio responda en el puerto

---

## 6. Primer Acceso

### Login como Superadmin
1. Ir a `https://tu-app.railway.app/login`
2. Credenciales por defecto:
   - **Usuario:** `superadmin`
   - **Contraseña:** `784512`
3. Accedes al panel de plataforma (`/platform/organizations`)

### Configurar la Organización
1. Desde `/platform/organizations`, crear o verificar tu organización
2. Asignar tipo de industria (DATAXPOS recomendado)
3. Aplicar preset de módulos
4. Crear sucursales (HQ + tiendas)
5. Crear usuarios por sucursal

### Datos de Prueba (Opcional)
Si configuraste `INIT_USERS_ON_BOOT=true`, al arrancar se crearon:
- Organización "QA" con 3 sucursales
- Usuarios de prueba por rol (admin, gerente, cajero, vendedor)
- 20 productos de ejemplo con inventario
- 3 clientes de prueba

> **Importante:** Después del primer arranque, **quita** `INIT_USERS_ON_BOOT` de las variables para evitar que se ejecute en cada deploy.

---

## 7. URLs del Sistema

| Ruta | Descripción | Acceso |
|------|-------------|--------|
| `/login` | Página de login | Público |
| `/platform/organizations` | Panel SaaS (superadmin) | SUPERADMIN |
| `/platform/metrics` | Métricas globales | SUPERADMIN |
| `/command-center` | Dashboard HQ | ADMINISTRADOR, DUEÑO |
| `/pos` | Punto de Venta | CAJERO, GERENTE |
| `/products` | Catálogo de productos | Según rol |
| `/sales` | Historial de ventas | GERENTE+ |
| `/cash-history` | Control de caja | CAJERO+ |
| `/api/docs` | Documentación API (Swagger) | Público |

---

## 8. Monitoreo y Mantenimiento

### Logs
- Railway Dashboard → tu servicio → **Logs** (tiempo real)
- Buscar errores con: `ERROR`, `FAILED`, `HTTPException`

### Healthcheck
- Railway verifica automáticamente que el servicio responda
- Si falla 3 veces seguidas → reinicio automático (máximo 10 reintentos)

### Redeploy
- **Automático:** Cada push a la rama conectada dispara un nuevo build
- **Manual:** En Railway Dashboard → **Redeploy** button

### Rollback
- Railway Dashboard → **Deployments** → click en un deploy anterior → **Rollback**

---

## 9. Solución de Problemas Comunes

### Build falla con `ModuleNotFoundError`
- Verificar que el paquete esté en `requirements.txt`
- Revisar `nixpacks.toml` por paquetes del sistema faltantes (referencia del toolchain)

### `NameError` o `ImportError` al arrancar
- Revisar logs de deploy en Railway
- Error de orden de imports en `app/main.py` — verificar que variables se definan antes de usarse

### La app no conecta a PostgreSQL
- Verificar `DATABASE_URL` en Variables
- Asegurar que el PostgreSQL de Railway esté corriendo
- Si es externo: verificar firewall y credenciales

### Los productos no aparecen en POS
- Verificar que la sucursal tenga productos habilitados (`ProductBranchStatus`)
- Desde superadmin: `/platform/organizations/{id}` → verificar módulos activos
- Ejecutar preset si la organización no tiene módulos

### Corte de caja muestra valores incorrectos
- Verificar que `total_change_given` esté calculado (columna agregada por migración)
- Los valores se recalculan en cada consulta desde los pagos

---

## 10. Scripts Útiles

### Resetear la base de datos (DESTRUCTIVO)
```bash
# Interactivo (pide confirmación)
python scripts/reset_db.py

# Sin confirmación
python scripts/reset_db_force.py
```
> **ADVERTENCIA:** Esto borra TODOS los datos. Solo usar en desarrollo.

### Cargar presets de industria
```bash
python scripts/init_presets_v2.py
```

### Crear superadmin manualmente
```bash
python scripts/init_sa.py
```

### Cargar datos de prueba (QA)
```bash
python scripts/init_users.py
```

### Correr tests
```bash
DATABASE_URL="sqlite:///file::memory:?cache=shared" pytest tests/ -v
```

---

## 11. Arquitectura de Deploy

```
GitHub Push
    ↓
Railway Build (Railpack)
    ↓
Python 3.11 + System Deps
    ↓
pip install requirements.txt
    ↓
railway_init.py (DB setup + migrations)
    ↓
uvicorn app.main:app --port $PORT
    ↓
Healthcheck → ✅ Deploy completo
```

### Ramas y Ambientes

> **Desactualizado desde 2026-09-22.** `staging` se unificó a `main` (fast-forward) y
> ya no existe como destino de despliegue; producción se cortó de Railway al VPS IONOS.
> Ver [`docs/DEPLOY.md`](docs/DEPLOY.md) y [`docs/branching-strategy.md`](docs/branching-strategy.md)
> para el esquema vigente (un solo tronco, CI/CD a IONOS). Tabla histórica, sin tocar:

| Rama | Destino | Auto-deploy |
|------|---------|-------------|
| `main` | Railway `atlas-bos` producción — **cliente real cobrando** | Sí |
| `staging` | VPS IONOS (`app.atlasone.com.mx`) | No (rsync manual) |

El entorno `staging` de Railway se eliminó el 2026-07-28; su contenido corre
ahora en el VPS. Ver [`docs/infra/deployment-map.md`](docs/infra/deployment-map.md).

---

## 12. Variables de Entorno (Referencia Completa)

| Variable | Default | Requerida | Uso |
|----------|---------|-----------|-----|
| `DATABASE_URL` | `sqlite:///./sql_app.db` | Sí (prod) | Conexión PostgreSQL |
| `PORT` | Asignado por Railway | Auto | Puerto del servidor |
| `INIT_USERS_ON_BOOT` | `false` | No | Bootstrap datos QA |
| `CLOUDINARY_CLOUD_NAME` | `""` | No | CDN imágenes |
| `CLOUDINARY_UPLOAD_PRESET` | `""` | No | Preset de upload |
