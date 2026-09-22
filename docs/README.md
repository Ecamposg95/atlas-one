# Documentación · Atlas One / Atlas BOS

Índice de la documentación técnica. Distingue **referencia viva** (se mantiene al día con el código) de **historial** (registros fechados que no se actualizan).

## 📖 Referencia viva

| Doc | Qué cubre |
|---|---|
| [`ONTOLOGY.md`](ONTOLOGY.md) | **Ontología de conocimiento**: glosario canónico, grafos de conceptos (dominio/entidades/módulos/eventos/RBAC/presets) e índice concepto→código. Punto de partida para agentes. |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Arquitectura del sistema: capas, arquitectura modular, **eventos/outbox** (comunicación entre módulos), multi-tenancy. |
| [`API_REFERENCE.md`](API_REFERENCE.md) | Catálogo de endpoints (core + platform + módulos) por dominio, con auth/rol/módulo. |
| [`DATA_MODEL.md`](DATA_MODEL.md) | Catálogo de las 73 tablas por dominio, mixins, enums y *gotchas* de esquema. |
| [`RBAC.md`](RBAC.md) | Tipos de usuario (7 roles tenant + 2 platform), auth/JWT, gating por rol y por módulo, tenancy, y huecos de seguridad conocidos. |
| [`FRONTEND_VIEWS.md`](FRONTEND_VIEWS.md) | Mapa de las 76 vistas del frontend (ruta → archivo → roles → API). |
| [`UI_REVIEW.md`](UI_REVIEW.md) | Revisión UI/UX de las 76 vistas (dark+claro, paleta, consistencia) + **plan de ejecución de Fase 5** (fundación de tokens/componentes + reskin por pantalla). |
| [`modules/MODULE_GUIDE.md`](modules/MODULE_GUIDE.md) | Cómo crear/mover un módulo (backend + seed + preset + frontend + tests + migración). |
| [`modules/GASTRO_MESAS_COMANDAS.md`](modules/GASTRO_MESAS_COMANDAS.md) | Feature doc del flujo mesas → comanda → KDS → cuenta → cobro. |
| [`presets/README.md`](presets/README.md) | Cómo crear un preset de industria nuevo (composición de módulos, datos vs. código, checklist). |
| [`presets/BOUTIQUE.md`](presets/BOUTIQUE.md) | Preset `ATLAS_POS_BOUTIQUE`: estándar de datos de producto, ticket, etiquetas, funciones de cajera, checklist de alta. |
| [`platform/superadmin-creation.md`](platform/superadmin-creation.md) | Crear SUPERADMINs de plataforma. |
| [`branching-strategy.md`](branching-strategy.md) | Modelo de ramas y entornos. |
| [`ci-cd/SETUP.md`](ci-cd/SETUP.md) | CI (GitHub Actions) y branch protection. |

## 🗂️ Historial / generado (no es referencia)

- [`audits/`](audits/) — auditorías fechadas (tenant-isolation, platform-orgs, cajero-visibility). Snapshots/baselines, no estado actual.
- [`CHANGELOG-2026-09-boutique.md`](CHANGELOG-2026-09-boutique.md) — bitácora fechada de lo construido para el preset boutique (2026-09-16 → 2026-09-21).
- `superpowers/` — specs, plans y runbooks por feature (historial de ejecución).
- `ATLAS ONE/` — mockups del deck comercial y prototipos `.jsx`/`.html` del sistema de diseño (no es doc técnica).

## 🧭 Rutas de lectura sugeridas

- **Onboarding de dev:** README raíz (inicio rápido) → `ARCHITECTURE.md` → `DATA_MODEL.md` → `RBAC.md`.
- **Trabajar en un módulo:** `modules/MODULE_GUIDE.md` → `API_REFERENCE.md` (endpoints del módulo) → `ARCHITECTURE.md §eventos` si publica/consume eventos.
- **Frontend:** `FRONTEND_VIEWS.md` → `RBAC.md` (gating rol/módulo).

> Los `file:line` y conteos en estos docs son puntos de entrada; verifica contra el código antes de asumir. Última auditoría profunda: julio 2026.
