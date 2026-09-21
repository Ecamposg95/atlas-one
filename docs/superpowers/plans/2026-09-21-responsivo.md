# Responsivo en teléfono y tablet Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que una cajera pueda vender, cobrar y cerrar caja desde un teléfono (390×844, con teclado abierto) y que un administrador pueda dar de alta y editar productos, usuarios y Empresa, sin campos ni botones fuera de pantalla ni desplazamiento horizontal de la página.

**Architecture:** Correcciones de maquetación Tailwind/CSS sobre el frontend existente; sin cambios de API. Base común primero (CSS global, armazón, molde de modales), luego dos olas independientes por conjunto de archivos.

**Tech Stack:** React 18 + Tailwind (breakpoints `sm` 640 / `md` 768 / `lg` 1024), CSS en `src/index.css`.

**Spec:** los dos informes de auditoría con file:line y fix por hallazgo — **léelos completos antes de tocar nada**:
- `/mnt/d/Devs/atlas-one/.superpowers/sdd/responsive-audit/cajera-findings.md`
- `/mnt/d/Devs/atlas-one/.superpowers/sdd/responsive-audit/admin-findings.md`

## Global Constraints

- Ninguna pantalla puede desplazarse horizontalmente en 390 px: solo tablas/matrices dentro de su propio contenedor `overflow-x-auto` (usa `TablaDesplazable` donde ya exista).
- Inputs con `font-size` ≥ 16 px en pantallas táctiles (evita el zoom de iOS); objetivos táctiles ≥ 44 px en el flujo de cobro y en botones de acción.
- Alturas de pantalla completa con `dvh` (`h-dvh`/`min-h-dvh`) y `env(safe-area-inset-*)` en barras fijas; nunca `100vh` nuevo.
- Modales: `max-h-[90dvh]` + `overflow-y-auto` en la tarjeta, botones de acción visibles con el teclado abierto (o tarjeta como bottom-sheet en `< md`).
- En escritorio (≥ 1024 px) todo debe verse **igual que hoy**: los cambios van detrás de breakpoints (`max-md:`, `md:`) o son neutrales.
- Sin dependencias nuevas. Verificación: `npx vitest run && npx tsc --noEmit && npm run build` desde `frontend/`; en el reporte, para cada pantalla tocada, describe el layout resultante a 390 px y a 768 px leyendo las clases (no hay navegador).
- Commits con `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` y `Claude-Session: https://claude.ai/code/session_01Lug2gDi7z3wjW7VJyjctTb`.

---

### Task 1: Base común — CSS global, armazón y molde de modales

**Files:** `frontend/src/index.css`, `frontend/src/components/layout/Layout.tsx`, `frontend/src/components/layout/Sidebar.tsx` (solo `h-screen`→`h-dvh` y `ROLE_ROUTES` de ADMINISTRADOR/DUEÑO: añadir `/mobile/owner`), el hook `useIsMobile` (que 768 cuente como móvil: `< 1024`? — lee admin-findings I-11 y decide el umbral; documenta), y un molde reutilizable para modales: clase `.dax-modal` en `index.css` (`max-h-[90dvh] overflow-y-auto` + `sm:` centrado / `max-sm:` bottom-sheet con `rounded-t-2xl` y `pb-[env(safe-area-inset-bottom)]`) que las olas 2 y 3 aplican.

- [ ] `index.css`: `@media (pointer: coarse) { .dax-input, select.dax-input, textarea.dax-input { font-size: 16px } }` (cajera I1 / admin C-7); `.dax-modal` como arriba; revisa `index.css:586` (botones forzados a 44 px bajo md) para que no rompa toolbars (admin C-4) — mantenlo pero permite `min-h` en vez de `h` fija.
- [ ] `Layout.tsx`: `h-screen`→`h-dvh`, `overflow-hidden` solo donde haga falta; `padding-bottom: env(safe-area-inset-bottom)` en el contenedor de contenido; el cajón off-canvas conserva su comportamiento.
- [ ] Commit `fix(ui): base responsiva — inputs sin zoom, alturas dvh, molde de modales`.

### Task 2: Flujo de cajera (POS, carrito, cobro, corte)

**Files:** `frontend/src/pages/pos/POS.tsx`, `frontend/src/components/pos/CartPanel.tsx`, `frontend/src/components/pos/modals/CashPaymentModal.tsx` y `CardPaymentModal.tsx`, `frontend/src/components/pos/modals/CustomerModal.tsx`, el modal de apertura/cierre de caja (teclado de denominaciones), `frontend/src/pages/pos/PrinterSettings.tsx` si el informe lo marca.

- [ ] POS: en `< md` el POS pasa a **una columna** con pestañas o un bottom-sheet para el carrito (badge con el número de artículos y el total; botón "Ver carrito" fijo abajo con safe-area); en `≥ md` se queda el reparto de hoy. Quita `min-w-[420px]`/`flex-shrink-0` en `< md`. Barra de acciones: solo iconos con `aria-label` en `< md` (C6).
- [ ] CartPanel: fila de artículo en dos líneas en `< md` (nombre completo arriba; cantidad, precio y total abajo) con `flex-wrap`; controles ±, eliminar ≥ 44 px; grid de métodos de pago `grid-cols-2` en `< sm`, `grid-cols-4` en `≥ sm`.
- [ ] CashPaymentModal / CardPaymentModal: aplicar `.dax-modal`; el teclado numérico y el botón "Cobrar" siempre visibles (botón en pie sticky dentro de la tarjeta); `inputMode="decimal"`.
- [ ] Apertura/cierre de caja: teclado de denominaciones con botones ≥ 44 px y `grid-cols-3` en `< sm` (I3).
- [ ] Commit `fix(pos): venta y cobro completos en teléfono`.

### Task 3: Flujo de administrador (formularios, tablas, catálogo)

**Files:** `frontend/src/pages/inventory/Products.tsx` (toolbar, botones hover-only, modal de alta/edición), `frontend/src/components/products/ProductTieredPricesSection.tsx`, `ProductVariantsEditor.tsx`, `ProductVariantsSection.tsx`, `frontend/src/pages/products/ProductForm.tsx`, `frontend/src/pages/core/AdminCatalog.tsx`, `frontend/src/pages/core/Users.tsx`, `frontend/src/pages/core/Organization.tsx`, `frontend/src/pages/core/{Brands,Departments}.tsx`, `frontend/src/pages/hq/*.tsx` según el informe, `frontend/src/components/catalog/ProductBranchMatrix.tsx`.

- [ ] Rejillas de precios/escalones y empaques: `grid-cols-1 sm:grid-cols-[...]` con etiquetas por campo en `< sm` (C-1).
- [ ] Toolbars: `flex-wrap` + `gap-2`, texto oculto en `< sm` con iconos y `aria-label` (C-3).
- [ ] Botones de editar visibles siempre en táctil: `opacity-100` bajo `md` o `@media (hover: none)` (C-5).
- [ ] Tablas anchas (`AdminCatalog`, inventario, usuarios, sucursales) dentro de `TablaDesplazable` con la primera columna sticky donde el informe lo pide (C-4, I-2, I-3).
- [ ] `ProductVariantsEditor`: filas de talla como tarjetas apiladas en `< md` (C-6).
- [ ] Modales de Users/Brands/Departments/Products: `.dax-modal` (C-2).
- [ ] Commit `fix(admin): formularios, tablas y modales usables en teléfono`.
