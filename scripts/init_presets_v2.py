"""
Atlas One Presets Seed (v3 — 2026-05-13).

Seeds the module catalog (21+ modules) and the 7 Atlas One presets:
ATLAS_POS, ATLAS_ONE_RETAIL, ATLAS_ONE_BEAUTY, ATLAS_ONE_GASTRO,
ATLAS_ONE_SERVICES, ATLAS_ONE_ENTERPRISE, CUSTOM.

Idempotent: upserts by key/industry_type. Does NOT delete legacy
presets (DISTRIBUTOR_POS, RETAIL_CHAIN, RESTAURANT_*, etc.) —
cleanup is manual via SQL.
"""
import logging
import os
import sys

sys.path.append(os.getcwd())

from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.modules import IndustryPreset, Module, ModuleScope, ModuleStatus

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ── Module catalog ────────────────────────────────────────────────────────────
MODULES_CATALOG = [
    ("core", "Core", "Funcionalidades base del sistema", ModuleScope.GLOBAL, ModuleStatus.STABLE),
    ("pos", "Punto de Venta", "Ventas mostrador, caja, cortes", ModuleScope.GLOBAL, ModuleStatus.STABLE),
    ("cash_management", "Gestión de Caja", "Cortes de caja, arqueos, control de efectivo", ModuleScope.GLOBAL, ModuleStatus.STABLE),
    ("inventory", "Inventario", "Stock, movimientos, kardex", ModuleScope.GLOBAL, ModuleStatus.STABLE),
    ("scanner", "Scanner de tienda", "Lectura con la cámara para cajeros: consulta, precio y conteo en piso", ModuleScope.BRANCH, ModuleStatus.STABLE),
    ("labels", "Etiquetas", "Etiquetas de mostrador para impresora Zebra: selección, copias, vista previa y envío al agente", ModuleScope.BRANCH, ModuleStatus.STABLE),
    ("variants", "Variantes color/talla", "Prendas con varias tallas y colores: matriz de variantes, selector en el POS y existencia por variante", ModuleScope.GLOBAL, ModuleStatus.STABLE),
    ("catalog", "Catálogo", "Productos, servicios, listas de precio", ModuleScope.GLOBAL, ModuleStatus.STABLE),
    ("branch_catalog_enablement", "Habilitación de Catálogo por Sucursal", "Control de productos disponibles por sucursal", ModuleScope.BRANCH, ModuleStatus.STABLE),
    ("returns", "Devoluciones", "Gestión de devoluciones y notas de crédito", ModuleScope.GLOBAL, ModuleStatus.STABLE),
    ("pricing", "Precios", "Gestión de precios y listas de precios", ModuleScope.GLOBAL, ModuleStatus.STABLE),
    ("promotions", "Promociones", "Descuentos, ofertas y promociones", ModuleScope.GLOBAL, ModuleStatus.STABLE),
    ("payments", "Pagos", "Métodos de pago y procesamiento", ModuleScope.GLOBAL, ModuleStatus.STABLE),
    ("crm", "CRM / Clientes", "Gestión de clientes, crédito, fidelidad", ModuleScope.GLOBAL, ModuleStatus.STABLE),
    ("users", "Usuarios", "Control de acceso y roles", ModuleScope.GLOBAL, ModuleStatus.STABLE),
    ("finance", "Finanzas", "Cuentas por cobrar/pagar, gastos", ModuleScope.GLOBAL, ModuleStatus.STABLE),
    ("reports", "Reportes", "Inteligencia de negocios básica", ModuleScope.GLOBAL, ModuleStatus.STABLE),
    ("quotes", "Cotizaciones", "Generación de presupuestos", ModuleScope.GLOBAL, ModuleStatus.STABLE),
    ("workshops", "Taller / Servicio", "Órdenes de servicio y reparación", ModuleScope.GLOBAL, ModuleStatus.STABLE),
    ("kitchen", "Cocina / KDS", "Display de cocina para restaurantes", ModuleScope.BRANCH, ModuleStatus.STABLE),
    ("tables", "Mesas", "Gestión de plano de mesas", ModuleScope.BRANCH, ModuleStatus.STABLE),
    ("menu", "Menú", "Carta visual de productos y modificadores", ModuleScope.BRANCH, ModuleStatus.STABLE),
    ("bar", "Bar / Botellas", "Inventario líquido: servir, rellenar, merma", ModuleScope.BRANCH, ModuleStatus.STABLE),
    ("logistics", "Logística", "Envíos, rutas, paquetería", ModuleScope.GLOBAL, ModuleStatus.STABLE),
    ("manufacturing", "Manufactura", "Producción y ensamblaje", ModuleScope.GLOBAL, ModuleStatus.STABLE),
    ("hr", "Recursos Humanos", "Asistencia, nómina básica", ModuleScope.GLOBAL, ModuleStatus.STABLE),
    # New (2026-05-13)
    ("purchasing", "Compras", "OC, proveedores, recepciones", ModuleScope.GLOBAL, ModuleStatus.STABLE),
    ("appointments", "Agenda", "Citas, disponibilidad, recordatorios", ModuleScope.BRANCH, ModuleStatus.BETA),
    ("commissions", "Comisiones", "Comisiones por servicio o venta", ModuleScope.GLOBAL, ModuleStatus.BETA),
    ("memberships", "Membresías", "Paquetes, créditos y suscripciones", ModuleScope.GLOBAL, ModuleStatus.BETA),
    ("recipes", "Recetas / BOM", "Recetas, ingredientes y costeo por platillo", ModuleScope.GLOBAL, ModuleStatus.STABLE),
    ("ai", "Inteligencia Artificial", "Copilotos, predicciones, automatización", ModuleScope.GLOBAL, ModuleStatus.BETA),
]


# ── Per-module upsell metadata ────────────────────────────────────────────────
MODULE_UPSELL = {
    "crm": {
        "category": "advanced",
        "recommended_presets": ["ATLAS_ONE_RETAIL", "ATLAS_ONE_BEAUTY", "ATLAS_ONE_GASTRO", "ATLAS_ONE_SERVICES"],
        "value_props": [
            "Base de datos de clientes",
            "Historial de compras",
            "Crédito y fidelización",
        ],
        "upgrade_prompt": "Activa CRM para conocer y fidelizar a tus clientes.",
        "icon": "fa-users",
        "sort_hint": 10,
    },
    "purchasing": {
        "category": "advanced",
        "recommended_presets": ["ATLAS_ONE_RETAIL", "ATLAS_ONE_GASTRO"],
        "value_props": [
            "Órdenes de compra a proveedores",
            "Recepciones e ingresos a inventario",
            "Cuentas por pagar",
        ],
        "upgrade_prompt": "Controla compras y proveedores desde Atlas One.",
        "icon": "fa-truck",
        "sort_hint": 20,
    },
    "promotions": {
        "category": "advanced",
        "recommended_presets": ["ATLAS_ONE_RETAIL"],
        "value_props": [
            "Descuentos por temporada",
            "Promociones 2x1, combos",
            "Cupones por cliente",
        ],
        "upgrade_prompt": "Vende más con promociones inteligentes.",
        "icon": "fa-tag",
        "sort_hint": 30,
    },
    "quotes": {
        "category": "advanced",
        "recommended_presets": ["ATLAS_ONE_RETAIL", "ATLAS_ONE_SERVICES"],
        "value_props": [
            "Presupuestos en PDF",
            "Seguimiento de oportunidades",
            "Conversión a venta",
        ],
        "upgrade_prompt": "Genera cotizaciones profesionales.",
        "icon": "fa-file-invoice-dollar",
        "sort_hint": 40,
    },
    "branch_catalog_enablement": {
        "category": "advanced",
        "recommended_presets": ["ATLAS_ONE_RETAIL"],
        "value_props": [
            "Catálogo distinto por sucursal",
            "Productos visibles solo donde aplican",
        ],
        "upgrade_prompt": "Personaliza el catálogo de cada sucursal.",
        "icon": "fa-store",
        "sort_hint": 50,
    },
    "appointments": {
        "category": "vertical",
        "recommended_presets": ["ATLAS_ONE_BEAUTY", "ATLAS_ONE_SERVICES"],
        "value_props": [
            "Calendario por profesional",
            "Recordatorios automáticos",
            "Bloqueos y disponibilidad",
        ],
        "upgrade_prompt": "Agenda citas y servicios con tus clientes.",
        "icon": "fa-calendar",
        "sort_hint": 60,
    },
    "commissions": {
        "category": "vertical",
        "recommended_presets": ["ATLAS_ONE_BEAUTY", "ATLAS_ONE_SERVICES"],
        "value_props": [
            "Comisiones por servicio o venta",
            "Reportes por profesional",
            "Cálculo automático",
        ],
        "upgrade_prompt": "Paga comisiones justas y automáticas.",
        "icon": "fa-percent",
        "sort_hint": 70,
    },
    "memberships": {
        "category": "vertical",
        "recommended_presets": ["ATLAS_ONE_BEAUTY"],
        "value_props": [
            "Paquetes y créditos",
            "Renovaciones automáticas",
            "Vencimientos y alertas",
        ],
        "upgrade_prompt": "Vende paquetes y membresías con control.",
        "icon": "fa-id-card",
        "sort_hint": 80,
    },
    "kitchen": {
        "category": "vertical",
        "recommended_presets": ["ATLAS_ONE_GASTRO"],
        "value_props": [
            "Pantalla de cocina (KDS)",
            "Comandas digitales",
            "Tiempos por platillo",
        ],
        "upgrade_prompt": "Acelera la cocina con KDS.",
        "icon": "fa-utensils",
        "sort_hint": 90,
    },
    "tables": {
        "category": "vertical",
        "recommended_presets": ["ATLAS_ONE_GASTRO"],
        "value_props": [
            "Plano de mesas",
            "Estatus por mesa",
            "Meseros y propinas",
        ],
        "upgrade_prompt": "Gestiona mesas y meseros profesionalmente.",
        "icon": "fa-chair",
        "sort_hint": 100,
    },
    "recipes": {
        "category": "vertical",
        "recommended_presets": ["ATLAS_ONE_GASTRO"],
        "value_props": [
            "Recetas con costeo",
            "Consumo automático de insumos",
            "Margen por platillo",
        ],
        "upgrade_prompt": "Conoce el costo real de cada platillo.",
        "icon": "fa-book",
        "sort_hint": 110,
    },
    "workshops": {
        "category": "vertical",
        "recommended_presets": ["ATLAS_ONE_SERVICES"],
        "value_props": [
            "Órdenes de trabajo",
            "Estatus por OT",
            "Técnicos asignados",
        ],
        "upgrade_prompt": "Lleva control de órdenes de servicio.",
        "icon": "fa-screwdriver-wrench",
        "sort_hint": 120,
    },
    "logistics": {
        "category": "advanced",
        "recommended_presets": ["ATLAS_ONE_RETAIL", "ATLAS_ONE_ENTERPRISE"],
        "value_props": [
            "Envíos y rutas",
            "Cajas y contenedores",
            "Tracking básico",
        ],
        "upgrade_prompt": "Logística integrada al POS.",
        "icon": "fa-truck-fast",
        "sort_hint": 130,
    },
    "manufacturing": {
        "category": "advanced",
        "recommended_presets": ["ATLAS_ONE_ENTERPRISE"],
        "value_props": [
            "Producción y ensamblaje",
            "Consumo de insumos",
            "BOM y costeo",
        ],
        "upgrade_prompt": "Manufactura ligera integrada.",
        "icon": "fa-industry",
        "sort_hint": 140,
    },
    "hr": {
        "category": "advanced",
        "recommended_presets": ["ATLAS_ONE_ENTERPRISE"],
        "value_props": [
            "Asistencia",
            "Nómina básica",
            "Vacaciones",
        ],
        "upgrade_prompt": "Recursos Humanos integrado.",
        "icon": "fa-users-gear",
        "sort_hint": 150,
    },
    "finance": {
        "category": "advanced",
        "recommended_presets": ["ATLAS_ONE_RETAIL", "ATLAS_ONE_ENTERPRISE"],
        "value_props": [
            "Cuentas por cobrar y pagar",
            "Gastos",
            "Conciliaciones",
        ],
        "upgrade_prompt": "Lleva las finanzas dentro de Atlas One.",
        "icon": "fa-coins",
        "sort_hint": 160,
    },
    "ai": {
        "category": "vertical",
        "recommended_presets": ["ATLAS_ONE_ENTERPRISE"],
        "value_props": [
            "Copiloto de ventas",
            "Predicciones de demanda",
            "Automatizaciones",
        ],
        "upgrade_prompt": "Agrega IA a tu operación.",
        "icon": "fa-microchip",
        "sort_hint": 170,
    },
}


# ── Preset compositions ───────────────────────────────────────────────────────
ATLAS_POS_MODS = [
    "core", "pos", "cash_management", "catalog", "inventory",
    "returns", "pricing", "payments", "reports",
]

PRESETS = [
    {
        "id": "ATLAS_POS",
        "name": "Atlas POS",
        "desc": "Punto de venta de entrada: ventas, caja, catálogo, inventario, precios, devoluciones y reportes.",
        # `labels` y `crm` van aquí y no en ATLAS_POS_MODS: la etiqueta ZPL es
        # de mostrador y no tiene por qué encenderse en los presets de otros
        # giros que reusan la misma base, y `crm` ya lo agrega por su cuenta el
        # preset de retail (meterlo en la base lo duplicaría en esa lista).
        "mods": ATLAS_POS_MODS + ["labels", "crm"],
    },
    {
        # Boutique de ropa/moda: lo mismo que Atlas POS mas el Scanner de tienda
        # visible para cajeros. Es un preset aparte para que activar el scanner en
        # una boutique no toque a las tiendas que operan con ATLAS_POS.
        "id": "ATLAS_POS_BOUTIQUE",
        "name": "Atlas POS Boutique",
        "desc": "Boutique de ropa y moda: Atlas POS más scanner con cámara para cajeros.",
        "mods": ATLAS_POS_MODS + ["scanner", "variants", "labels", "crm"],
    },
    {
        "id": "ATLAS_ONE_RETAIL",
        "name": "Atlas One Retail",
        "desc": "Retail multi-sucursal: ferreterías, abarrotes, farmacias, papelerías, refaccionarias.",
        "mods": ATLAS_POS_MODS + ["crm", "branch_catalog_enablement", "purchasing", "promotions", "quotes"],
    },
    # ── Legacy (taxonomy v1) — display marked so the operator migrates ────────
    {
        "id": "ATLAS_ONE_BEAUTY",
        "name": "Atlas One Beauty (legacy — usar Beauty & Wellness o Barber)",
        "desc": "[LEGACY] Sustituido por ATLAS_ONE_BEAUTY_WELLNESS y ATLAS_ONE_BARBER en taxonomy v2.",
        "deprecated": True,
        "mods": [
            "core", "users", "catalog", "inventory", "payments",
            "cash_management", "crm", "pos",
            "appointments", "commissions", "memberships",
            "reports",
        ],
    },
    {
        "id": "ATLAS_ONE_GASTRO",
        "name": "Atlas One Gastro (legacy — usar Restaurant, Café o Bar)",
        "desc": "[LEGACY] Sustituido por ATLAS_ONE_RESTAURANT, ATLAS_ONE_CAFE y ATLAS_ONE_BAR en taxonomy v2.",
        "deprecated": True,
        "mods": [
            "core", "users", "catalog", "inventory", "payments",
            "cash_management", "crm", "pos",
            "kitchen", "tables", "menu", "bar", "recipes",
            "reports",
        ],
    },

    # ── Taxonomy v2 (2026-05-15) — vertical-specific presets ──────────────────
    {
        "id": "ATLAS_ONE_BARBER",
        "name": "Atlas One Barber",
        "desc": "Barberías masculinas: cortes, barba, diseño y paquetes para hombre.",
        "mods": [
            "core", "users", "catalog", "payments", "cash_management", "crm", "pos",
            "appointments", "commissions", "memberships", "reports",
        ],
    },
    {
        "id": "ATLAS_ONE_BEAUTY_WELLNESS",
        "name": "Atlas One Beauty & Wellness",
        "desc": "Estéticas, uñas, depilación, maquillaje, spas y wellness no clínico.",
        "mods": [
            "core", "users", "catalog", "inventory", "payments",
            "cash_management", "crm", "pos",
            "appointments", "commissions", "memberships",
            "reports",
        ],
    },
    {
        "id": "ATLAS_ONE_HEALTH",
        "name": "Atlas One Health",
        "desc": "Consultorios médicos, dentales, quiroprácticos, fisio y terapia. Agenda, pacientes, planes de tratamiento.",
        "mods": [
            "core", "users", "catalog", "payments", "cash_management", "crm", "pos",
            "appointments", "commissions", "memberships", "reports",
        ],
    },
    {
        "id": "ATLAS_ONE_RESTAURANT",
        "name": "Atlas One Restaurant",
        "desc": "Restaurantes con mesas, meseros, cocina y recetas costeadas.",
        "mods": [
            "core", "users", "catalog", "inventory", "payments",
            "cash_management", "crm", "pos",
            "kitchen", "tables", "menu", "bar", "recipes", "commissions", "reports",
        ],
    },
    {
        "id": "ATLAS_ONE_CAFE",
        "name": "Atlas One Café",
        "desc": "Cafeterías, bakery y mostrador rápido. Operativa ligera, sin mesas asignadas.",
        "mods": [
            "core", "users", "catalog", "inventory", "payments",
            "cash_management", "crm", "pos",
            "kitchen", "menu", "recipes", "reports",
        ],
    },
    {
        "id": "ATLAS_ONE_BAR",
        "name": "Atlas One Bar",
        "desc": "Bares y cantinas: cocteles, mesas, bartenders con comisión y control de inventario líquido.",
        "mods": [
            "core", "users", "catalog", "inventory", "payments",
            "cash_management", "crm", "pos",
            "tables", "menu", "bar", "recipes", "commissions", "reports",
        ],
    },
    {
        "id": "ATLAS_ONE_SERVICES",
        "name": "Atlas One Services",
        "desc": "Talleres, consultorios, mantenimiento, soporte y operaciones con órdenes de trabajo.",
        "mods": [
            "core", "users", "catalog", "payments", "crm",
            "workshops", "appointments", "quotes", "commissions",
            "reports",
        ],
    },
    {
        "id": "ATLAS_ONE_ENTERPRISE",
        "name": "Atlas One Enterprise",
        "desc": "Implementación completa: multi-sucursal avanzado, IA, integraciones y todos los módulos.",
        "mods": [k for k, *_ in MODULES_CATALOG],
    },
    {
        "id": "CUSTOM",
        "name": "Personalizado",
        "desc": "Configuración manual desde cero. Solo módulos base.",
        "mods": ["core", "users"],
    },
]


def seed_modules_and_presets(db: Session) -> None:
    """Upsert modules (with upsell_metadata) and the 7 Atlas One presets."""
    logger.info("--- Seeding Modules ---")
    for key, name, desc, scope, status in MODULES_CATALOG:
        mod = db.query(Module).filter(Module.key == key).first()
        if not mod:
            mod = Module(key=key, name=name, description=desc, scope=scope, status=status)
            db.add(mod)
            logger.info(f"  + module: {key}")
        else:
            mod.name = name
            mod.description = desc
            mod.status = status
            logger.info(f"  ~ module: {key}")
        mod.upsell_metadata = MODULE_UPSELL.get(key)
    db.commit()

    logger.info(f"--- Seeding {len(PRESETS)} Presets ---")
    for p in PRESETS:
        existing = (
            db.query(IndustryPreset)
            .filter(IndustryPreset.industry_type == p["id"])
            .first()
        )
        if existing:
            existing.display_name = p["name"]
            existing.description = p["desc"]
            existing.modules = p["mods"]
            existing.is_system = True
            existing.is_deprecated = p.get("deprecated", False)
            logger.info(f"  ~ preset: {p['name']}")
        else:
            db.add(
                IndustryPreset(
                    industry_type=p["id"],
                    display_name=p["name"],
                    description=p["desc"],
                    modules=p["mods"],
                    is_system=True,
                    is_deprecated=p.get("deprecated", False),
                )
            )
            logger.info(f"  + preset: {p['name']}")
    db.commit()

    _cleanup_legacy_dataxpos(db)
    _backfill_gastro_modules(db)
    _backfill_labels_module(db)
    _backfill_crm_module(db)


def _backfill_gastro_modules(db: Session) -> None:
    """Backfill de módulos gastro nuevos (menu/bar/recipes) en orgs YA existentes.

    `apply_industry_preset` solo corre al crear una org (o al re-aplicar preset
    manualmente), así que las orgs gastro creadas ANTES de agregar `menu`/`bar`
    al preset no tendrían esas filas en `organization_modules`. Este backfill es
    idempotente y ADITIVO: solo inserta filas faltantes — nunca deshabilita ni
    toca módulos existentes, respetando toggles manuales del cliente.
    """
    from app.models.organization import IndustryType, Organization
    from app.models.modules import OrganizationModule

    backfill = {
        IndustryType.ATLAS_ONE_RESTAURANT: ["menu", "bar"],
        IndustryType.ATLAS_ONE_CAFE:       ["menu", "recipes"],
        IndustryType.ATLAS_ONE_BAR:        ["menu", "bar"],
        IndustryType.ATLAS_ONE_GASTRO:     ["menu", "bar"],
    }
    added = 0
    for industry, keys in backfill.items():
        orgs = db.query(Organization).filter(Organization.industry_type == industry).all()
        for org in orgs:
            for key in keys:
                exists = db.query(OrganizationModule).filter(
                    OrganizationModule.organization_id == org.id,
                    OrganizationModule.module_key == key,
                ).first()
                if not exists:
                    db.add(OrganizationModule(organization_id=org.id, module_key=key, is_enabled=True))
                    added += 1
    db.commit()
    logger.info(f"  ✓ gastro backfill: {added} fila(s) de módulo agregadas")


def _backfill_labels_module(db: Session) -> None:
    """Backfill de `labels` en las orgs POS/boutique que ya existían.

    Mismo caso que el backfill gastro: `apply_industry_preset` solo corre al
    crear la org, así que sin esto una tienda dada de alta antes del 2026-09-22
    tendría el preset con `labels` pero sin la fila en `organization_modules`, y
    sus cajeros verían 403. Idempotente y ADITIVO: solo inserta lo que falta.
    """
    from app.models.organization import IndustryType, Organization
    from app.models.modules import OrganizationModule

    industrias = (IndustryType.ATLAS_POS, IndustryType.ATLAS_POS_BOUTIQUE)
    added = 0
    orgs = db.query(Organization).filter(Organization.industry_type.in_(industrias)).all()
    for org in orgs:
        exists = db.query(OrganizationModule).filter(
            OrganizationModule.organization_id == org.id,
            OrganizationModule.module_key == "labels",
        ).first()
        if not exists:
            db.add(OrganizationModule(organization_id=org.id, module_key="labels", is_enabled=True))
            added += 1
    db.commit()
    logger.info(f"  ✓ labels backfill: {added} fila(s) de módulo agregadas")


def _backfill_crm_module(db: Session) -> None:
    """Backfill de `crm` en las tiendas POS/boutique que ya existían.

    El módulo `crm` llevaba en el catálogo desde siempre pero fuera de los dos
    presets de mostrador, así que la entrada "Clientes" del menú no se veía en
    ninguna tienda POS. Al sumarlo al preset hace falta este backfill: como el
    router de clientes ahora exige `require_module("crm")`, sin la fila en
    `organization_modules` las tiendas dadas de alta antes de este cambio
    verían 403 en toda la pantalla de Clientes. Idempotente y ADITIVO: solo
    inserta lo que falta, nunca deshabilita.
    """
    from app.models.organization import IndustryType, Organization
    from app.models.modules import OrganizationModule

    industrias = (IndustryType.ATLAS_POS, IndustryType.ATLAS_POS_BOUTIQUE)
    added = 0
    orgs = db.query(Organization).filter(Organization.industry_type.in_(industrias)).all()
    for org in orgs:
        exists = db.query(OrganizationModule).filter(
            OrganizationModule.organization_id == org.id,
            OrganizationModule.module_key == "crm",
        ).first()
        if not exists:
            db.add(OrganizationModule(organization_id=org.id, module_key="crm", is_enabled=True))
            added += 1
    db.commit()
    logger.info(f"  ✓ crm backfill: {added} fila(s) de módulo agregadas")


def _cleanup_legacy_dataxpos(db: Session) -> None:
    """Retire the legacy DATAXPOS naming (old commercial name for Atlas POS).

    Idempotent: migrates any organization still flagged DATAXPOS onto ATLAS_POS
    and removes the orphan DATAXPOS row from `industry_presets`. Runs after the
    enum sync in railway_init guarantees ATLAS_POS exists in the PG enum.
    """
    from sqlalchemy import text

    migrated = db.execute(text(
        "UPDATE organization SET industry_type = 'ATLAS_POS' "
        "WHERE CAST(industry_type AS TEXT) = 'DATAXPOS'"
    )).rowcount
    deleted = db.execute(text(
        "DELETE FROM industry_presets WHERE industry_type = 'DATAXPOS'"
    )).rowcount
    db.commit()
    if migrated or deleted:
        logger.info(f"  ✓ DATAXPOS retired (orgs migrated={migrated}, preset rows removed={deleted})")
    else:
        logger.info("  · DATAXPOS already absent")


def main():
    db = SessionLocal()
    try:
        logger.info("🚀 Initializing Atlas One Modules & Presets...")
        seed_modules_and_presets(db)
        logger.info("✅ Done")
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
