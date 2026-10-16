"""Estado por sucursal y existencias: los helpers que antes estaban copiados
en create, update, duplicate, crear_variantes y upload."""
from decimal import Decimal
from types import SimpleNamespace

from conftest import _make_product
from app.models.inventory import InventoryMovement, MovementType, StockOnHand
from app.models.products import ProductBranchStatus
from app.modules.products.services.sucursales import (
    armar_estado_por_sucursal, copiar_estado_por_sucursal, fijar_existencia,
    registrar_stock_inicial, resolver_sucursales_destino,
    sucursal_de_existencia_inicial, sucursales_que_venden,
)

SIN_SUCURSAL = SimpleNamespace(branch_id=None)


class TestResolverDestino:
    def test_sin_sucursal_ni_destinos_toma_todas_las_que_venden(self, db, org, branch_a, branch_b, hq_branch):
        # hq_branch tiene can_sell=False: no entra.
        assert resolver_sucursales_destino(db, org.id, SIN_SUCURSAL, None) == sorted([branch_a.id, branch_b.id])

    def test_inactiva_o_que_no_vende_no_entra(self, db, org, branch_a, branch_b):
        branch_b.is_active = False
        db.flush()
        assert sucursales_que_venden(db, org.id) == [branch_a.id]

    def test_con_destinos_une_la_del_usuario_y_ordena(self, db, org, branch_a, branch_b):
        usuario = SimpleNamespace(branch_id=branch_b.id)
        assert resolver_sucursales_destino(db, org.id, usuario, [branch_a.id, branch_a.id]) == sorted([branch_a.id, branch_b.id])

    def test_sin_ninguna_que_venda_queda_vacio(self, db, org, hq_branch):
        assert resolver_sucursales_destino(db, org.id, SIN_SUCURSAL, None) == []


class TestSucursalDeExistencia:
    def test_orden_de_preferencia(self, branch_a, branch_b):
        usuario = SimpleNamespace(branch_id=branch_b.id)
        destinos = sorted([branch_a.id, branch_b.id])
        assert sucursal_de_existencia_inicial(usuario, branch_a.id, destinos) == branch_a.id
        assert sucursal_de_existencia_inicial(usuario, None, destinos) == branch_b.id
        assert sucursal_de_existencia_inicial(SIN_SUCURSAL, 999999, destinos) == destinos[0]
        assert sucursal_de_existencia_inicial(SIN_SUCURSAL, None, []) is None


class TestEstadoPorSucursal:
    def test_crea_faltantes_y_no_duplica_existentes(self, db, org, branch_a, branch_b):
        _, v = _make_product(db, org, "P", "PBS-1", 10, [(branch_a.id, False)])
        armar_estado_por_sucursal(db, org.id, v, [branch_a.id, branch_b.id], is_active_hq=True)
        filas = {p.branch_id: p for p in db.query(ProductBranchStatus).filter(ProductBranchStatus.variant_id == v.id).all()}
        assert set(filas) == {branch_a.id, branch_b.id}
        # La que ya existía solo se hace visible; sus demás banderas no se tocan.
        assert filas[branch_a.id].is_visible is True and filas[branch_a.id].is_active_pos is False
        assert filas[branch_b.id].is_active_hq is True and filas[branch_b.id].is_active_pos is True

    def test_reemplazar_borra_las_viejas(self, db, org, branch_a, branch_b):
        _, v = _make_product(db, org, "P", "PBS-2", 10, [(branch_a.id, True)])
        armar_estado_por_sucursal(db, org.id, v, [branch_b.id], reemplazar=True)
        assert [p.branch_id for p in db.query(ProductBranchStatus).filter(ProductBranchStatus.variant_id == v.id).all()] == [branch_b.id]

    def test_reemplazar_sincroniza_la_relacion_ya_cargada(self, db, org, branch_a, branch_b):
        _, v = _make_product(db, org, "P", "PBS-5", 10, [(branch_a.id, True)])
        assert [p.branch_id for p in v.branch_statuses] == [branch_a.id]   # precarga la relación
        armar_estado_por_sucursal(db, org.id, v, [branch_b.id], reemplazar=True)
        assert [p.branch_id for p in v.branch_statuses] == [branch_b.id]

    def test_copiar_conserva_banderas_y_overrides(self, db, org, branch_a):
        _, origen = _make_product(db, org, "O", "PBS-3", 10, [(branch_a.id, True)])
        pbs = db.query(ProductBranchStatus).filter(ProductBranchStatus.variant_id == origen.id).one()
        pbs.price_override = Decimal("9.50")
        pbs.is_active_hq = True
        db.flush()
        _, destino = _make_product(db, org, "D", "PBS-4", 10)
        copiar_estado_por_sucursal(db, org.id, origen, destino)
        copia = db.query(ProductBranchStatus).filter(ProductBranchStatus.variant_id == destino.id).one()
        assert (copia.branch_id, copia.price_override, copia.is_active_hq) == (branch_a.id, Decimal("9.50"), True)


class TestExistencias:
    def test_stock_inicial_va_al_destino_y_cero_a_las_demas_con_kardex(self, db, org, branch_a, branch_b, admin_user):
        _, v = _make_product(db, org, "S", "SOH-1", 10)
        registrar_stock_inicial(db, org.id, v, [branch_a.id, branch_b.id], branch_b.id, Decimal("7"), admin_user.id)
        por_sucursal = {s.branch_id: s.qty_on_hand for s in db.query(StockOnHand).filter(StockOnHand.variant_id == v.id).all()}
        assert por_sucursal == {branch_a.id: Decimal("0"), branch_b.id: Decimal("7")}
        movs = db.query(InventoryMovement).filter(InventoryMovement.variant_id == v.id).all()
        assert len(movs) == 1
        assert (movs[0].branch_id, movs[0].reference, movs[0].notes) == (branch_b.id, "Alta Inicial", "Creación de producto")
        assert (movs[0].qty_before, movs[0].qty_after) == (Decimal("0"), Decimal("7"))

    def test_fijar_existencia_ajusta_por_diferencia_y_calla_si_no_cambia(self, db, org, branch_a, admin_user):
        _, v = _make_product(db, org, "F", "SOH-2", 10, [(branch_a.id, True)])   # nace con 100
        fijar_existencia(db, org.id, v, branch_a.id, Decimal("40"), admin_user.id, notas="Carga Masiva (Ajuste)")
        soh = db.query(StockOnHand).filter(StockOnHand.variant_id == v.id).one()
        assert soh.qty_on_hand == Decimal("40")
        mov = db.query(InventoryMovement).filter(InventoryMovement.variant_id == v.id).one()
        assert (mov.movement_type, mov.qty_change, mov.qty_before, mov.qty_after, mov.reference) == \
            (MovementType.ADJUSTMENT_OUT, Decimal("60"), Decimal("100"), Decimal("40"), "Excel Upload")
        fijar_existencia(db, org.id, v, branch_a.id, Decimal("40"), admin_user.id, notas="Carga Masiva (Ajuste)")
        assert db.query(InventoryMovement).filter(InventoryMovement.variant_id == v.id).count() == 1

    def test_fijar_existencia_crea_el_registro_si_no_existe(self, db, org, branch_b, admin_user):
        _, v = _make_product(db, org, "F", "SOH-3", 10)
        fijar_existencia(db, org.id, v, branch_b.id, Decimal("3"), admin_user.id, notas="Carga Masiva (Inicial)")
        soh = db.query(StockOnHand).filter(StockOnHand.variant_id == v.id).one()
        assert (soh.branch_id, soh.qty_on_hand) == (branch_b.id, Decimal("3"))
        mov = db.query(InventoryMovement).filter(InventoryMovement.variant_id == v.id).one()
        assert (mov.movement_type, mov.qty_change) == (MovementType.ADJUSTMENT_IN, Decimal("3"))
