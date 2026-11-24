"""
Extremo a extremo real de /api/cierres/dia: app completa de main.py,
JWT real, journal y cierre local reales en carpetas temporales.
"""

import datetime

import pytest
from flask_jwt_extended import create_access_token

import main as modulo_main
from almacen_local import cierres, journal


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "CARPETA_POR_DEFECTO", tmp_path)
    monkeypatch.setattr(cierres, "CARPETA_POR_DEFECTO", tmp_path)

    app = modulo_main.crear_app(carpeta_frontend=str(tmp_path))
    app.testing = True
    return app


@pytest.fixture
def token(app):
    with app.app_context():
        return create_access_token(identity="usuario-de-prueba")


@pytest.fixture
def cliente(app):
    return app.test_client()


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_dia_sin_ventas_esta_abierto(cliente, token):
    respuesta = cliente.get("/api/cierres/dia", headers=_auth(token))
    data = respuesta.get_json()
    assert data["cerrado"] is False


def test_capturar_y_cerrar_el_dia_de_extremo_a_extremo(cliente, token):
    cliente.post(
        "/api/ventas",
        json={"lineas": [{"tipo": "categoria", "categoria": "dulces", "monto": 20}]},
        headers=_auth(token),
    )
    cliente.post(
        "/api/ventas",
        json={"lineas": [{"tipo": "categoria", "categoria": "papeleria", "monto": 30}]},
        headers=_auth(token),
    )

    respuesta = cliente.post("/api/cierres/dia", json={}, headers=_auth(token))
    assert respuesta.status_code == 201
    cierre = respuesta.get_json()
    assert cierre["total"] == 50.0
    assert cierre["num_ventas"] == 2

    consulta = cliente.get("/api/cierres/dia", headers=_auth(token))
    data = consulta.get_json()
    assert data["cerrado"] is True
    assert data["cierre"]["total"] == 50.0


def test_cerrar_dos_veces_no_duplica(cliente, token):
    cliente.post(
        "/api/ventas",
        json={"lineas": [{"tipo": "categoria", "categoria": "dulces", "monto": 20}]},
        headers=_auth(token),
    )

    primero = cliente.post("/api/cierres/dia", json={}, headers=_auth(token)).get_json()

    # Una venta capturada DESPUES de cerrar no debe alterar el cierre
    # ya generado (eso es #54, corrección de días cerrados).
    cliente.post(
        "/api/ventas",
        json={"lineas": [{"tipo": "categoria", "categoria": "dulces", "monto": 999}]},
        headers=_auth(token),
    )
    segundo = cliente.post("/api/cierres/dia", json={}, headers=_auth(token)).get_json()

    assert primero["id"] == segundo["id"]
    assert segundo["total"] == 20.0


def test_regenerar_acta_de_hoy_recoge_las_ventas_posteriores(cliente, token):
    cliente.post(
        "/api/ventas",
        json={"lineas": [{"tipo": "categoria", "categoria": "dulces", "monto": 20}]},
        headers=_auth(token),
    )
    primero = cliente.post("/api/cierres/dia", json={}, headers=_auth(token)).get_json()
    assert primero["total"] == 20.0

    cliente.post(
        "/api/ventas",
        json={"lineas": [{"tipo": "categoria", "categoria": "papeleria", "monto": 30}]},
        headers=_auth(token),
    )
    regenerado = cliente.post(
        "/api/cierres/dia/regenerar", json={}, headers=_auth(token)
    )
    assert regenerado.status_code == 201
    data = regenerado.get_json()
    assert data["total"] == 50.0
    assert data["id"] != primero["id"]

    estado = cliente.get("/api/cierres/dia", headers=_auth(token)).get_json()
    assert estado["cierre"]["total"] == 50.0
    assert estado["cierre"]["sincronizado"] is False


def test_regenerar_un_dia_pasado_da_409(cliente, token):
    ayer = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    respuesta = cliente.post(
        "/api/cierres/dia/regenerar", json={"fecha": ayer}, headers=_auth(token)
    )
    assert respuesta.status_code == 409


def test_sin_token_da_401(cliente):
    assert cliente.get("/api/cierres/dia").status_code == 401
    assert cliente.post("/api/cierres/dia", json={}).status_code == 401
    assert cliente.post("/api/cierres/dia/regenerar", json={}).status_code == 401
