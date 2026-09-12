"""``/api/platform/*`` router package.

Split from a single 4k-line ``platform.py`` in Sprint 5. The aggregator
preserves the original parent-router contract (``tags=["Platform (SaaS)"]``
and the ``require_platform_admin`` dependency that gates every endpoint).

``main.py`` mounts this package via ``include_router(platform.router,
prefix="/api/platform", ...)`` — Python prefers the package over a
sibling ``platform.py``, so the import path stays the same.
"""

from fastapi import APIRouter, Depends

from app.modules.platform.dependencies import require_platform_admin

from . import (
    stats,
    organizations,
    branches,
    users,
    modules,
    presets,
    admins,
    impersonation,
    audit,
    announcements,
    health,
    alerts,
    incidents,
    feature_flags,
    api_keys,
    reports,
    reports_money,
    control_tower,
    overview,
)

router = APIRouter(
    tags=["Platform (SaaS)"],
    dependencies=[Depends(require_platform_admin)],
)
router.include_router(stats.router)
router.include_router(organizations.router)
router.include_router(branches.router)
router.include_router(users.router)
router.include_router(modules.router)
router.include_router(presets.router)
router.include_router(admins.router)
router.include_router(impersonation.router)
router.include_router(audit.router)
router.include_router(announcements.router)
router.include_router(health.router)
router.include_router(alerts.router)
router.include_router(incidents.router)
router.include_router(feature_flags.router)
router.include_router(api_keys.router)
router.include_router(reports.router)
router.include_router(reports_money.router)
router.include_router(control_tower.router)
router.include_router(overview.router)
