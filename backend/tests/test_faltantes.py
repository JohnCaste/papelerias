"""
Lista de faltantes: journal local, reglas del servicio, sincronizacion a
BigQuery, reconstruccion y endpoints (todos los roles, todas las sucursales).

El journal de faltantes se aisla en tmp_path via conftest.py.
"""

import datetime

import pytest
from flask_jwt_extended import create_access_token

import main as modulo_main
from almacen_local import faltantes as journal_faltantes
from almacen_local import reconstruir_faltantes
from almacen_local import sincronizador
from faltantes import servicio
from faltantes.servicio import ErrorFaltantes


def _alta(usuario="u1", nombre_usuario="Miguel", **cambios):
    datos = {"nombre": "Cuaderno profesional raya", "producto_id": "p1", "cantidad": 5}
    datos.update(cambios)
    return servicio.crear(datos, usuario, nombre_usuario)


# ================================================================ journal

def test_journal_append_only_y_ultima_version_gana():
    journal_faltantes.escribir_faltante({"faltante_id": "f1", "nombre": "A", "estado": "pendiente"})
    journal_faltantes.escribir_faltante({"faltante_id": "f1", "nombre": "A", "cantidad": 3, "estado": "pendiente"})
    journal_faltantes.escribir_faltante({"faltante_id": "f2", "nombre": "B", "estado": "pendiente"})
    journal_faltantes.escribir_faltante({"faltante_id": "f2", "nombre": "B", "eliminado": True})

    vigentes = journal_faltantes.faltantes_vigentes()
    assert [(f["faltante_id"], f["cantidad"]) for f in vigentes] == [("f1", 3)]
    assert len(journal_faltantes.leer_eventos()) == 4


def test_pendientes_y_confirmados():
    e1 = journal_faltantes.escribir_faltante({"faltante_id": "f1"})
    e2 = journal_faltantes.escribir_faltante({"faltante_id": "f2"})
    assert {e["id"] for e in journal_faltantes.leer_pendientes()} == {e1["id"], e2["id"]}
    journal_faltantes.marcar_confirmados([e1["id"]])
    assert [e["id"] for e in journal_faltantes.leer_pendientes()] == [e2["id"]]


def test_journal_sin_archivo_no_crea_carpeta(tmp_path):
    assert journal_faltantes.leer_eventos() == []
    assert not (tmp_path / "faltantes").exists()


def test_no_permite_la_carpeta_real_bajo_pruebas(monkeypatch):
    monkeypatch.setattr(journal_faltantes, "CARPETA_POR_DEFECTO", journal_faltantes._CARPETA_REAL)
    with pytest.raises(RuntimeError):
        journal_faltantes.leer_eventos()


# ================================================================ servicio

def test_alta_desde_catalogo():
    f = _alta()
    assert (f["producto_id"], f["nombre"], f["cantidad"], f["estado"]) == ("p1", "Cuaderno profesional raya", 5, "pendiente")
    assert f["registrado_por"] == "Miguel" and f["usuario_id"] == "u1"
    assert [p["faltante_id"] for p in servicio.estado()["pendientes"]] == [f["faltante_id"]]


def test_alta_texto_libre_sin_cantidad_ni_nota():
    f = servicio.crear({"nombre": "  Hojas   opalina ", "nota": "  "}, "u1", "Miguel")
    assert (f["producto_id"], f["nombre"], f["cantidad"], f["nota"]) == (None, "Hojas opalina", None, None)


@pytest.mark.parametrize("cambios, campo", [
    ({"nombre": ""}, "nombre"),
    ({"nombre": "   "}, "nombre"),
    ({"nombre": "x" * 121}, "nombre"),
    ({"cantidad": 0}, "cantidad"),
    ({"cantidad": -2}, "cantidad"),
    ({"cantidad": 1.5}, "cantidad"),
    ({"cantidad": "dos"}, "cantidad"),
    ({"nota": "x" * 201}, "nota"),
])
def test_validaciones(cambios, campo):
    with pytest.raises(ErrorFaltantes) as error:
        _alta(**cambios)
    assert error.value.status == 400 and error.value.campo == campo
    assert journal_faltantes.leer_eventos() == []


def test_producto_repetido_en_pendientes_da_409():
    f = _alta()
    with pytest.raises(ErrorFaltantes) as error:
        _alta(cantidad=2)
    assert error.value.status == 409
    assert error.value.extra["faltante_id"] == f["faltante_id"]
    # Texto libre repetido si se permite.
    servicio.crear({"nombre": "Pegamento"}, "u1")
    servicio.crear({"nombre": "Pegamento"}, "u1")
    assert len(servicio.estado()["pendientes"]) == 3


def test_producto_comprado_se_puede_volver_a_pedir():
    f = _alta()
    servicio.cambiar_estado(f["faltante_id"], "comprado", "dueno", "Nadya")
    assert _alta()["estado"] == "pendiente"


def test_editar_cantidad_y_nota_conserva_historial():
    f = _alta()
    editado = servicio.editar(f["faltante_id"], {"cantidad": 10, "nota": "marca Scribe"}, "u2", "Ana")
    assert (editado["cantidad"], editado["nota"], editado["registrado_por"]) == (10, "marca Scribe", "Miguel")
    assert len(journal_faltantes.leer_eventos()) == 2


def test_marcar_comprado_y_regresar():
    f = _alta()
    comprado = servicio.cambiar_estado(f["faltante_id"], "comprado", "dueno", "Nadya")
    assert comprado["estado"] == "comprado" and comprado["comprado_por"] == "Nadya" and comprado["comprado_en"]
    estado = servicio.estado()
    assert estado["pendientes"] == [] and len(estado["comprados"]) == 1

    regresado = servicio.cambiar_estado(f["faltante_id"], "pendiente", "dueno", "Nadya")
    assert (regresado["estado"], regresado["comprado_por"], regresado["cantidad"]) == ("pendiente", None, 5)


def test_empleado_no_marca_comprado():
    f = _alta()
    with pytest.raises(ErrorFaltantes) as error:
        servicio.cambiar_estado(f["faltante_id"], "comprado", "empleado", "Miguel")
    assert error.value.status == 403
    assert servicio.estado()["pendientes"][0]["estado"] == "pendiente"


def test_estado_invalido():
    f = _alta()
    with pytest.raises(ErrorFaltantes) as error:
        servicio.cambiar_estado(f["faltante_id"], "perdido", "dueno")
    assert error.value.status == 400


def test_eliminar_permisos():
    f = _alta(usuario="u1")
    with pytest.raises(ErrorFaltantes) as error:
        servicio.eliminar(f["faltante_id"], "u2", "empleado")
    assert error.value.status == 403
    servicio.eliminar(f["faltante_id"], "u1", "empleado")
    assert servicio.estado()["pendientes"] == []

    otro = _alta(usuario="u1")
    servicio.eliminar(otro["faltante_id"], "u9", "dueno")
    with pytest.raises(ErrorFaltantes) as error:
        servicio.eliminar(otro["faltante_id"], "u9", "dueno")
    assert error.value.status == 404


def test_comprados_solo_ultimos_30_dias_y_orden():
    a = _alta(producto_id="pa", nombre="A")
    b = _alta(producto_id="pb", nombre="B")
    servicio.cambiar_estado(a["faltante_id"], "comprado", "dueno")
    servicio.cambiar_estado(b["faltante_id"], "comprado", "dueno")
    assert [c["nombre"] for c in servicio.estado()["comprados"]] == ["B", "A"]

    dentro_de_31 = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=31)
    assert servicio.estado(ahora=dentro_de_31)["comprados"] == []


def test_estado_cuenta_pendientes_de_subir():
    _alta()
    assert servicio.estado()["pendientes_de_subir"] == 1


# ================================================================ sincronizacion

def test_sincroniza_y_confirma(monkeypatch):
    _alta()
    insertado = {}
    monkeypatch.setattr(sincronizador, "insertar_filas", lambda tabla, filas: insertado.setdefault(tabla, filas))
    assert sincronizador.sincronizar_faltantes_una_vez() == {"enviados": 1, "exito": True, "error": None}
    filas = insertado[sincronizador.TABLA_FALTANTE]
    assert len(filas) == 1 and "evento" not in filas[0]
    assert journal_faltantes.leer_pendientes() == []


def test_falla_no_confirma_y_reintenta_con_mismos_ids(monkeypatch):
    _alta()

    def falla(tabla, filas):
        raise ConnectionError("sin internet")

    monkeypatch.setattr(sincronizador, "insertar_filas", falla)
    assert sincronizador.sincronizar_faltantes_una_vez()["exito"] is False
    ids_antes = {e["id"] for e in journal_faltantes.leer_pendientes()}

    enviados = []
    monkeypatch.setattr(sincronizador, "insertar_filas", lambda t, filas: enviados.extend(filas))
    sincronizador.sincronizar_faltantes_una_vez()
    assert {f["id"] for f in enviados} == ids_antes


def test_error_en_faltantes_no_frena_lo_demas(monkeypatch):
    llamados = []
    ok = lambda nombre, clave: (lambda **k: llamados.append(nombre) or {clave: 1, "exito": True, "error": None})
    monkeypatch.setattr(sincronizador, "sincronizar_una_vez", ok("ventas", "enviadas"))
    monkeypatch.setattr(sincronizador, "sincronizar_cierres_una_vez", ok("cierres", "enviados"))
    monkeypatch.setattr(sincronizador, "sincronizar_compras_una_vez", ok("compras", "enviados"))

    def explota(**k):
        raise RuntimeError("tabla faltante no existe")

    monkeypatch.setattr(sincronizador, "sincronizar_faltantes_una_vez", explota)
    monkeypatch.setattr(sincronizador, "_guardar_estado_persistido", lambda *a: None)

    resultado = sincronizador.Sincronizador().ejecutar_ciclo()
    assert llamados == ["ventas", "cierres", "compras"]
    assert resultado["compras_enviadas"] == 1 and resultado["faltantes_enviados"] == 0
    assert resultado["exito"] is False and "faltante" in resultado["error"]


# ================================================================ reconstruccion

def test_reconstruir_en_pc_nueva_da_los_mismos_vigentes(tmp_path):
    a = _alta()
    _alta(producto_id=None, nombre="Hojas opalina", cantidad=None)
    servicio.cambiar_estado(a["faltante_id"], "comprado", "dueno", "Nadya")
    antes = servicio.estado()
    filas = [{k: v for k, v in e.items() if k != "evento"}
             for e in journal_faltantes.leer_eventos() if e["evento"] == "faltante"]

    nueva = tmp_path / "pc_nueva"
    total = reconstruir_faltantes.reconstruir(carpeta=nueva, consultar=lambda sql: filas)

    assert total == 3
    assert journal_faltantes.leer_pendientes(nueva) == []
    despues = servicio.estado(carpeta=nueva)
    assert despues["pendientes"] == antes["pendientes"]
    assert despues["comprados"] == antes["comprados"]


def test_reconstruir_se_niega_con_pendientes():
    _alta()
    with pytest.raises(reconstruir_faltantes.ReconstruccionNoPermitida):
        reconstruir_faltantes.reconstruir(consultar=lambda sql: [])
    assert len(journal_faltantes.leer_eventos()) == 1


# ================================================================ endpoints

@pytest.fixture
def app(tmp_path):
    app = modulo_main.crear_app(carpeta_frontend=str(tmp_path))
    app.testing = True
    return app


def _h(app, rol="dueno", usuario="u1", nombre="Nadya"):
    with app.app_context():
        token = create_access_token(identity=usuario, additional_claims={"rol": rol, "nombre": nombre})
    return {"Authorization": f"Bearer {token}"}


def test_sin_token_401(app):
    assert app.test_client().get("/api/faltantes").status_code == 401


def test_flujo_empleado_y_duena_sin_bigquery(app, monkeypatch):
    def sin_bigquery(*a, **k):
        raise AssertionError("no debe consultar BigQuery")

    monkeypatch.setattr("acceso_datos.consultas.ejecutar_query", sin_bigquery)
    cliente = app.test_client()
    emp = _h(app, "empleado", "u2", "Miguel")
    duena = _h(app)

    r = cliente.post("/api/faltantes", json={"nombre": "Pegamento", "producto_id": "p9", "cantidad": 2}, headers=emp)
    assert r.status_code == 201
    faltante_id = r.get_json()["faltante_id"]

    r = cliente.post("/api/faltantes", json={"nombre": "Pegamento", "producto_id": "p9"}, headers=emp)
    assert r.status_code == 409 and r.get_json()["faltante_id"] == faltante_id

    r = cliente.put(f"/api/faltantes/{faltante_id}", json={"cantidad": 4}, headers=emp)
    assert r.status_code == 200 and r.get_json()["cantidad"] == 4

    assert cliente.put(f"/api/faltantes/{faltante_id}/estado", json={"estado": "comprado"}, headers=emp).status_code == 403
    r = cliente.put(f"/api/faltantes/{faltante_id}/estado", json={"estado": "comprado"}, headers=duena)
    assert r.status_code == 200 and r.get_json()["comprado_por"] == "Nadya"

    estado = cliente.get("/api/faltantes", headers=emp).get_json()
    assert estado["pendientes"] == [] and len(estado["comprados"]) == 1
    assert estado["pendientes_de_subir"] == 3

    assert cliente.delete(f"/api/faltantes/{faltante_id}", headers=_h(app, "empleado", "u3")).status_code == 403
    assert cliente.delete(f"/api/faltantes/{faltante_id}", headers=emp).status_code == 200
    assert cliente.delete(f"/api/faltantes/{faltante_id}", headers=emp).status_code == 404


def test_datos_invalidos_dan_400_con_campo(app):
    r = app.test_client().post("/api/faltantes", json={"nombre": "X", "cantidad": 0}, headers=_h(app))
    assert r.status_code == 400 and r.get_json()["campo"] == "cantidad"


def test_funciona_en_otra_sucursal(app, monkeypatch):
    monkeypatch.setattr("esquema.tablas.DATASET", "lapape_sucursal2")
    cliente = app.test_client()
    assert cliente.post("/api/faltantes", json={"nombre": "Foami"}, headers=_h(app, "empleado")).status_code == 201
    assert len(cliente.get("/api/faltantes", headers=_h(app)).get_json()["pendientes"]) == 1
