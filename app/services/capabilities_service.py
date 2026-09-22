from sqlalchemy.orm import Session
from app.models.organization import Organization, IndustryType
from app.models.modules import Module, OrganizationModule, ModuleScope, ModuleStatus

# Wave 2: módulos sin referencia en ningún preset POS-focused tras drop de
# verticals no-POS. Removidos: clinical, services, sales_pipeline,
# fulfillment, pm, documents, purchasing.
# Define module constant keys
MOD_CORE = "core"
MOD_REPORTS = "reports"
MOD_POS = "pos"
MOD_WAREHOUSE = "warehouse"
MOD_QUOTES = "quotes"
MOD_APPOINTMENTS = "appointments"

MOD_CRM = "crm"
MOD_CUSTOMER_PORTAL = "customer_portal"
MOD_INVOICING = "invoicing"
MOD_PAYMENTS = "payments"
MOD_CASH = "cash_management"
MOD_RETURNS = "returns"
MOD_PRICING = "pricing"
MOD_PROMOTIONS = "promotions"
MOD_CATALOG = "catalog"
MOD_BRANCH_CATALOG = "branch_catalog_enablement"
MOD_INVENTORY = "inventory"
MOD_WORK_ORDERS = "work_orders"
MOD_KDS = "kds"
MOD_TABLES = "tables"
MOD_MENU = "menu"
MOD_SCANNER = "scanner"
MOD_LABELS = "labels"
MOD_VARIANTS = "variants"

# Presets by Industry
# Wave 2: enfoque POS multi-sucursal. Industrias de servicios médicos/
# belleza, e-commerce, B2B, manufactura, 3PL, professional services
# removidas. Las filas existentes en BD quedan hasta limpieza manual; este
# fallback dict solo se consulta si la query a `industry_presets` no
# devuelve nada para una industria dada.
INDUSTRY_PRESETS = {
    # Must mirror ATLAS_POS_MODS in scripts/init_presets_v2.py (DB row is the
    # source of truth; this fallback only fires if industry_presets is empty).
    IndustryType.ATLAS_POS: [
        MOD_CORE, MOD_POS, MOD_CASH, MOD_CATALOG, MOD_INVENTORY,
        MOD_RETURNS, MOD_PRICING, MOD_PAYMENTS, MOD_REPORTS, MOD_LABELS,
        MOD_CRM
    ],
    IndustryType.ATLAS_POS_BOUTIQUE: [
        MOD_CORE, MOD_POS, MOD_CASH, MOD_CATALOG, MOD_INVENTORY,
        MOD_RETURNS, MOD_PRICING, MOD_PAYMENTS, MOD_REPORTS, MOD_SCANNER,
        MOD_VARIANTS, MOD_LABELS, MOD_CRM
    ],
    IndustryType.DISTRIBUTOR_POS: [
        MOD_CORE, MOD_REPORTS, MOD_POS, MOD_WAREHOUSE, MOD_QUOTES, MOD_INVENTORY, MOD_CASH, MOD_CATALOG
    ],
    IndustryType.RESTAURANT_QSR: [
        MOD_CORE, MOD_POS, MOD_CASH, MOD_MENU, MOD_KDS, MOD_PAYMENTS, MOD_REPORTS
    ],
    IndustryType.RESTAURANT_FULL: [
        MOD_CORE, MOD_POS, MOD_CASH, MOD_MENU, MOD_KDS, MOD_TABLES,
        MOD_INVENTORY, MOD_CRM, MOD_APPOINTMENTS, MOD_PAYMENTS, MOD_REPORTS
    ],
    IndustryType.AUTO_REPAIR_SHOP: [
        MOD_CORE, MOD_APPOINTMENTS, MOD_WORK_ORDERS, MOD_QUOTES, MOD_INVENTORY, MOD_CRM, MOD_PAYMENTS, MOD_INVOICING, MOD_CUSTOMER_PORTAL, MOD_REPORTS
    ],
    IndustryType.RETAIL_CHAIN: [
        MOD_CORE, MOD_POS, MOD_CASH, MOD_RETURNS, MOD_CATALOG, MOD_BRANCH_CATALOG, MOD_INVENTORY, MOD_WAREHOUSE, MOD_PRICING, MOD_REPORTS
    ],
    IndustryType.CAFE_BAKERY: [
        MOD_CORE, MOD_POS, MOD_MENU, MOD_INVENTORY, MOD_CASH, MOD_PAYMENTS, MOD_REPORTS
    ],
    IndustryType.CUSTOM: [MOD_CORE, MOD_REPORTS]
}

def get_organization_capabilities(db: Session, org_id: int):
    """
    Returns the set of enabled module keys for an organization.
    """
    modules = db.query(OrganizationModule).filter(
        OrganizationModule.organization_id == org_id,
        OrganizationModule.is_enabled == True
    ).all()
    return [m.module_key for m in modules]

def apply_industry_preset(db: Session, org_id: int, industry_type: IndustryType):
    """
    Upserts the organization_modules based on the industry preset.
    Now fetches from the database instead of hardcoded dictionary.
    Falls back to hardcoded INDUSTRY_PRESETS if database is not populated.
    """
    import logging
    from app.models.modules import IndustryPreset

    logger = logging.getLogger(__name__)

    preset = db.query(IndustryPreset).filter(
        IndustryPreset.industry_type == industry_type.value
    ).first()

    if preset:
        preset_modules = preset.modules
    else:
        preset_modules = INDUSTRY_PRESETS.get(industry_type, [MOD_CORE])

    # Filter against the modules catalog FK target; rows in `industry_presets`
    # may carry stale keys (legacy seeds) that violate
    # `organization_modules_module_key_fkey` if inserted blindly.
    valid_keys = {row[0] for row in db.query(Module.key).all()}
    skipped = [k for k in preset_modules if k not in valid_keys]
    if skipped:
        logger.warning(
            "apply_industry_preset: skipping %d unknown module key(s) for org=%s industry=%s: %s",
            len(skipped), org_id, industry_type.value, sorted(set(skipped)),
        )
    accepted = [k for k in preset_modules if k in valid_keys]

    for module_all in accepted:
        org_mod = db.query(OrganizationModule).filter(
            OrganizationModule.organization_id == org_id,
            OrganizationModule.module_key == module_all
        ).first()

        if org_mod:
            org_mod.is_enabled = True
        else:
            org_mod = OrganizationModule(
                organization_id=org_id,
                module_key=module_all,
                is_enabled=True
            )
            db.add(org_mod)

    db.commit()

def seed_global_modules(db: Session):
    """
    Ensures the modules catalog exists.
    """
    catalog = [
        {"key": MOD_CORE, "name": "Core System", "scope": ModuleScope.GLOBAL, "status": ModuleStatus.STABLE},
        {"key": MOD_REPORTS, "name": "Global Reports", "scope": ModuleScope.HQ, "status": ModuleStatus.STABLE},
        {"key": MOD_POS, "name": "Point of Sale", "scope": ModuleScope.BRANCH, "status": ModuleStatus.STABLE},
        {"key": MOD_WAREHOUSE, "name": "Warehouse Management", "scope": ModuleScope.WAREHOUSE, "status": ModuleStatus.STABLE},
        {"key": MOD_QUOTES, "name": "Quoting System", "scope": ModuleScope.HQ, "status": ModuleStatus.STABLE},
        {"key": MOD_APPOINTMENTS, "name": "Appointments Manager", "scope": ModuleScope.HQ, "status": ModuleStatus.BETA},

        {"key": MOD_CRM, "name": "CRM & Customers", "scope": ModuleScope.HQ, "status": ModuleStatus.STABLE},
        {"key": MOD_CUSTOMER_PORTAL, "name": "Customer Portal", "scope": ModuleScope.GLOBAL, "status": ModuleStatus.BETA},
        {"key": MOD_INVOICING, "name": "Electronic Invoicing", "scope": ModuleScope.HQ, "status": ModuleStatus.STABLE},
        {"key": MOD_PAYMENTS, "name": "Payments & Collection", "scope": ModuleScope.BRANCH, "status": ModuleStatus.STABLE},
        {"key": MOD_CASH, "name": "Cash Control", "scope": ModuleScope.BRANCH, "status": ModuleStatus.STABLE},
        {"key": MOD_RETURNS, "name": "Returns Management", "scope": ModuleScope.BRANCH, "status": ModuleStatus.STABLE},
        {"key": MOD_PRICING, "name": "Advanced Pricing", "scope": ModuleScope.HQ, "status": ModuleStatus.STABLE},
        {"key": MOD_PROMOTIONS, "name": "Promotions Engine", "scope": ModuleScope.HQ, "status": ModuleStatus.BETA},
        {"key": MOD_CATALOG, "name": "Global Catalog", "scope": ModuleScope.HQ, "status": ModuleStatus.STABLE},
        {"key": MOD_BRANCH_CATALOG, "name": "Branch Enablement", "scope": ModuleScope.HQ, "status": ModuleStatus.STABLE},
        {"key": MOD_INVENTORY, "name": "Inventory Control", "scope": ModuleScope.GLOBAL, "status": ModuleStatus.STABLE},
        {"key": MOD_SCANNER, "name": "Scanner de tienda", "scope": ModuleScope.BRANCH, "status": ModuleStatus.STABLE},
        {"key": MOD_LABELS, "name": "Etiquetas", "scope": ModuleScope.BRANCH, "status": ModuleStatus.STABLE},
        {"key": MOD_VARIANTS, "name": "Variantes color/talla", "scope": ModuleScope.GLOBAL, "status": ModuleStatus.STABLE},
        {"key": MOD_WORK_ORDERS, "name": "Work Orders & Service", "scope": ModuleScope.BRANCH, "status": ModuleStatus.STABLE},
        {"key": MOD_KDS, "name": "Kitchen Display System", "scope": ModuleScope.BRANCH, "status": ModuleStatus.BETA},
        {"key": MOD_TABLES, "name": "Table Management", "scope": ModuleScope.BRANCH, "status": ModuleStatus.BETA},
        {"key": MOD_MENU, "name": "Menu & Modifiers", "scope": ModuleScope.BRANCH, "status": ModuleStatus.STABLE},
    ]
    
    for item in catalog:
        mod = db.query(Module).filter(Module.key == item["key"]).first()
        if not mod:
            mod = Module(**item)
            db.add(mod)
        else:
            # Update values if needed
            mod.name = item["name"]
            mod.scope = item["scope"]
            mod.status = item["status"]
            
    db.commit()
