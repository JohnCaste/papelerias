"""
Tests de que crear/actualizar/eliminar un producto (catalogos/productos.py)
refleja el cambio de inmediato en el espejo local (#13), sin esperar el
ciclo de refresco periodico -- y que un fallo al escribir en el espejo
nunca cambia la respuesta HTTP de la operacion real (BigQuery, ya
confirmada). BigQuery se mockea (nunca se toca la red); el espejo local
usa el archivo temporal que ya redirige tests/conftest.py.
"""

import json

import pytest
from flask import Flask

import acceso_datos.repositorios.productos_local as productos_local
import catalogos.productos as vista


@pytest.fixture
def app():
    app = Flask(__name__)
    app.testing = True
    return app


def _producto_bigquery(**overrides):
    base = {
        "id": "p1",
        "codigo_barras": None,
        "codigo_interno": None,
        "nombre": "Pluma",
        "categoria": "Escritura",
        "marca": None,
        "descripcion": None,
        "imagen": None,
        "precio": 10.0,
        "costo": None,
        "stock_minimo": None,
        "activo": True,
    }
    base.update(overrides)
    return base


def test_crear_producto_se_ve_de_inmediato_en_el_espejo(app, monkeypatch):
    monkeypatch.setattr(vista.productos_repo, "obtener_por_codigo_barras", lambda c: None)
    monkeypatch.setattr(
        vista.productos_repo, "crear", lambda datos: _producto_bigquery(nombre=datos["nombre"])
    )
    monkeypatch.setattr(vista.movimientos_repo, "stock_de_varios", lambda ids: {"p1": 0})

    with app.test_request_context(
        "/api/catalogo",
        method="POST",
        json={"nombre": "Recien creado", "categoria": "Escritura", "precio": 15},
    ):
        vista.agregar_productos()

    # Sin esperar ningun ciclo de refresco: ya aparece en una busqueda local.
    filas, total = productos_local.buscar_con_total(termino="Recien creado")
    assert total == 1
    assert filas[0]["nombre"] == "Recien creado"


def test_actualizar_producto_se_ve_de_inmediato_en_el_espejo(app, monkeypatch):
    # El producto ya existia en el espejo (como si un refresco previo lo
    # hubiera puesto ahi) con el precio viejo.
    productos_local.upsert_producto(_producto_bigquery(precio=10, cantidad=0))

    monkeypatch.setattr(vista.productos_repo, "actualizar", lambda id_, datos: None)
    monkeypatch.setattr(
        vista.productos_repo,
        "obtener_por_id",
        lambda id_: _producto_bigquery(precio=99),
    )
    monkeypatch.setattr(vista.movimientos_repo, "stock_de_varios", lambda ids: {"p1": 0})

    with app.test_request_context(
        "/api/catalogo", method="PATCH", json={"id": "p1", "precio": 99}
    ):
        vista.actualizar_productos()

    filas, _ = productos_local.buscar_con_total(termino="Pluma")
    assert filas[0]["precio"] == 99.0


def test_eliminar_producto_desaparece_de_inmediato_del_espejo(app, monkeypatch):
    productos_local.upsert_producto(_producto_bigquery(cantidad=0))
    assert productos_local.buscar_con_total(termino="Pluma")[1] == 1

    monkeypatch.setattr(vista.productos_repo, "eliminar", lambda id_: None)

    with app.test_request_context("/api/catalogo?id=p1", method="DELETE"):
        vista.eliminar_productos()

    assert productos_local.buscar_con_total(termino="Pluma")[1] == 0


def test_fallo_al_escribir_en_el_espejo_no_cambia_la_respuesta_http(app, monkeypatch):
    """Si BigQuery (la fuente de verdad) ya confirmo el alta, un fallo al
    reflejarlo en el espejo local NUNCA debe convertirse en un error para
    el cliente."""
    monkeypatch.setattr(vista.productos_repo, "obtener_por_codigo_barras", lambda c: None)
    monkeypatch.setattr(
        vista.productos_repo, "crear", lambda datos: _producto_bigquery(nombre=datos["nombre"])
    )
    monkeypatch.setattr(vista.movimientos_repo, "stock_de_varios", lambda ids: {"p1": 0})

    def _truena(producto):
        raise RuntimeError("disco lleno")

    monkeypatch.setattr(vista.productos_local, "upsert_producto", _truena)

    with app.test_request_context(
        "/api/catalogo",
        method="POST",
        json={"nombre": "Pluma", "categoria": "Escritura", "precio": 8},
    ):
        body, status = vista.agregar_productos()

    assert status == 201
    data = json.loads(body.get_data(as_text=True))
    assert data["nombre"] == "Pluma"


def test_fallo_al_eliminar_del_espejo_no_cambia_la_respuesta_http(app, monkeypatch):
    monkeypatch.setattr(vista.productos_repo, "eliminar", lambda id_: None)

    def _truena(id_):
        raise RuntimeError("disco lleno")

    monkeypatch.setattr(vista.productos_local, "marcar_inactivo", _truena)

    with app.test_request_context("/api/catalogo?id=p1", method="DELETE"):
        respuesta = vista.eliminar_productos()

    data = json.loads(respuesta.get_data(as_text=True))
    assert data == {"ok": True}
