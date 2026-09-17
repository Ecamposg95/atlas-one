#!/usr/bin/env python3
"""
Railway Deployment Initialization Script
Ejecuta la secuencia completa de inicialización:
1. Crear Superadmin
2. Crear Organización Rmazh con preset ATLAS_POS
3. Vincular Superadmin a Rmazh
"""
import sys
import os
import logging
import secrets

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import app.models to ensure all tables are registered in Base.metadata
import app.models  # This imports all submodules defined in app/models/__init__.py

from app.core.database import SessionLocal, engine, Base
from app.models.users import User, PlatformRole, Role, UserOrganization
from app.models.organization import Organization, IndustryType
from app.core.security import get_password_hash
from sqlalchemy.exc import IntegrityError

def init_database():
    """Initialize database tables"""
    print("🔧 Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("✅ Database tables created")

def run_migrations():
    """Run incremental column migrations (idempotent)."""
    print("\n🔄 Running column migrations...")
    from sqlalchemy import text

    # Sync EVERY value of the Python IndustryType enum into the Postgres
    # `industrytype` type. The DB enum was originally created with the legacy
    # taxonomy (incl. DATAXPOS); create_all() never ALTERs an existing type, so
    # renamed/added values — ATLAS_POS itself and the whole ATLAS_ONE_* family —
    # must be backfilled here, otherwise INSERT org with industry_type='ATLAS_POS'
    # raises InvalidTextRepresentation. ADD VALUE cannot run in a txn block → AUTOCOMMIT.
    print("\n  Atlas One — ensuring industrytype enum values…")
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        for member in IndustryType:
            conn.execute(text(
                f"ALTER TYPE industrytype ADD VALUE IF NOT EXISTS '{member.value}'"
            ))
    print(f"  ✓ industrytype enum synced ({len(list(IndustryType))} values)")

    migrations = [
        # (table, column, ddl)
        ("products", "image_url",      "ALTER TABLE products ADD COLUMN image_url VARCHAR;"),
        ("product_variants", "has_iva", "ALTER TABLE product_variants ADD COLUMN has_iva BOOLEAN DEFAULT FALSE;"),
        # Variantes color/talla (2026-09-17, preset boutique). Opcionales.
        ("product_variants", "color", "ALTER TABLE product_variants ADD COLUMN color VARCHAR(60);"),
        ("product_variants", "size",  "ALTER TABLE product_variants ADD COLUMN size VARCHAR(30);"),
        ("brands",   "logo_url",       "ALTER TABLE brands ADD COLUMN logo_url VARCHAR;"),
        ("branches", "paper_width_mm", "ALTER TABLE branches ADD COLUMN paper_width_mm INTEGER DEFAULT 80;"),
        ("branches", "printer_cols",   "ALTER TABLE branches ADD COLUMN printer_cols INTEGER;"),
        ("branches", "open_drawer_on_print", "ALTER TABLE branches ADD COLUMN open_drawer_on_print BOOLEAN NOT NULL DEFAULT TRUE;"),
        # Cashier Cockpit (PR #165) — Branch.daily_sales_goal and Branch.closing_time
        ("branches", "daily_sales_goal", "ALTER TABLE branches ADD COLUMN daily_sales_goal NUMERIC(12,2);"),
        ("branches", "closing_time",     "ALTER TABLE branches ADD COLUMN closing_time TIME;"),
        # Branch logo (E#2) — per-branch ticket logo override
        ("branches", "logo_url",         "ALTER TABLE branches ADD COLUMN logo_url VARCHAR;"),
        ("cash_sessions", "total_change_given", "ALTER TABLE cash_sessions ADD COLUMN total_change_given NUMERIC(10,2) DEFAULT 0.00;"),
        ("sales_lines", "discount_percent", "ALTER TABLE sales_lines ADD COLUMN discount_percent NUMERIC(5,2) DEFAULT 0.00;"),
        # Sprint 2 — multi-tenancy completa (S2.2)
        ("cash_sessions", "organization_id", "ALTER TABLE cash_sessions ADD COLUMN organization_id INTEGER REFERENCES organization(id);"),
        ("employees", "organization_id", "ALTER TABLE employees ADD COLUMN organization_id INTEGER REFERENCES organization(id);"),
        # Track 1 (POS bug-fix) — vincular venta a sesión de caja
        ("sales_documents", "cash_session_id", "ALTER TABLE sales_documents ADD COLUMN cash_session_id INTEGER REFERENCES cash_sessions(id);"),
        # Fase 1.3 — vuelto entregado por venta (persistido al crear, leído al cuadrar).
        # NULL = venta legada → reconciliación recomputa con la lógica antigua.
        ("sales_documents", "change_given", "ALTER TABLE sales_documents ADD COLUMN change_given NUMERIC(12,2);"),
        # Track 4 (POS bug-fix) — tracking per-PC en print_jobs
        ("print_jobs", "device_id",          "ALTER TABLE print_jobs ADD COLUMN device_id VARCHAR(64);"),
        ("print_jobs", "device_fingerprint", "ALTER TABLE print_jobs ADD COLUMN device_fingerprint VARCHAR(128);"),
        ("print_jobs", "client_ip",          "ALTER TABLE print_jobs ADD COLUMN client_ip VARCHAR(64);"),
        # CAJERO audit 2026-04-29 (H-2) — descuento global persistido para reportes.
        # No se agrega al modelo ORM; solo lectura defensiva via setattr.
        ("sales_documents", "global_discount_pct", "ALTER TABLE sales_documents ADD COLUMN global_discount_pct NUMERIC(5,2) DEFAULT 0;"),
        # CAJERO audit 2026-04-29 (M-3) — lifecycle de parked tickets. status='ACTIVE' default;
        # se setea a 'CONVERTED' cuando el ticket se materializa en una venta. converted_to_sale_id
        # da trazabilidad parked → sale.
        ("parked_tickets", "status",                "ALTER TABLE parked_tickets ADD COLUMN status VARCHAR(16) NOT NULL DEFAULT 'ACTIVE';"),
        ("parked_tickets", "converted_to_sale_id",  "ALTER TABLE parked_tickets ADD COLUMN converted_to_sale_id VARCHAR(36) REFERENCES sales_documents(id);"),
        # Atlas One presets expansion 2026-05-13 — upsell metadata per module.
        # Populated by scripts/init_presets_v2.py (run manually post-deploy).
        ("modules", "upsell_metadata", "ALTER TABLE modules ADD COLUMN upsell_metadata JSON;"),
        # Appointments MVP 2026-05-18 — slug for public portal URLs
        ("organization", "slug", "ALTER TABLE organization ADD COLUMN slug VARCHAR(64);"),
        # Preset deprecation 2026-06-09 — hide legacy presets from selectors
        ("industry_presets", "is_deprecated", "ALTER TABLE industry_presets ADD COLUMN is_deprecated BOOLEAN NOT NULL DEFAULT FALSE;"),
        # Gastro 2026-07-09 — propina cobrada y atribución al mesero (ventas por mesero)
        ("sales_documents", "tip_amount",     "ALTER TABLE sales_documents ADD COLUMN tip_amount NUMERIC(10,2) DEFAULT 0;"),
        ("sales_documents", "server_user_id", "ALTER TABLE sales_documents ADD COLUMN server_user_id INTEGER REFERENCES users(id);"),
        # IVA — fuente única 2026-09-11 (auditoría Rmazh §3). Modo de precio por
        # organización, consumido por app/services/tax.py. DEFAULT FALSE a
        # propósito: es el comportamiento histórico (precio neto + IVA encima);
        # ponerlo en TRUE cambiaría el total cobrado a clientes vivos.
        ("organization", "price_includes_tax", "ALTER TABLE organization ADD COLUMN price_includes_tax BOOLEAN NOT NULL DEFAULT FALSE;"),
        # Equivalente en dolares 2026-09-17. Modo 'off' por DEFAULT a proposito:
        # ninguna organizacion viva ve nada hasta que su dueño lo encienda.
        # La tabla `exchange_rates` la crea `create_all` (modelo registrado en
        # app/models/__init__.py); aqui solo van las columnas de tablas ya vivas.
        ("organization", "usd_rate_mode",   "ALTER TABLE organization ADD COLUMN usd_rate_mode VARCHAR(10) NOT NULL DEFAULT 'off';"),
        ("organization", "usd_rate_manual", "ALTER TABLE organization ADD COLUMN usd_rate_manual NUMERIC(10,4);"),
        ("organization", "usd_rate_margin", "ALTER TABLE organization ADD COLUMN usd_rate_margin NUMERIC(10,4) NOT NULL DEFAULT 0;"),
    ]

    # Track 1 — Audit + cleanup de Payment huérfanos antes de NOT NULL.
    # Listar count en logs; en QA borramos. En prod, ESTA acción se replantea
    # antes de promover (ver tech-debt roadmap).
    print("\n  Track 1 — Auditando payments huérfanos (sales_document_id IS NULL)…")
    with engine.begin() as conn:
        orphan_count = conn.execute(text(
            "SELECT count(*) FROM payments WHERE sales_document_id IS NULL"
        )).scalar() or 0
        print(f"  · payments huérfanos detectados: {orphan_count}")
        if orphan_count > 0:
            # Un pago sin venta es EVIDENCIA de dinero recibido: puede venir de
            # un checkout que fallo a medias. Borrarlo en silencio en cada
            # arranque destruye el rastro. Solo se limpia si alguien lo pide
            # explicitamente con ATLAS_PURGE_ORPHAN_PAYMENTS=1.
            if os.getenv("ATLAS_PURGE_ORPHAN_PAYMENTS", "").strip().lower() in {"1", "true", "yes"}:
                conn.execute(text("DELETE FROM payments WHERE sales_document_id IS NULL"))
                print(f"  ✓ {orphan_count} payments huérfanos eliminados (purga explícita)")
            else:
                print(
                    f"  ⚠ {orphan_count} payments huérfanos NO se tocan. Revísalos a mano; "
                    f"para purgarlos usa ATLAS_PURGE_ORPHAN_PAYMENTS=1."
                )
        # Aplicar NOT NULL si aún no lo es
        is_nullable = conn.execute(text(
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_name='payments' AND column_name='sales_document_id'"
        )).scalar()
        if is_nullable == 'YES':
            conn.execute(text(
                "ALTER TABLE payments ALTER COLUMN sales_document_id SET NOT NULL"
            ))
            print("  ✓ payments.sales_document_id ahora NOT NULL")
        else:
            print("  · payments.sales_document_id ya era NOT NULL")

    with engine.connect() as conn:
        for table, column, ddl in migrations:
            res = conn.execute(text(
                "SELECT column_name FROM information_schema.columns "
                f"WHERE table_name='{table}' AND column_name='{column}'"
            ))
            if not res.fetchone():
                conn.execute(text(ddl))
                conn.commit()
                print(f"  ✓ {table}.{column} added")
            else:
                print(f"  · {table}.{column} already exists")

    # --- Index migrations (idempotent via CREATE INDEX IF NOT EXISTS) ---
    index_migrations = [
        # (name, ddl)
        # Folio race fix 2026-07-29 — garantía dura contra folios fiscales
        # duplicados. get_next_folio hace MAX(folio)+1 sin bloqueo; dos ventas
        # concurrentes de la misma sucursal podían compartir folio. El advisory
        # lock en app/utils/folios.py lo previene; este índice lo hace imposible.
        # Verificado 0 duplicados en prod antes de crearlo. Parcial: los folios
        # son permanentes una vez asignados (soft-delete incluido).
        (
            "uq_sales_documents_branch_series_folio",
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_sales_documents_branch_series_folio
                ON sales_documents (branch_id, series, folio)
                WHERE folio IS NOT NULL;
            """,
        ),
        (
            "ix_pbs_branch_active_pos",
            """
            CREATE INDEX IF NOT EXISTS ix_pbs_branch_active_pos
                ON product_branch_status (branch_id, variant_id)
                WHERE is_active_pos = true;
            """,
        ),
        # Sprint 2 — índices para filtros por organization_id
        (
            "ix_cash_sessions_organization_id",
            "CREATE INDEX IF NOT EXISTS ix_cash_sessions_organization_id ON cash_sessions (organization_id);",
        ),
        (
            "ix_employees_organization_id",
            "CREATE INDEX IF NOT EXISTS ix_employees_organization_id ON employees (organization_id);",
        ),
        # Track 1 (POS bug-fix)
        (
            "ix_sales_documents_cash_session_id",
            "CREATE INDEX IF NOT EXISTS ix_sales_documents_cash_session_id ON sales_documents (cash_session_id);",
        ),
        # Track 4 (POS bug-fix)
        (
            "ix_print_jobs_device_id",
            "CREATE INDEX IF NOT EXISTS ix_print_jobs_device_id ON print_jobs (device_id);",
        ),
        # Platform pack 2026-04-30 — Control Tower / Stats endpoints filtran sales_documents
        # por created_at en cada request (sales-now, system-health-summary, kpis-extended,
        # cohort-retention, etc). Sin este índice, full table scan = endpoints cuelgan.
        (
            "ix_sales_documents_created_at",
            "CREATE INDEX IF NOT EXISTS ix_sales_documents_created_at ON sales_documents (created_at);",
        ),
        # Cashier perf 2026-05-07 — /cash/summary y /cash/branch-summary filtran por
        # (seller_id, created_at) cada vez que el cajero refresca el dashboard del turno.
        # Sin composite, plan = bitmap heap scan sobre miles de filas.
        (
            "ix_sales_seller_created",
            "CREATE INDEX IF NOT EXISTS ix_sales_seller_created ON sales_documents (seller_id, created_at);",
        ),
        # Cashier perf 2026-05-07 — cierre de turno scanea parked_tickets por user+branch+created_at
        # para detectar tickets pausados. Composite acelera tanto el cierre como el polling
        # del badge de pendientes en POS.
        (
            "ix_parked_tickets_user_branch_created",
            "CREATE INDEX IF NOT EXISTS ix_parked_tickets_user_branch_created ON parked_tickets (user_id, branch_id, created_at);",
        ),
        # Appointments MVP 2026-05-18 — critical indexes for availability + lifecycle
        (
            "ix_appt_org_branch_starts",
            "CREATE INDEX IF NOT EXISTS ix_appt_org_branch_starts ON appointments (organization_id, branch_id, starts_at);",
        ),
        (
            "ix_appt_professional_range",
            "CREATE INDEX IF NOT EXISTS ix_appt_professional_range ON appointments (professional_id, starts_at, ends_at);",
        ),
        (
            "ix_appt_customer",
            "CREATE INDEX IF NOT EXISTS ix_appt_customer ON appointments (customer_id);",
        ),
        (
            "ix_appt_events",
            "CREATE INDEX IF NOT EXISTS ix_appt_events ON appointments_events (appointment_id, created_at);",
        ),
        (
            "ix_blocks_prof_range",
            "CREATE INDEX IF NOT EXISTS ix_blocks_prof_range ON appointments_blocks (professional_id, starts_at, ends_at);",
        ),
    ]

    with engine.connect() as conn:
        for name, ddl in index_migrations:
            conn.execute(text(ddl))
            conn.commit()
            print(f"  ✓ index {name} ensured")

    # Partial index — only Postgres supports CREATE INDEX ... WHERE
    if engine.dialect.name == "postgresql":
        with engine.connect() as conn:
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_appt_resource_range "
                "ON appointments (resource_id, starts_at, ends_at) "
                "WHERE resource_id IS NOT NULL;"
            ))
            conn.commit()
            print("  ✓ index ix_appt_resource_range (partial) ensured")

    # Carrera al abrir caja 2026-09-11 (auditoría Rmazh §5) — una sola sesión
    # ABIERTA por (usuario, sucursal). Parcial: el historial de cortes cerrados
    # acumula muchas filas del mismo par y no debe estorbar.
    #
    # Si la base ya trae duplicados (los que creó la carrera antes de este
    # arreglo) el CREATE UNIQUE fallaría y tumbaría el deploy. Preferimos
    # reportarlos y seguir: el arreglo del endpoint ya impide crear nuevos, y
    # los existentes se resuelven cerrando la sesión sobrante a mano.
    if engine.dialect.name == "postgresql":
        with engine.connect() as conn:
            duplicados = conn.execute(text(
                "SELECT user_id, branch_id, COUNT(*) AS n FROM cash_sessions "
                "WHERE status = 'OPEN' GROUP BY user_id, branch_id HAVING COUNT(*) > 1"
            )).fetchall()
            if duplicados:
                detalle = ", ".join(f"user={d[0]} branch={d[1]} ({d[2]})" for d in duplicados)
                aviso = (
                    f"uq_cash_sessions_open_user_branch NO se crea: hay sesiones "
                    f"abiertas duplicadas — {detalle}. Cierra las sobrantes y vuelve a desplegar."
                )
                print(f"  ⚠ {aviso}")
                # El print se pierde en el scroll del arranque; el warning queda
                # en el log estructurado, que es donde se busca despues.
                logging.getLogger(__name__).warning("RAILWAY_INIT: %s", aviso)
            else:
                conn.execute(text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_cash_sessions_open_user_branch "
                    "ON cash_sessions (user_id, branch_id) "
                    "WHERE status = 'OPEN';"
                ))
                conn.commit()
                print("  ✓ index uq_cash_sessions_open_user_branch (partial) ensured")

    # --- Sprint 2 backfill: cash_sessions.organization_id y employees.organization_id ---
    # Derivado de branches.organization_id. Idempotente (solo filas con NULL).
    print("\n  Backfill organization_id (Sprint 2)…")
    with engine.begin() as conn:
        result_cs = conn.execute(text(
            "UPDATE cash_sessions cs "
            "SET organization_id = b.organization_id "
            "FROM branches b "
            "WHERE cs.branch_id = b.id AND cs.organization_id IS NULL "
            "RETURNING cs.id"
        ))
        cs_count = len(result_cs.fetchall())
        print(f"  ✓ cash_sessions backfill: {cs_count} filas actualizadas")

        result_emp = conn.execute(text(
            "UPDATE employees e "
            "SET organization_id = b.organization_id "
            "FROM branches b "
            "WHERE e.base_branch_id = b.id "
            "AND e.organization_id IS NULL "
            "AND e.base_branch_id IS NOT NULL "
            "RETURNING e.id"
        ))
        emp_count = len(result_emp.fetchall())
        print(f"  ✓ employees backfill: {emp_count} filas actualizadas")

        orphans = conn.execute(text(
            "SELECT COUNT(*) FROM employees WHERE organization_id IS NULL"
        )).scalar()
        if orphans:
            print(f"  ⚠ {orphans} employees sin organization_id (sin base_branch_id) — resolver manual antes de Sprint 9.")

    # Appointments MVP — backfill slug from name for orgs that don't have one.
    # Create UNIQUE INDEX first so concurrent backfills (e.g., two Railway
    # replicas booting) fail-fast with IntegrityError instead of producing
    # silent duplicates after the fact. Base slug is truncated to 60 chars
    # so the "-N" suffix (n < 1000 → up to 4 chars) always fits within 64.
    import re
    print("\n  Backfill organization.slug…")
    with engine.connect() as conn:
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ux_organization_slug ON organization (slug);"))
        conn.commit()
    with engine.begin() as conn:
        # Postgres advisory lock to serialize concurrent backfills
        if engine.dialect.name == "postgresql":
            conn.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": 91827364})
        rows = conn.execute(text("SELECT id, name FROM organization WHERE slug IS NULL")).fetchall()
        if not rows:
            print("  ✓ nothing to backfill")
        for org_id, name in rows:
            base = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")[:60] or f"org-{org_id}"
            cand, n = base, 1
            while conn.execute(text("SELECT 1 FROM organization WHERE slug = :s"), {"s": cand}).scalar():
                n += 1
                cand = f"{base}-{n}"
                if len(cand) > 64:
                    # Should never happen with base ≤ 60 and n < 9999, but safe-guard
                    cand = f"org-{org_id}"
            conn.execute(text("UPDATE organization SET slug = :s WHERE id = :id"), {"s": cand, "id": org_id})
            print(f"    · org {org_id} ('{name}') → slug='{cand}'")
        if rows:
            print(f"  ✓ backfilled {len(rows)} orgs")

    print("✅ Migrations complete")

def should_seed_demo() -> bool:
    """Si se siembran organizaciones demo en este arranque.

    Por omision si, para no alterar el comportamiento historico. En una base
    de produccion con un cliente real se apaga con ATLAS_SEED_DEMO=0: usuarios
    demo con contrasena conocida no tienen nada que hacer junto a datos de un
    negocio que factura.
    """
    valor = os.getenv("ATLAS_SEED_DEMO")
    if valor is None:
        return True
    return valor.strip().lower() not in {"0", "false", "no", "off"}


def superadmin_password() -> str:
    """Contrasena del superadministrador al crear una base desde cero.

    Sale de SUPERADMIN_PASSWORD. Sin esa variable se genera una aleatoria y se
    avisa por consola: el valor historico estaba escrito en este archivo y por
    tanto publicado en el repositorio.
    """
    del_entorno = os.getenv("SUPERADMIN_PASSWORD")
    if del_entorno:
        return del_entorno
    return secrets.token_urlsafe(24)


def create_superadmin(db):
    """Create superadmin user if not exists"""
    print("\n👤 Creating Superadmin...")
    
    # Check if superadmin exists
    existing = db.query(User).filter(User.username == "superadmin").first()
    if existing:
        print("⚠️  Superadmin already exists, skipping...")
        return existing
    
    clave = superadmin_password()
    superadmin = User(
        username="superadmin",
        password_hash=get_password_hash(clave),
        role=Role.ADMINISTRADOR,
        platform_role=PlatformRole.SUPERADMIN,
        is_active=True
    )
    
    db.add(superadmin)
    db.commit()
    db.refresh(superadmin)
    
    print(f"✅ Superadmin created: {superadmin.username}")
    if os.getenv("SUPERADMIN_PASSWORD"):
        print("   Password: la de SUPERADMIN_PASSWORD")
    else:
        print(f"   Password GENERADA (guardala, no se vuelve a mostrar): {clave}")
    return superadmin

def create_rmazh_organization(db):
    """Create Rmazh organization with ATLAS_POS preset"""
    print("\n🏢 Creating Rmazh Organization...")
    
    # Check if organization exists
    existing = db.query(Organization).filter(Organization.name == "Rmazh").first()
    if existing:
        print("⚠️  Rmazh organization already exists, skipping...")
        return existing
    
    rmazh = Organization(
        name="Rmazh",
        industry_type=IndustryType.ATLAS_POS,
        is_active=True,
        plan="Pro",
        status="ACTIVE"
    )
    
    db.add(rmazh)
    db.commit()
    db.refresh(rmazh)
    
    print(f"✅ Organization created: {rmazh.name}")
    print(f"   Industry: {rmazh.industry_type.value}")
    return rmazh

def link_superadmin_to_rmazh(db, superadmin, organization):
    """Link superadmin to Rmazh organization"""
    print("\n🔗 Linking Superadmin to Rmazh...")
    
    # Check if link exists
    existing_link = db.query(UserOrganization).filter(
        UserOrganization.user_id == superadmin.id,
        UserOrganization.organization_id == organization.id
    ).first()
    
    if existing_link:
        print("⚠️  Link already exists, skipping...")
        return
    
    link = UserOrganization(
        user_id=superadmin.id,
        organization_id=organization.id,
        is_active=True
    )
    
    db.add(link)
    db.commit()
    
    print(f"✅ Superadmin linked to {organization.name}")

def initialize_modules(db, organization):
    """Initialize ATLAS_POS modules for organization"""
    print("\n📦 Initializing ATLAS_POS modules...")
    
    from app.models.modules import Module, OrganizationModule
    
    # ATLAS_POS module keys — alineado con scripts/init_presets_v2.py preset
    # canónico (Wave 2: removidos purchasing/fulfillment/documents/
    # sales_pipeline/invoicing/quotes que no son parte del preset Atlas POS).
    atlas_pos_modules = [
        "core", "pos", "cash_management", "inventory", "catalog",
        "branch_catalog_enablement", "returns", "pricing", "promotions",
        "payments", "crm", "reports",
    ]

    modules_created = 0
    for module_key in atlas_pos_modules:
        # Check if module exists in catalog
        module = db.query(Module).filter(Module.key == module_key).first()
        if not module:
            # Create module if doesn't exist
            module = Module(
                key=module_key,
                name=module_key.replace("_", " ").title(),
                description=f"Module for {module_key}"
            )
            db.add(module)
            db.commit()
            db.refresh(module)
        
        # Check if already enabled for org
        org_module = db.query(OrganizationModule).filter(
            OrganizationModule.organization_id == organization.id,
            OrganizationModule.module_key == module.key
        ).first()
        
        if not org_module:
            org_module = OrganizationModule(
                organization_id=organization.id,
                module_key=module.key,
                is_enabled=True
            )
            db.add(org_module)
            modules_created += 1
    
    db.commit()
    print(f"✅ {modules_created} modules initialized for {organization.name}")
    
def initialize_presets(db):
    """Initialize Industry Presets"""
    print("\n📋 Initializing Industry Presets...")
    
    from app.models.modules import IndustryPreset, Module
    
    # ATLAS_POS Preset
    preset_data = {
        "industry_type": "ATLAS_POS",
        "display_name": "Atlas POS Retail",
        "description": "Configuración completa para punto de venta retail con inventario avanzado.",
        "modules": [
            "pos", "inventory", "sales", "customers", "finance", 
            "reports", "users", "branches", "cash_register",
            "products", "categories", "suppliers", "returns",
            "invoicing", "receipts", "dashboard"
        ],
        "is_system": True
    }
    
    existing = db.query(IndustryPreset).filter(IndustryPreset.industry_type == preset_data["industry_type"]).first()
    if not existing:
        preset = IndustryPreset(**preset_data)
        db.add(preset)
        print("✅ Created preset: ATLAS_POS Retail")
    else:
        print("⚠️  Preset ATLAS_POS already exists, skipping...")
        
    db.commit()

def main():
    """Main initialization sequence"""
    print("=" * 60)
    print("🚀 RAILWAY DEPLOYMENT INITIALIZATION")
    print("=" * 60)
    
    try:
        # Initialize database
        init_database()

        # Run incremental migrations
        run_migrations()

        # Create database session
        db = SessionLocal()
        
        try:
            # Step 1: Create Superadmin
            create_superadmin(db)

            # Step 2: Initialize Presets (legacy)
            initialize_presets(db)

            # Step 3: Atlas One presets seed (2026-05-13)
            # Idempotent upsert — adds 6 new modules + Atlas One presets
            # (ATLAS_POS aligerado + ATLAS_ONE_*) + CUSTOM, and retires the
            # legacy DATAXPOS naming (orgs migrated → ATLAS_POS, preset row dropped).
            print("\n🌐 Atlas One — seeding modules & presets...")
            try:
                from scripts.init_presets_v2 import seed_modules_and_presets
                seed_modules_and_presets(db)
                print("✅ Atlas One seed complete")
            except Exception as e:
                print(f"⚠️ Atlas One seed failed (non-fatal): {e}")
                import traceback
                traceback.print_exc()

            # Step 4: Demo organizations + users + sample products (2026-05-14)
            # Idempotent: skip if a demo org already exists by name.
            # Creates 7 orgs (1 per Atlas One preset) with branch HQ, admin
            # user demo_<preset>/demo1234, applied preset, and sample products.
            # Wrapped in try/except so a partial failure does not crash boot.
            if not should_seed_demo():
                print("\n🎭 Atlas One — demo orgs OMITIDAS (ATLAS_SEED_DEMO apagado)")
            else:
                print("\n🎭 Atlas One — seeding demo organizations...")
                try:
                    from scripts.seed_demo_orgs import seed_all as seed_demo_orgs_all
                    seed_demo_orgs_all(db)
                    print("✅ Demo organizations seed complete")
                except Exception as e:
                    print(f"⚠️ Demo orgs seed failed (non-fatal): {e}")
                    import traceback
                    traceback.print_exc()

            print("\n" + "=" * 60)
            print("✅ INITIALIZATION COMPLETE!")
            print("=" * 60)
            print("\n📋 Summary:")
            print(f"   • Superadmin: superadmin")
            print(f"   • Presets: Initialized")
            print("=" * 60)
            
        finally:
            db.close()
            
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
