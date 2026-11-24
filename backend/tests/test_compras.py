"""
Compras de trabajadores: journal local, calculos/validaciones, sincronizacion
a BigQuery, reconstruccion y endpoints (candado sucursal + rol).

El journal de compras se aisla en tmp_path via conftest.py.
"""

import datetime

import pytest
from flask_jwt_extended import create_access_token

import main as modulo_main
from almacen_local import compras as journal_compras
from almacen_local import reconstruir_compras
from almacen_local import sincronizador
from compras import acceso, servicio
from compras.servicio import ErrorCompras

HOY = datetime.date(2026, 11, 4)


@pytest.fixture(autouse=True)
def _hoy_fijo(monkeypatch):
    monkeypatch.setattr(servicio.zona_negocio, "hoy", lambda: HOY)


def _alta(**cambios):
    datos = {"nombre": "Ana", "producto": "Cuaderno", "cantidad": 2, "precio": 45,
             "fecha": "2026-11-04", "pago": 50}
    datos.update(cambios)
    return servicio.crear_compra(datos, "u1", "Nadya")


# ================================================================ journal

def test_journal_append_only_y_ultima_version_gana():
    journal_compras.escribir_compra({"compra_id": "c1", "nombre": "Ana", "cantidad": 1})
    journal_compras.escribir_compra({"compra_id": "c1", "nombre": "Ana B", "cantidad": 3})
    journal_compras.escribir_compra({"compra_id": "c2", "nombre": "Luis", "cantidad": 1})
    journal_compras.escribir_compra({"compra_id": "c2", "nombre": "Luis", "eliminada": True})

    vigentes = journal_compras.compras_vigentes()
    assert [(c["compra_id"], c["nombre"], c["cantidad"]) for c in vigentes] == [("c1", "Ana B", 3)]
    assert len(journal_compras.leer_eventos()) == 4  # nada se reescribe


def test_pendientes_y_confirmados():
    e1 = journal_compras.escribir_compra({"compra_id": "c1"})
    e2 = journal_compras.escribir_abono({"abono_id": "a1", "compra_id": "c1", "monto": "5.00"})
    assert {e["id"] for e in journal_compras.leer_pendientes()} == {e1["id"], e2["id"]}

    journal_compras.marcar_confirmados([e1["id"]])
    assert [e["id"] for e in journal_compras.leer_pendientes()] == [e2["id"]]


def test_journal_sin_archivo_no_crea_carpeta(tmp_path):
    assert journal_compras.leer_eventos() == []
    assert not (tmp_path / "compras").exists()


def test_no_permite_la_carpeta_real_bajo_pruebas(monkeypatch):
    monkeypatch.setattr(journal_compras, "CARPETA_POR_DEFECTO", journal_compras._CARPETA_REAL)
    with pytest.raises(RuntimeError):
        journal_compras.leer_eventos()


# ================================================================ calculos

def test_compra_con_pago_inicial_queda_parcial():
    compra = _alta()
    assert (compra["importe"], compra["pagado"], compra["total"], compra["estatus"]) == (90, 50, 40, "parcial")

    estado = servicio.estado()
    assert [a["monto"] for a in estado["abonos"]] == [50]
    assert estado["abonos"][0]["registrado_por"] == "Nadya"


def test_compra_sin_abonos_pendiente():
    compra = _alta(producto="Toner", cantidad=1, precio=380, pago=0)
    assert (compra["total"], compra["estatus"]) == (380, "pendiente")


def test_compra_liquidada_y_de_importe_cero():
    assert _alta(cantidad=5, precio=12, pago=60)["estatus"] == "pagado"
    cero = _alta(precio=0, pago=0)
    assert (cero["total"], cero["estatus"]) == (0, "pagado")


def test_decimales_sin_errores_de_float():
    compra = _alta(cantidad=3, precio="0.10", pago="0.10")
    assert compra["importe"] == 0.3
    assert compra["total"] == 0.2


@pytest.mark.parametrize("cambios,campo", [
    ({"cantidad": 0}, "cantidad"),
    ({"cantidad": 1.5}, "cantidad"),
    ({"precio": -1}, "precio"),
    ({"nombre": "   "}, "nombre"),
    ({"producto": ""}, "producto"),
    ({"pago": 100}, "pago"),  # mayor que el importe (90)
    ({"fecha": "2026-11-05"}, "fecha"),  # futura
    ({"fecha": "ayer"}, "fecha"),
])
def test_validaciones_de_alta(cambios, campo):
    with pytest.raises(ErrorCompras) as error:
        _alta(**cambios)
    assert error.value.campo == campo
    assert journal_compras.leer_eventos() == []


def test_abonos_completar_excesivo_y_eliminar():
    compra = _alta()
    with pytest.raises(ErrorCompras) as error:
        servicio.abonar(compra["compra_id"], {"monto": 50}, "u1")
    assert "40" in error.value.mensaje

    with pytest.raises(ErrorCompras):
        servicio.abonar(compra["compra_id"], {"monto": 0}, "u1")

    r = servicio.abonar(compra["compra_id"], {"monto": 40}, "u1")
    assert r["compra"]["estatus"] == "pagado"

    servicio.eliminar_abono(r["abono_id"], "u1")
    estado = servicio.estado()
    assert estado["compras"][0]["pagado"] == 50
    assert len(estado["abonos"]) == 1

    with pytest.raises(ErrorCompras) as error:
        servicio.eliminar_abono(r["abono_id"], "u1")
    assert error.value.status == 404


def test_editar_cantidad_y_rechazar_saldo_negativo():
    compra = _alta()
    editada = servicio.editar_compra(
        compra["compra_id"],
        {"nombre": "Ana", "producto": "Cuaderno", "cantidad": 3, "precio": 45, "fecha": "2026-11-04"},
        "u1",
    )
    assert (editada["importe"], editada["total"], editada["estatus"]) == (135, 85, "parcial")

    with pytest.raises(ErrorCompras):
        servicio.editar_compra(
            compra["compra_id"],
            {"nombre": "Ana", "producto": "Cuaderno", "cantidad": 1, "precio": 30, "fecha": "2026-11-04"},
            "u1",
        )
    assert servicio.estado()["compras"][0]["importe"] == 135


def test_eliminar_compra_quita_compra_abonos_y_resumen():
    compra = _alta()
    servicio.eliminar_compra(compra["compra_id"], "u1")
    estado = servicio.estado()
    assert estado["compras"] == [] and estado["abonos"] == []
    assert estado["resumen"] == {"por_cobrar": 0, "compras_abiertas": 0, "abonado_mes": 0}

    with pytest.raises(ErrorCompras) as error:
        servicio.abonar(compra["compra_id"], {"monto": 1}, "u1")
    assert error.value.status == 404


def test_nombres_normalizados_y_agrupados():
    _alta(nombre="Ana")
    nueva = _alta(nombre="  ana  ")
    assert nueva["nombre"] == "Ana"  # adopta la forma ya registrada
    _alta(nombre="Luis  Perez")
    assert servicio.estado()["nombres"] == ["Ana", "Luis Perez"]


def test_resumen():
    _alta()  # total 40, abonado 50 este mes
    _alta(producto="Toner", cantidad=1, precio=380, pago=0)
    _alta(producto="Plumas", cantidad=5, precio=12, pago=60, fecha="2026-10-20")
    resumen = servicio.estado()["resumen"]
    assert resumen == {"por_cobrar": 420, "compras_abiertas": 2, "abonado_mes": 50}


def test_estado_cuenta_pendientes_de_subir():
    _alta()
    assert servicio.estado()["pendientes_subir"] == 2  # compra + abono inicial


# ================================================================ sincronizacion

def test_sincroniza_y_confirma(monkeypatch):
    _alta()
    insertado = {}
    monkeypatch.setattr(
        sincronizador, "insertar_filas", lambda tabla, filas: insertado.setdefault(tabla, filas)
    )
    resultado = sincronizador.sincronizar_compras_una_vez()

    assert resultado == {"enviados": 2, "exito": True, "error": None}
    assert len(insertado[sincronizador.TABLA_COMPRA_TRABAJADOR]) == 1
    assert len(insertado[sincronizador.TABLA_ABONO_COMPRA]) == 1
    assert all("evento" not in f for filas in insertado.values() for f in filas)
    assert journal_compras.leer_pendientes() == []


def test_falla_no_confirma_y_reintenta_con_mismos_ids(monkeypatch):
    _alta()

    def falla(tabla, filas):
        raise ConnectionError("sin internet")

    monkeypatch.setattr(sincronizador, "insertar_filas", falla)
    assert sincronizador.sincronizar_compras_una_vez()["exito"] is False
    ids_antes = {e["id"] for e in journal_compras.leer_pendientes()}
    assert len(ids_antes) == 2

    enviados = []
    monkeypatch.setattr(sincronizador, "insertar_filas", lambda t, filas: enviados.extend(filas))
    sincronizador.sincronizar_compras_una_vez()
    assert {f["id"] for f in enviados} == ids_antes


def test_error_en_compras_no_frena_ventas_ni_cierres(monkeypatch):
    llamados = []
    monkeypatch.setattr(sincronizador, "sincronizar_una_vez",
                        lambda **k: llamados.append("ventas") or {"enviadas": 1, "exito": True, "error": None})
    monkeypatch.setattr(sincronizador, "sincronizar_cierres_una_vez",
                        lambda **k: llamados.append("cierres") or {"enviados": 0, "exito": True, "error": None})

    def explota(**k):
        raise RuntimeError("tabla compra_trabajador no existe")

    monkeypatch.setattr(sincronizador, "sincronizar_compras_una_vez", explota)
    monkeypatch.setattr(sincronizador, "_guardar_estado_persistido", lambda *a: None)

    resultado = sincronizador.Sincronizador().ejecutar_ciclo()
    assert llamados == ["ventas", "cierres"]
    assert resultado["ventas_enviadas"] == 1
    assert resultado["exito"] is False


# ================================================================ reconstruccion

def _consultar_desde(eventos):
    compras = [{k: v for k, v in e.items() if k != "evento"} for e in eventos if e["evento"] == "compra"]
    abonos = [{k: v for k, v in e.items() if k != "evento"} for e in eventos if e["evento"] == "abono"]
    return lambda sql: compras if "compra_trabajador" in sql else abonos


def test_reconstruir_en_pc_nueva_da_los_mismos_saldos(tmp_path):
    compra = _alta()
    servicio.abonar(compra["compra_id"], {"monto": 10}, "u1")
    _alta(producto="Toner", cantidad=1, precio=380, pago=0)
    antes = servicio.estado()
    eventos = journal_compras.leer_eventos()

    nueva = tmp_path / "pc_nueva"
    total = reconstruir_compras.reconstruir(carpeta=nueva, consultar=_consultar_desde(eventos))

    assert total == 4
    assert journal_compras.leer_pendientes(nueva) == []
    despues = servicio.estado(carpeta=nueva)
    assert despues["resumen"] == antes["resumen"]
    assert [c["total"] for c in despues["compras"]] == [c["total"] for c in antes["compras"]]


def test_reconstruir_se_niega_con_pendientes():
    _alta()
    with pytest.raises(reconstruir_compras.ReconstruccionNoPermitida):
        reconstruir_compras.reconstruir(consultar=lambda sql: [])
    assert len(journal_compras.leer_eventos()) == 2


# ================================================================ endpoints

@pytest.fixture
def app(tmp_path):
    app = modulo_main.crear_app(carpeta_frontend=str(tmp_path))
    app.testing = True
    return app


def _token(app, rol):
    with app.app_context():
        return create_access_token(identity="u1", additional_claims={"rol": rol, "nombre": "Nadya"})


def _h(app, rol="dueno"):
    return {"Authorization": f"Bearer {_token(app, rol)}"}


def test_otra_sucursal_da_404_sin_tocar_el_journal(app, monkeypatch, tmp_path):
    monkeypatch.setattr(acceso.tablas, "DATASET", "lapape_sucursal2")
    cliente = app.test_client()
    assert cliente.get("/api/compras", headers=_h(app)).status_code == 404
    assert cliente.post("/api/compras", json={}, headers=_h(app)).status_code == 404
    assert not (tmp_path / "compras").exists()


def test_empleado_da_403_y_sin_token_401(app):
    cliente = app.test_client()
    assert cliente.get("/api/compras", headers=_h(app, "empleado")).status_code == 403
    assert cliente.get("/api/compras").status_code == 401


def test_flujo_completo_sin_bigquery(app, monkeypatch):
    def sin_bigquery(*a, **k):
        raise AssertionError("no debe consultar BigQuery")

    monkeypatch.setattr("acceso_datos.consultas.ejecutar_query", sin_bigquery)
    cliente = app.test_client()
    h = _h(app)

    r = cliente.post("/api/compras", json={"nombre": "Ana", "producto": "Cuaderno",
                                           "cantidad": 2, "precio": 45, "fecha": "2026-11-04",
                                           "pago": 50}, headers=h)
    assert r.status_code == 201
    compra_id = r.get_json()["compra_id"]

    r = cliente.post(f"/api/compras/{compra_id}/abonos", json={"monto": 20}, headers=h)
    assert r.status_code == 201 and r.get_json()["compra"]["total"] == 20
    abono_id = r.get_json()["abono_id"]

    assert cliente.delete(f"/api/compras/abonos/{abono_id}", headers=h).status_code == 200
    assert len(cliente.get("/api/compras/abonos", headers=h).get_json()) == 1

    r = cliente.put(f"/api/compras/{compra_id}", json={"nombre": "Ana", "producto": "Cuaderno",
                                                      "cantidad": 3, "precio": 45,
                                                      "fecha": "2026-11-04"}, headers=h)
    assert r.status_code == 200 and r.get_json()["total"] == 85

    assert cliente.delete(f"/api/compras/{compra_id}", headers=h).status_code == 200
    assert cliente.get("/api/compras", headers=h).get_json()["compras"] == []


def test_datos_invalidos_dan_400_con_campo(app):
    r = app.test_client().post("/api/compras", json={"nombre": "Ana", "producto": "X",
                                                     "cantidad": 0, "precio": 1}, headers=_h(app))
    assert r.status_code == 400
    assert r.get_json()["campo"] == "cantidad"
