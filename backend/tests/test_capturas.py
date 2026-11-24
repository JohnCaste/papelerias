"""
Tests de ventas/capturas.py -- vistas de Flask con el journal falseado
(unitarios) y, al final, un par de pruebas de extremo a extremo reales
con JWT contra el journal real en una carpeta temporal.
"""

import json

import pytest
from flask import Flask

import acceso_datos.repositorios.movimientos_inventario as movimientos_repo
import ventas.capturas as vista
from almacen_local import journal


@pytest.fixture
def app():
    app = Flask(__name__)
    app.testing = True
    return app


def _linea_categoria(categoria="papeleria", monto=20):
    return {"tipo": "categoria", "categoria": categoria, "monto": monto}


# ------------------------------------------------------- validaciones

def test_sin_lineas_da_400(app):
    with app.test_request_context("/api/ventas", method="POST", json={}):
        body, status = vista.capturar_venta()
    assert status == 400


def test_categoria_invalida_da_400(app):
    with app.test_request_context(
        "/api/ventas",
        method="POST",
        json={"lineas": [{"tipo": "categoria", "categoria": "no-existe", "monto": 10}]},
    ):
        body, status = vista.capturar_venta()
    assert status == 400
    assert "categoria invalida" in json.loads(body.get_data(as_text=True))["error"]


def test_monto_cero_o_negativo_da_400(app):
    with app.test_request_context(
        "/api/ventas",
        method="POST",
        json={"lineas": [_linea_categoria(monto=0)]},
    ):
        body, status = vista.capturar_venta()
    assert status == 400


def test_metodo_pago_invalido_da_400(app):
    with app.test_request_context(
        "/api/ventas",
        method="POST",
        json={"lineas": [_linea_categoria()], "metodo_pago": "bitcoin"},
    ):
        body, status = vista.capturar_venta()
    assert status == 400


def test_producto_sin_producto_id_da_400(app):
    with app.test_request_context(
        "/api/ventas",
        method="POST",
        json={"lineas": [{"tipo": "producto", "monto": 10}]},
    ):
        body, status = vista.capturar_venta()
    assert status == 400
    assert "producto_id" in json.loads(body.get_data(as_text=True))["error"]


def test_recarga_sin_comision_da_400(app):
    with app.test_request_context(
        "/api/ventas",
        method="POST",
        json={"lineas": [{"tipo": "recarga", "monto": 100}]},
    ):
        body, status = vista.capturar_venta()
    assert status == 400
    assert "comision" in json.loads(body.get_data(as_text=True))["error"]


def test_fecha_con_formato_invalido_en_dia_da_400(app):
    with app.test_request_context("/api/ventas/dia?fecha=no-es-fecha"):
        body, status = vista.listar_ventas_del_dia()
    assert status == 400


# ------------------------------------------- captura correcta (mockeada)

def test_captura_por_categoria_llama_al_journal_con_metodo_por_defecto(app, monkeypatch):
    capturado = {}

    def falso_escribir(datos):
        capturado.update(datos)
        return {**datos, "id": "v1"}

    monkeypatch.setattr(journal, "escribir_venta", falso_escribir)
    monkeypatch.setattr(vista, "get_jwt_identity", lambda: "u1")

    with app.test_request_context(
        "/api/ventas", method="POST", json={"lineas": [_linea_categoria("papeleria", 20)]}
    ):
        body, status = vista.capturar_venta()

    assert status == 201
    assert capturado["metodo_pago"] == "efectivo"  # default
    assert capturado["total"] == 20.0
    assert capturado["usuario_id"] == "u1"
    assert capturado["detallada"] is False
    assert capturado["lineas"][0]["categoria"] == "papeleria"


def test_captura_guarda_el_vendedor_del_token(app, monkeypatch):
    capturado = {}
    monkeypatch.setattr(
        journal, "escribir_venta", lambda datos: capturado.update(datos) or {**datos, "id": "v1"}
    )
    monkeypatch.setattr(vista, "get_jwt_identity", lambda: "u1")
    monkeypatch.setattr(vista, "get_jwt", lambda: {"nombre": "Ana"})

    with app.test_request_context(
        "/api/ventas", method="POST", json={"lineas": [_linea_categoria("papeleria", 20)]}
    ):
        body, status = vista.capturar_venta()

    assert status == 201
    assert capturado["vendedor"] == "Ana"


def test_captura_sin_nombre_en_el_token_guarda_vendedor_nulo(app, monkeypatch):
    capturado = {}
    monkeypatch.setattr(
        journal, "escribir_venta", lambda datos: capturado.update(datos) or {**datos, "id": "v1"}
    )
    monkeypatch.setattr(vista, "get_jwt_identity", lambda: "u1")
    monkeypatch.setattr(vista, "get_jwt", lambda: {})

    with app.test_request_context(
        "/api/ventas", method="POST", json={"lineas": [_linea_categoria("papeleria", 20)]}
    ):
        body, status = vista.capturar_venta()

    assert status == 201
    assert capturado["vendedor"] is None


@pytest.mark.parametrize("categoria", ["sublimacion", "limpieza", "otros"])
def test_categorias_nuevas_se_aceptan(app, monkeypatch, categoria):
    monkeypatch.setattr(journal, "escribir_venta", lambda datos: {**datos, "id": "v1"})
    monkeypatch.setattr(vista, "get_jwt_identity", lambda: "u1")
    monkeypatch.setattr(vista, "get_jwt", lambda: {})

    with app.test_request_context(
        "/api/ventas", method="POST", json={"lineas": [_linea_categoria(categoria, 30)]}
    ):
        body, status = vista.capturar_venta()

    assert status == 201


def test_captura_con_varias_lineas_suma_el_total(app, monkeypatch):
    capturado = {}
    monkeypatch.setattr(
        journal, "escribir_venta", lambda datos: capturado.update(datos) or {**datos, "id": "v1"}
    )
    monkeypatch.setattr(vista, "get_jwt_identity", lambda: "u1")

    with app.test_request_context(
        "/api/ventas",
        method="POST",
        json={"lineas": [_linea_categoria("papeleria", 20), _linea_categoria("dulces", 15)]},
    ):
        vista.capturar_venta()

    assert capturado["total"] == 35.0


def test_linea_de_producto_marca_la_venta_como_detallada(app, monkeypatch):
    capturado = {}
    monkeypatch.setattr(
        journal, "escribir_venta", lambda datos: capturado.update(datos) or {**datos, "id": "v1"}
    )
    monkeypatch.setattr(vista, "get_jwt_identity", lambda: "u1")

    with app.test_request_context(
        "/api/ventas",
        method="POST",
        json={"lineas": [{"tipo": "producto", "producto_id": "p1", "monto": 8, "cantidad": 2}]},
    ):
        vista.capturar_venta()

    assert capturado["detallada"] is True
    assert capturado["lineas"][0]["cantidad"] == 2.0


def test_listar_ventas_del_dia_sin_fecha_usa_hoy(app, monkeypatch):
    capturado = {}

    def falso_leer_dia(fecha):
        capturado["fecha"] = fecha
        return []

    monkeypatch.setattr(journal, "leer_dia", falso_leer_dia)

    with app.test_request_context("/api/ventas/dia"):
        respuesta = vista.listar_ventas_del_dia()

    data = json.loads(respuesta.get_data(as_text=True))
    assert data["num_ventas"] == 0
    assert data["total"] == 0


def test_listar_ventas_del_dia_suma_el_total(app, monkeypatch):
    monkeypatch.setattr(
        journal,
        "leer_dia",
        lambda fecha: [{"total": 20.0, "id": "a"}, {"total": 15.0, "id": "b"}],
    )

    with app.test_request_context("/api/ventas/dia?fecha=2026-08-31"):
        respuesta = vista.listar_ventas_del_dia()

    data = json.loads(respuesta.get_data(as_text=True))
    assert data["total"] == 35.0
    assert data["num_ventas"] == 2
    assert data["fecha"] == "2026-08-31"


# ---------------------------------------- aviso de stock (#21) -- nunca bloquea

def test_venta_sin_lineas_de_producto_no_consulta_stock(app, monkeypatch):
    llamado = []
    monkeypatch.setattr(movimientos_repo, "stock_de_varios", lambda ids: llamado.append(ids) or {})
    monkeypatch.setattr(
        journal, "escribir_venta", lambda datos: {**datos, "id": "v1"}
    )
    monkeypatch.setattr(vista, "get_jwt_identity", lambda: "u1")

    with app.test_request_context(
        "/api/ventas", method="POST", json={"lineas": [_linea_categoria()]}
    ):
        body, status = vista.capturar_venta()

    assert llamado == []
    assert "advertencias" not in json.loads(body.get_data(as_text=True))


def test_producto_con_stock_suficiente_no_trae_advertencias(app, monkeypatch):
    monkeypatch.setattr(movimientos_repo, "stock_de_varios", lambda ids: {"p1": 10})
    monkeypatch.setattr(
        journal, "escribir_venta", lambda datos: {**datos, "id": "v1"}
    )
    monkeypatch.setattr(vista, "get_jwt_identity", lambda: "u1")

    with app.test_request_context(
        "/api/ventas",
        method="POST",
        json={"lineas": [{"tipo": "producto", "producto_id": "p1", "monto": 5, "cantidad": 3}]},
    ):
        body, status = vista.capturar_venta()

    assert status == 201
    assert "advertencias" not in json.loads(body.get_data(as_text=True))


def test_producto_con_stock_en_cero_avisa_pero_igual_se_vende(app, monkeypatch):
    monkeypatch.setattr(movimientos_repo, "stock_de_varios", lambda ids: {"p1": 0})
    capturado = {}
    monkeypatch.setattr(
        journal,
        "escribir_venta",
        lambda datos: capturado.update(datos) or {**datos, "id": "v1"},
    )
    monkeypatch.setattr(vista, "get_jwt_identity", lambda: "u1")

    with app.test_request_context(
        "/api/ventas",
        method="POST",
        json={"lineas": [{"tipo": "producto", "producto_id": "p1", "monto": 5, "cantidad": 3}]},
    ):
        body, status = vista.capturar_venta()

    data = json.loads(body.get_data(as_text=True))
    assert status == 201  # nunca se bloquea por stock
    assert capturado["lineas"]  # la venta se escribio igual
    assert len(data["advertencias"]) == 1
    assert "p1" in data["advertencias"][0]


def test_producto_con_bigquery_caido_no_avisa_y_no_revienta(app, monkeypatch):
    def truena(ids):
        raise ConnectionError("sin internet")

    monkeypatch.setattr(movimientos_repo, "stock_de_varios", truena)
    monkeypatch.setattr(
        journal, "escribir_venta", lambda datos: {**datos, "id": "v1"}
    )
    monkeypatch.setattr(vista, "get_jwt_identity", lambda: "u1")

    with app.test_request_context(
        "/api/ventas",
        method="POST",
        json={"lineas": [{"tipo": "producto", "producto_id": "p1", "monto": 5, "cantidad": 3}]},
    ):
        body, status = vista.capturar_venta()

    assert status == 201
    assert "advertencias" not in json.loads(body.get_data(as_text=True))


# ------------------------------------ dia cerrado (#50) -- nunca se bloquea

def test_capturar_con_dia_abierto_no_marca_extemporanea(app, monkeypatch):
    capturado = {}
    monkeypatch.setattr(vista.cierres, "ya_cerrado", lambda fecha: False)
    monkeypatch.setattr(
        journal, "escribir_venta", lambda datos: capturado.update(datos) or {**datos, "id": "v1"}
    )
    monkeypatch.setattr(vista, "get_jwt_identity", lambda: "u1")

    with app.test_request_context(
        "/api/ventas", method="POST", json={"lineas": [_linea_categoria("papeleria", 20)]}
    ):
        body, status = vista.capturar_venta()

    assert status == 201
    assert capturado["extemporanea"] is False


def test_capturar_con_dia_cerrado_marca_extemporanea_pero_no_rechaza(app, monkeypatch):
    """
    Principio central: el sistema NUNCA rechaza una venta por el
    cierre del dia (#22). Si el dia ya cerro, la venta se guarda igual,
    solo marcada para que #54 la reconcilie despues.
    """
    capturado = {}
    monkeypatch.setattr(vista.cierres, "ya_cerrado", lambda fecha: True)
    monkeypatch.setattr(
        journal, "escribir_venta", lambda datos: capturado.update(datos) or {**datos, "id": "v1"}
    )
    monkeypatch.setattr(vista, "get_jwt_identity", lambda: "u1")

    with app.test_request_context(
        "/api/ventas", method="POST", json={"lineas": [_linea_categoria("papeleria", 20)]}
    ):
        body, status = vista.capturar_venta()

    assert status == 201  # nunca 4xx/5xx por esto
    assert capturado["extemporanea"] is True
