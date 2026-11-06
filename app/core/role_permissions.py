# app/core/role_permissions.py
"""
Atlas POS Role-Based View Permissions Matrix
Defines which templates each role can access in the Atlas POS preset.
"""

from app.models.users import Role

# Atlas POS Role -> Allowed Templates Mapping
ATLAS_POS_ROLE_VIEWS = {
    Role.ADMINISTRADOR: [
        # HQ Administration
        "hq_operations.html",
        "hq_reports_hub.html",
        "hq_control.html",
        "admin_catalog.html",
        "departments.html",
        "organization.html",
        "users.html",
        "customers.html",
        # "portal.html",  <-- Removed for admins (client only)
        "command_center_dashboard.html",
        "hq_branch_detail.html",
        "hq_branches.html",
        "hq_inventory_overview.html",
        "hq_sales_log.html",
        "hq_returns.html",
        "hq_reports.html",
        "brands.html",
        "hr.html",
        "hr_me.html",
        # Inventory & Logistics
        "boxes.html",
        "inventory.html",
        "logistics.html",
        # Sales & Quotes
        "quote_maker.html",
        "quotes.html",
        "seguimiento.html",
        "returns.html",
        "purchases.html",
        "expenses.html",
        # Atlas POS Home
        "atlas-pos.html",
        "startup.html",
        "index.html",
        "construction.html",
    ],

    Role.DUEÑO: [
        # Owner - Reduced scope
        "hq_operations.html",
        "hq_reports_hub.html",
        "hq_control.html",
        "admin_catalog.html",
        "customers.html",
        # "portal.html", <-- Removed for owners
        "hq_sales_log.html",
        "hq_returns.html",
        "hr_me.html",
        "boxes.html",
        "inventory.html",
        "logistics.html",
        "quote_maker.html",
        "quotes.html",
        "seguimiento.html",
        "returns.html",
        "purchases.html",
        "expenses.html",
        # Atlas POS Home
        "atlas-pos.html",
        "startup.html",
        "index.html",
        "construction.html",
    ],

    Role.GERENTE: [
        # Branch Manager - POS + Reports
        "cash_history.html",
        "reports.html",
        "hr_me.html",
        "products.html",
        "pos.html",
        "sales.html",
        "returns.html",
        "atlas-pos.html",
        "index.html",
        "construction.html",
    ],

    Role.CAJERO: [
        # Cashier - POS only — POS primero
        "pos.html",
        "cash_history.html",
        "hr_me.html",
        "products.html",
        "printer_config.html",
        "sales.html",
        "returns.html",
        "reports.html",
        "atlas-pos.html",
        "index.html",
        "construction.html",
    ],
    
    Role.VENDEDOR: [
        # Mobile Sales
        "mobile_dashboard.html",
        "mobile_query.html",
        "mobile_sales.html",
        "mobile_profile.html",
        "hr_me.html",
        "atlas-pos.html",
        "index.html",
        "construction.html",
    ],

    Role.SOPORTE_OPERATIVO: [
        # Mobile Query Only
        "mobile_dashboard.html",
        "mobile_query.html",
        "mobile_profile.html",
        "hr_me.html",
        "atlas-pos.html",
        "index.html",
        "construction.html",
    ],
    
    Role.CLIENTE: [
        # Customer Portal
        "portal.html",
        "index.html",
    ],
}

# Context Requirements for Roles
ROLE_CONTEXT_REQUIREMENTS = {
    Role.ADMINISTRADOR: "HQ",  # Can switch to BRANCH
    Role.DUEÑO: "HQ",
    Role.GERENTE: "BRANCH",
    Role.CAJERO: "BRANCH",
    Role.VENDEDOR: "MOBILE",  # or BRANCH with mobile UI
    Role.SOPORTE_OPERATIVO: "MOBILE",
}

# Nav group order for sidebar.
# Templates not listed here get group "Otros" and are hidden from sidebar.
_NAV_GROUP = {
    # ── HQ / ADMINISTRADOR ────────────────────────────────
    "hq_operations.html":            (0, "Inicio"),
    "hq_reports_hub.html":           (1, "Inicio"),
    "hq_control.html":               (2, "Inicio"),
    "command_center_dashboard.html": (0, "Inicio"),  # legacy — excluido del nav
    "admin_catalog.html":            (1, "Catálogo"),
    "departments.html":              (1, "Catálogo"),
    "brands.html":                   (1, "Catálogo"),
    "hq_sales_log.html":             (2, "Ventas"),
    "hq_returns.html":               (2, "Ventas"),
    "seguimiento.html":              (2, "Ventas"),
    "quotes.html":                   (2, "Ventas"),
    "quote_maker.html":              (2, "Ventas"),
    "returns.html":                  (2, "Ventas"),
    "purchases.html":                (3, "Finanzas"),
    "expenses.html":                 (3, "Finanzas"),
    # hq_reports.html removed — merged into command_center_dashboard (tab=reports)
    "inventory.html":                (4, "Inventario"),
    "hq_inventory_overview.html":    (4, "Inventario"),
    "logistics.html":                (4, "Inventario"),
    "customers.html":                (5, "Clientes"),
    "organization.html":             (6, "Organización"),
    "hq_branches.html":              (6, "Organización"),
    "users.html":                    (6, "Organización"),
    "hr.html":                       (6, "Organización"),
    # ── BRANCH — GERENTE / CAJERO ─────────────────────────
    "atlas-pos.html":                 (-2, "Mi día"),
    "pos.html":                      (-1, "Cobrar"),
    "cash_history.html":             (1, "Mi turno"),
    "sales.html":                    (2, "Mi turno"),
    "products.html":                 (4, "Inventario"),
    "reports.html":                  (5, "Inventario"),
    "printer_config.html":           (6, "Configuración"),
    # ── MOBILE — VENDEDOR / SOPORTE_OPERATIVO ─────────────
    "mobile_dashboard.html":         (0, "Móvil"),         # pinned
    "mobile_query.html":             (1, "Móvil"),
    "mobile_sales.html":             (1, "Móvil"),
    "mobile_profile.html":           (1, "Móvil"),
}

# Template Metadata for Atlas POS (Label, Icon, URL)
TEMPLATE_METADATA = {
    # --- HQ / Admin ---
    "hq_operations.html":            {"label": "Operaciones",            "icon": "fa-gauge-high",          "url": "/hq/operations"},
    "hq_reports_hub.html":           {"label": "Reportes",               "icon": "fa-chart-line",          "url": "/hq/reports-hub"},
    "hq_control.html":               {"label": "Control HQ",             "icon": "fa-sliders",             "url": "/hq/control"},
    "command_center_dashboard.html": {"label": "Panel de Control",       "icon": "fa-chart-line",         "url": "/command-center"},
    "admin_catalog.html":            {"label": "Productos",              "icon": "fa-book",               "url": "/admin/catalog"},
    "departments.html":              {"label": "Departamentos",          "icon": "fa-layer-group",         "url": "/departments"},
    "brands.html":                   {"label": "Marcas & Empaques",      "icon": "fa-tags",                "url": "/brands"},
    "inventory.html":                {"label": "Inventario",             "icon": "fa-boxes",               "url": "/inventory"},
    "hq_inventory_overview.html":    {"label": "Inventario por Sucursal","icon": "fa-globe",               "url": "/hq/inventory"},
    "hq_sales_log.html":             {"label": "Ventas",                 "icon": "fa-receipt",             "url": "/hq/sales"},
    "hq_returns.html":               {"label": "Devoluciones",           "icon": "fa-undo",                "url": "/hq/returns"},
    "hq_reports.html":               {"label": "Reportes",               "icon": "fa-chart-pie",           "url": "/hq/reports"},
    "hq_branches.html":              {"label": "Sucursales",             "icon": "fa-store",               "url": "/hq/branches"},
    "organization.html":             {"label": "Empresa y Sucursales",   "icon": "fa-building",            "url": "/organization"},
    "users.html":                    {"label": "Usuarios",               "icon": "fa-users-cog",           "url": "/users"},
    "customers.html":                {"label": "Clientes",               "icon": "fa-address-book",        "url": "/customers"},
    "hr.html":                       {"label": "Recursos Humanos",       "icon": "fa-user-tie",            "url": "/hr"},
    "hr_me.html":                    {"label": "Mi Expediente",          "icon": "fa-id-card",             "url": "/hr/me"},
    "logistics.html":                {"label": "Logística",              "icon": "fa-truck-loading",       "url": "/logistics"},
    "quotes.html":                   {"label": "Cotizaciones",           "icon": "fa-file-invoice",        "url": "/quotes"},
    "quote_maker.html":              {"label": "Nueva Cotización",       "icon": "fa-file-invoice-dollar", "url": "/quotes/new"},
    "seguimiento.html":              {"label": "Pedidos",                "icon": "fa-clipboard-check",     "url": "/seguimiento"},
    "returns.html":                  {"label": "Devoluciones",           "icon": "fa-undo",                "url": "/returns"},
    "purchases.html":                {"label": "Compras",                "icon": "fa-shopping-cart",       "url": "/purchases"},
    "expenses.html":                 {"label": "Gastos",                 "icon": "fa-money-bill-wave",     "url": "/expenses"},
    # --- POS / Branch ---
    "pos.html":                      {"label": "Punto de Venta",         "icon": "fa-cash-register",       "url": "/pos"},
    "cash_history.html":             {"label": "Cortes de Caja",         "icon": "fa-vault",               "url": "/cash-history"},
    "sales.html":                    {"label": "Historial Ventas",       "icon": "fa-history",             "url": "/sales"},
    "products.html":                 {"label": "Consulta Productos",     "icon": "fa-barcode",             "url": "/products"},
    "printer_config.html":           {"label": "Configuración",          "icon": "fa-gear",                "url": "/configuracion"},
    "reports.html":                  {"label": "Reportes",               "icon": "fa-chart-pie",           "url": "/api/reports/sales-summary"},
    # --- Mobile ---
    "mobile_query.html":             {"label": "Consulta Móvil",         "icon": "fa-mobile-alt",          "url": "/mobile/query"},
    "mobile_sales.html":             {"label": "Venta Móvil",            "icon": "fa-cart-plus",           "url": "/mobile/sales"},
    "mobile_dashboard.html":         {"label": "Dashboard Móvil",        "icon": "fa-mobile-screen",       "url": "/mobile/dashboard"},
    "mobile_profile.html":           {"label": "Perfil Móvil",           "icon": "fa-user-circle",         "url": "/mobile/profile"},
    # --- Portal ---
    "portal.html":                   {"label": "Portal Clientes",        "icon": "fa-user-circle",         "url": "/portal/dashboard"},
    # --- Internal (excluded from nav) ---
    "atlas-pos.html":                 {"label": "Inicio",                 "icon": "fa-home",                "url": "/atlas-pos"},
    "index.html":                    {"label": "Inicio",                 "icon": "fa-home",                "url": "/index"},
    "startup.html":                  {"label": "Setup",                  "icon": "fa-gear",                "url": "/startup"},
}

# Per-role label overrides applied AFTER TEMPLATE_METADATA lookup.
# Branch users see semantic labels ("Mi día", "Cobrar") while HQ keeps canonical names.
TEMPLATE_LABEL_OVERRIDES_BY_ROLE: dict[Role, dict[str, str]] = {
    Role.CAJERO: {
        "atlas-pos.html":       "Mi día",
        "pos.html":             "Cobrar",
        "cash_history.html":    "Mi caja",
        "sales.html":           "Mis ventas",
        "returns.html":         "Devolución",
        "products.html":        "Inventario",
        "printer_config.html":  "Configuración",
    },
}
# GERENTE shares the same semantic labels as CAJERO, plus reports access.
# GERENTE does NOT have printer_config.html in their template view, so it's omitted.
TEMPLATE_LABEL_OVERRIDES_BY_ROLE[Role.GERENTE] = {
    k: v for k, v in TEMPLATE_LABEL_OVERRIDES_BY_ROLE[Role.CAJERO].items()
    if k != "printer_config.html"
}
TEMPLATE_LABEL_OVERRIDES_BY_ROLE[Role.GERENTE]["reports.html"] = "Reportes"


# Validation: every override key must exist in ATLAS_POS_ROLE_VIEWS for that role.
for _role, _overrides in TEMPLATE_LABEL_OVERRIDES_BY_ROLE.items():
    _allowed = set(ATLAS_POS_ROLE_VIEWS.get(_role, []))
    _missing = set(_overrides) - _allowed
    if _missing:
        raise RuntimeError(
            f"TEMPLATE_LABEL_OVERRIDES_BY_ROLE[{_role}] references templates not in ATLAS_POS_ROLE_VIEWS: {_missing}"
        )


def can_access_template(role: Role, template_name: str) -> bool:
    """Check if a given role can access a specific template."""
    # Ensure optimal lookup whether role is Enum or String
    lookup_key = role
    if isinstance(role, str):
        try:
            lookup_key = Role(role)
        except (ValueError, KeyError):
            pass
            
    allowed_templates = ATLAS_POS_ROLE_VIEWS.get(lookup_key, [])
    
    # If empty, double check if we have a string/enum mismatch in the dict keys
    if not allowed_templates and hasattr(role, 'value'):
         # Maybe keys are strings? (unlikely here but safe)
         pass 

    return template_name in allowed_templates

def get_allowed_templates(role: Role) -> list[str]:
    """Get all templates a role can access."""
    return ATLAS_POS_ROLE_VIEWS.get(role, [])

def get_required_context(role: Role) -> str:
    """Get the required context for a role."""
    return ROLE_CONTEXT_REQUIREMENTS.get(role, "HQ")

def get_atlas_pos_nav(role: Role) -> list[dict]:
    """Returns list of nav items for Atlas POS based on role, with group metadata for sidebar rendering."""
    lookup_key = role
    if isinstance(role, str):
        try:
            lookup_key = Role(role)
        except (ValueError, KeyError):
            pass

    templates = ATLAS_POS_ROLE_VIEWS.get(lookup_key, [])

    # Templates that are internal/utility — never appear in sidebar
    _EXCLUDED_FROM_NAV = {
        "index.html", "startup.html", "atlas-pos.html", "hr_me.html",
        "hq_branch_detail.html", "construction.html", "hq_reports.html",
        "command_center_dashboard.html",  # legacy — reemplazado por hq_operations/reports/control
    }
    # ADMINISTRADOR y DUEÑO ya tienen otros dashboards como punto de entrada;
    # para los demás roles (CAJERO, GERENTE, VENDEDOR, SOPORTE) atlas-pos es el "Inicio".
    _ROLES_SIN_INICIO = {Role.ADMINISTRADOR, Role.DUEÑO}
    if lookup_key not in _ROLES_SIN_INICIO:
        _EXCLUDED_FROM_NAV.discard("atlas-pos.html")

    overrides = TEMPLATE_LABEL_OVERRIDES_BY_ROLE.get(lookup_key, {}) if isinstance(lookup_key, Role) else {}
    nav = []
    for t_name in templates:
        if t_name in TEMPLATE_METADATA and t_name not in _EXCLUDED_FROM_NAV:
            meta = TEMPLATE_METADATA[t_name]
            sort_order, group = _NAV_GROUP.get(t_name, (99, "Otros"))
            nav.append({
                "label": overrides.get(t_name, meta["label"]),
                "icon": meta["icon"],
                "href": meta["url"],
                "group": group,
                "_sort": sort_order,
            })

    # Sort by group order, then by original template list order within group
    nav.sort(key=lambda x: x["_sort"])
    return nav
