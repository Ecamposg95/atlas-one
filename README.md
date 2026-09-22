<div align="center">

# Atlas One
### The all-in-one business suite for physical businesses in LatAm

**A modular suite powered by Atlas BOS to operate, sell, control, and scale your business.**

[![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python)](#)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi)](#)
[![React](https://img.shields.io/badge/React-18-61DAFB?logo=react)](#)
[![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?logo=typescript)](#)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-18-336791?logo=postgresql)](#)
[![Docker](https://img.shields.io/badge/Deploy-CI%2FCD%20%E2%86%92%20IONOS-0B0D0E?logo=docker)](#)
[![PWA](https://img.shields.io/badge/PWA-Instalable-5A0FC8?logo=pwa)](#)

</div>

---

Atlas One es una suite modular todo-en-uno para negocios físicos en México y Latinoamérica. El cliente arranca con **Atlas POS** (preset ligero) y activa progresivamente módulos avanzados: inventario, compras, CRM, citas, operación de restaurante (mesas/cocina/recetas/bar), reportes, IA y enterprise.

> **📚 ¿Buscas documentación técnica?** Empieza por **[`docs/README.md`](docs/README.md)** — el índice de toda la documentación (arquitectura, referencia de API, modelo de datos, RBAC, guías de módulos).

---

## ⚠️ Antes de tocar `main`

**`main` es producción en vivo.** Es tronco único (no hay `staging`, se fusionó a
`main` el 2026-09-22) y un CI/CD (GitHub Actions) la despliega automáticamente al VPS
IONOS en cada push, y hay un negocio real cobrando ahí todos los días. No es una rama
de integración.

- Los PRs nuevos van a **`main`** (no hay rama intermedia)
- Cambios a `main`, fuera del horario de la tienda (opera hasta ~20:00 hora de México) —
  el deploy es inmediato, no hay ventana de aprobación manual
- El `Dockerfile` de la raíz **sí debe estar en `main`**: es el mecanismo de build de
  producción (a diferencia del esquema anterior con Railway)

Detalle completo en [`docs/DEPLOY.md`](docs/DEPLOY.md) y
[`docs/infra/deployment-map.md`](docs/infra/deployment-map.md).

## 🌐 Dónde vive cada cosa

| Destino | Rama | Base de datos |
|---|---|---|
| `app.atlasone.com.mx` | `main` | Postgres 18 en el VPS IONOS — **producción, cliente real** |
| `atlasone.com.mx` | — | Landing estática |

Railway (`atlas-one.up.railway.app`) dejó de servir producción el 2026-09-22, cuando se
cortó el punto de venta de Novedades Kaory al VPS. La Gastro Suite (mesas, comandas,
KDS, recetas, ledger de barra) y el módulo de clientes POS (CRUD + estado de cuenta PDF
+ WhatsApp) se habían promovido de `staging` a `main` el 2026-08-09; `staging` misma se
fusionó a `main` el 2026-09-22, cerrando el esquema de dos ramas.

## 🛠️ Desarrollo local

```bash
docker compose up -d          # Postgres + backend en :8000 con recarga
cd frontend && npm ci && npm run dev   # Vite en :5173, proxy a /api
```

Sin Docker:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL=postgresql://postgres:toor@localhost:5432/railway
uvicorn app.main:app --reload
```

**`LOG_LEVEL` debe ir en MAYÚSCULAS.** `app/main.py` lo pasa directo a `logging`;
con `info` en minúscula uvicorn muere con `ValueError: Unknown level`.

> **Divergencia conocida:** `docker-compose.yml` usa `postgres:17-alpine` y
> producción corre **18.3**, así que un dump de producción no restaura en local.
> Al alinearlo hay que cambiar también el punto de montaje: Postgres 18 espera el
> volumen en `/var/lib/postgresql`, no en `/var/lib/postgresql/data`, o el
> contenedor entra en bucle de reinicio.

### Variables de entorno

| Variable | Efecto si falta |
|---|---|
| `DATABASE_URL` | Requerida |
| `SECRET_KEY` | Usa el default público del repositorio — **ver deuda de seguridad abajo** |
| `LOG_LEVEL` | `INFO` |
| `CLOUDINARY_URL` | Las imágenes van a disco local en `app/static/` |
| `SUPERADMIN_USER` / `SUPERADMIN_PASS` | `superadmin` / `admin123`, solo al crear el usuario |

`scripts/railway_init.py` corre en cada arranque, es idempotente y siembra 13
organizaciones demo con contraseña `demo1234`.

### Notas de la API

`POST /api/auth/login` es **form-encoded** (OAuth2PasswordRequestForm), no JSON.
Con JSON responde 422. El frontend usa `baseURL: '/api'` relativo, así que no
necesita variables `VITE_*` en build time.

## 🔓 Deuda de seguridad — histórica, resuelta en el destino actual

`app/core/security/config.py` usa
`_DEFAULT_SECRET = "atlas_erp_secret_key_change_me_in_prod"` como respaldo de
`SECRET_KEY`. Cuando Railway era producción, no definía la variable y los JWT de un
negocio real se firmaban con un secreto público del repositorio. El VPS IONOS (destino
actual, ver [`docs/DEPLOY.md`](docs/DEPLOY.md)) sí define un `SECRET_KEY` real — ver
`docs/infra/deployment-map.md`. Verifica siempre que cualquier destino nuevo defina la
variable antes de recibir tráfico real.

---

## ⚙️ Powered by Atlas BOS

**Atlas BOS** (*Business Operating System*) es el core técnico detrás de Atlas One: una arquitectura **API-first, multi-tenant y modular** en FastAPI + SQLAlchemy + PostgreSQL en el backend, y React + Vite + TypeScript en el frontend (SPA/PWA).

Una sola base de código sirve a todos los verticales. Un **preset de industria** decide qué módulos se activan para cada organización; el mismo motor opera un abarrotes, un restaurante o un salón de belleza.

---

## 🏗️ Arquitectura de producto

| Capa | Rol | Descripción |
|---|---|---|
| **Atlas One** | Marca comercial | La suite todo-en-uno que ve el cliente. |
| **Atlas BOS** | Core técnico | Motor: API, multi-tenant, RBAC, catálogo de módulos, eventos. |
| **Atlas POS** | Preset ligero | Punto de venta de entrada: ventas, pagos, productos, inventario básico, caja, tickets, reportes. |
| **Presets verticales** | Configuraciones | Retail, Gastro (Restaurant/Café/Bar), Beauty/Services (citas), Enterprise… — cada uno activa un set de módulos. |

## 📚 Documentación

| Documento | Contenido |
|---|---|
| [`docs/DEPLOY.md`](docs/DEPLOY.md) | Despliegue a producción — CI/CD (GitHub Actions) al VPS IONOS |
| [`docs/infra/deployment-map.md`](docs/infra/deployment-map.md) | Qué rama alimenta cada destino |
| [`docs/infra/ionos-vps.md`](docs/infra/ionos-vps.md) | Runbook del VPS `atlas-prod-01` |
| [`docs/branching-strategy.md`](docs/branching-strategy.md) | Ramas, reglas y convenciones |
| [`RAILWAY_DEPLOY.md`](RAILWAY_DEPLOY.md) | Histórico — despliegue en Railway, ya no describe producción |

## 🖨️ Agente de impresión

El agente local que habla con las impresoras térmicas ESC/POS vive en su
propio repositorio, común a todos los productos de Atlas:
<https://github.com/Ecamposg95/Atlas-Print-Agent> (`GET /api/printer/download-agent`
redirige ahí; `ATLAS_PRINT_AGENT_URL` permite apuntar a otro origen). Su configuración
de orígenes permitidos (`ATLAS_AGENT_ORIGINS`) ya no es parte de este repositorio —
verifica el estado actual en el repo del agente antes de asumir cómo valida un dominio
nuevo. Al dar de alta un punto de venta en un dominio propio, confirma con una
impresión real que el agente lo acepta, o la caja seguirá vendiendo sin imprimir
tickets.

<br/>

<div align="center">

**Atlas One — the ultimate operating system for physical business.**

</div>
