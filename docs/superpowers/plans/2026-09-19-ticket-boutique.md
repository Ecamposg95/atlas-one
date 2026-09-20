# Ticket boutique Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** El ticket de venta (térmico, reimpresión y HTML) gana secciones configurables por organización: encabezado personalizado (hoy se edita pero no se imprime), redes sociales, términos y condiciones, y una línea de Atlas como proveedor tecnológico. Todo se configura en Empresa y cada sección se imprime solo si está capturada.

**Architecture:** Columnas nuevas en `organization` (`ticket_terms` TEXT; `ticket_instagram`, `ticket_facebook`, `ticket_tiktok`, `ticket_whatsapp` VARCHAR; `ticket_show_vendor` BOOLEAN NOT NULL DEFAULT TRUE) con ALTERs idempotentes en `scripts/railway_init.py`. `app/pos_printer.py` gana un bloque `_build_boutique_footer(organization, branch)` que emiten `build_ticket_bytes` y `build_reissued_ticket_bytes` después del pie de siempre; `app/templates/print/ticket.html` imprime lo mismo. `frontend/src/pages/core/Organization.tsx` (sección "Encabezado y Pie de Ticket") captura los campos.

**Tech Stack:** FastAPI + SQLAlchemy + Pydantic v2; ESC/POS (FONT_A/FONT_B, BOLD, CENTER); React/TS.

**Spec:** este documento. Pedido del dueño de Eleven Fashion (boutique): ticket completo con términos y condiciones, redes sociales y Atlas como proveedor tecnológico.

## Global Constraints

- Ninguna sección nueva se imprime si el campo está vacío: las organizaciones que no configuren nada reciben exactamente el ticket de hoy (los tests existentes de `tests/test_ticket_layout.py`, `test_ticket_usd.py`, `test_ticket_comision_*.py`, `test_pos_printer.py` no cambian).
- El encabezado personalizado (`ticket_header`) se imprime bajo el nombre del negocio SOLO si está capturado y es distinto del valor heredado "ATLAS POS - Nota de Venta" (seed de todas las orgs): así los clientes actuales no ven una línea nueva sin haberla pedido.
- Latin-1 con `replace` como el resto del ticket; ninguna línea excede `self.cols`; texto largo se envuelve con `_wrap_text`.
- Sin cambios en `create_sale` ni en el agente.
- Tests: `python3 -m pytest -q -p no:warnings --ignore=tests/test_cash_complete.py` (baseline 914 passed, 2 skipped, 3 xfailed); frontend `npx tsc --noEmit && npm run build`.
- Commits con `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` y `Claude-Session: https://claude.ai/code/session_01Lug2gDi7z3wjW7VJyjctTb`.

---

### Task 1: Backend — columnas, schemas, bloque boutique en térmico y HTML

**Files:**
- Modify: `app/modules/tenants/models.py` (bloque "Branding / tickets"), `app/modules/tenants/schemas.py` (`OrganizationBase`/`OrganizationUpdate`/read: los 6 campos), `scripts/railway_init.py` (6 ALTERs en `migrations`, patrón `("organization", "ticket_terms", "ALTER TABLE organization ADD COLUMN ticket_terms TEXT;")`; el booleano `ADD COLUMN ticket_show_vendor BOOLEAN NOT NULL DEFAULT TRUE`), `app/pos_printer.py`, `app/templates/print/ticket.html`.
- Test: `tests/test_ticket_boutique.py` (nuevo). Usa `_make_sale`/`_line`/`_build`/`_decode` de `tests/test_ticket_layout.py` como referencia (cópialos o impórtalos), con `organization = SimpleNamespace(name=…, ticket_header=…, ticket_footer=…, website=…, ticket_terms=…, ticket_instagram=…, ticket_facebook=…, ticket_tiktok=…, ticket_whatsapp=…, ticket_show_vendor=…, logo_url=None, phone=None, legal_name=None)`.

**Interfaces:**
- Produces: `PosPrinter._build_boutique_footer(organization, branch) -> bytes` y los 6 campos en `OrganizationRead`/`OrganizationUpdate`.

- [ ] **Step 1: Tests (fallan primero)** — `tests/test_ticket_boutique.py`:
  1. Sin campos configurados: el ticket es byte-idéntico al de una org con solo `ticket_footer` (compara `_build(sale, organization=org_basica)` contra la misma org con los campos nuevos en `None`/`True`).
  2. Con `ticket_header="Boutique de moda"`: aparece una línea con ese texto después del nombre del negocio; con el valor heredado "ATLAS POS - Nota de Venta" NO aparece.
  3. Redes: con instagram `@elevenfashion`, facebook `Eleven Fashion`, tiktok `@eleven`, whatsapp `55 1234 5678` y `website` `elevenfashion.mx`: aparece un título "SIGUENOS" y una línea por red con prefijo (`Instagram: @elevenfashion`, `Facebook: …`, `TikTok: …`, `WhatsApp: …`, `Web: …`); las vacías no aparecen.
  4. Términos: con un texto de ~300 caracteres aparece el título "TERMINOS Y CONDICIONES" y el texto envuelto; ninguna línea decodificada (quitando bytes ESC) excede `p.cols`; el texto completo se conserva (unir líneas y comparar palabras).
  5. Proveedor: con `ticket_show_vendor=True` aparece "Sistema: Atlas One | Atlas Tech" y "atlasone.com.mx"; con `False` no aparece nada de Atlas.
  6. Orden: pie del negocio → SIGUENOS → TERMINOS → proveedor → `LF*3 + CUT` (verifica índices con `.find`).
  7. Reimpresión: `build_reissued_ticket_bytes` imprime el mismo bloque.
  8. Ticket HTML: renderiza `app/templates/print/ticket.html` con Jinja directo (mira cómo lo hace `tests/test_sale_customer_name.py`) y comprueba que salen términos, redes y la línea de proveedor solo cuando están configurados; el bloque "Software: Atlas One / atlasone.com.mx" existente pasa a depender de `ticket_show_vendor`.
- [ ] **Step 2: Modelo + migración + schemas.**
- [ ] **Step 3: `_build_boutique_footer`** en `pos_printer.py`:
  - Redes: `CENTER`, `BOLD_ON` "SIGUENOS" `BOLD_OFF`, luego una línea por red presente (`Instagram: …`, `Facebook: …`, `TikTok: …`, `WhatsApp: …`, `Web: …` usando `organization.website`), truncadas a `cols`.
  - Términos: separador de guiones, `BOLD_ON` "TERMINOS Y CONDICIONES" `BOLD_OFF`, `LEFT`, texto con `_wrap_text(texto, cols)` línea por línea (normaliza saltos de línea del usuario: cada párrafo se envuelve por separado). Si el ancho es 80 mm usa `FONT_B` para el cuerpo de los términos y restaura `self._default_font` al terminar; en 58 mm deja la fuente por defecto.
  - Proveedor: separador, `CENTER`, "Sistema: Atlas One | Atlas Tech" y "atlasone.com.mx".
  - Emitir el bloque en `build_ticket_bytes` y `build_reissued_ticket_bytes` justo después del pie (`_resolve_footer`) y antes de `LF*3`/cajón/corte. En `_build_compact_header`, tras la línea 1 del nombre, imprimir `ticket_header` según la regla de Global Constraints (usa `getattr(organization, "ticket_header", None)`; el branch puede tener el suyo: `branch.ticket_header` gana si existe).
- [ ] **Step 4: `ticket.html`**: bajo el pie, secciones "Síguenos" (lista) y "Términos y condiciones" (párrafo pequeño, `white-space: pre-line`), y el bloque de proveedor condicionado a `organization.ticket_show_vendor`.
- [ ] **Step 5: Suite completa verde y commit** `feat(ticket): secciones boutique — encabezado, redes, terminos y proveedor`.

---

### Task 2: Frontend — captura en Empresa

**Files:**
- Modify: `frontend/src/pages/core/Organization.tsx` (sección "Encabezado y Pie de Ticket", ~línea 356), `frontend/src/api/organization.ts` o donde viva el tipo de organización (grep `ticket_footer` en `frontend/src/api` y `frontend/src/types`).

**Interfaces:**
- Consumes: los 6 campos de la Tarea 1 por `GET/PUT /api/organization`.

- [ ] **Step 1:** Añadir a la sección de ticket: `textarea` "Términos y condiciones" (ayuda: "Se imprimen al final del ticket. Cambios, garantías, política de devolución…", `rows={5}`), cuatro inputs "Instagram", "Facebook", "TikTok", "WhatsApp" con placeholders (`@tu_tienda`, `Tu Tienda`, `@tu_tienda`, `55 1234 5678`) y nota "El sitio web se toma del campo Sitio web de arriba", y un interruptor "Mostrar «Sistema: Atlas One | Atlas Tech» al pie" (por defecto encendido). Guardar junto con el resto del formulario (`|| null` para vacíos, booleano tal cual).
- [ ] **Step 2:** `npx tsc --noEmit && npm run build`; commit `feat(empresa): terminos, redes y proveedor del ticket`.
