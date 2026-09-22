"""Regresión de la auditoría funcional del backend (2026-09-22) — usuarios.

C-5: `PUT /api/users/{id}` aplicaba todo el payload con un setattr genérico,
así que un ADMINISTRADOR de la organización se autopromovía a
`platform_role=SUPERADMIN` (acceso a `/api/platform/*`, todas las orgs).
"""
from app.modules.users.models import PlatformRole


def test_c5_admin_de_tenant_no_puede_autopromoverse_a_superadmin(
    client, db, org, hq_branch, admin_user, auth_admin
):
    assert admin_user.platform_role != PlatformRole.SUPERADMIN

    r = client.put(
        f"/api/users/{admin_user.id}",
        json={"platform_role": "SUPERADMIN"},
        headers=auth_admin,
    )
    # El campo ya no existe en el schema: Pydantic lo ignora y el PUT no falla,
    # pero el rol de plataforma queda intacto.
    assert r.status_code == 200, r.text
    db.refresh(admin_user)
    assert admin_user.platform_role != PlatformRole.SUPERADMIN
    assert r.json().get("platform_role") != "SUPERADMIN"


def test_c5_el_resto_del_put_de_usuarios_sigue_funcionando(
    client, db, org, hq_branch, admin_user, auth_admin, cajero_a
):
    r = client.put(
        f"/api/users/{cajero_a.id}",
        json={"full_name": "Cajera Renombrada", "is_active": True},
        headers=auth_admin,
    )
    assert r.status_code == 200, r.text
    db.refresh(cajero_a)
    assert cajero_a.full_name == "Cajera Renombrada"
