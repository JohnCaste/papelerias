"""
Prueba de extremo a extremo real de /api/ventas: app completa de
main.py, JWT real, journal real en una carpeta temporal (sin BigQuery,
sin mocks de la vista). Es lo mas cercano a lo que hace el navegador.
"""

import pytest
from flask_jwt_extended import create_access_token

import main as modulo_main
from almacen_local import journal


@pytest.fixture
def app(tmp_path, monkeypatch):
    # El journal por defecto de main.py apunta a backend/datos_locales;
    # se redirige a una carpeta temporal para no tocar la real.
    monkeypatch.setattr(journal, "CARPETA_POR_DEFECTO", tmp_path)

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


def test_sin_token_da_401(cliente):
    respuesta = cliente.post("/api/ventas", json={"lineas": [{"categoria": "dulces", "monto": 10}]})
    assert respuesta.status_code == 401


def test_capturar_venta_de_extremo_a_extremo(cliente, token):
    respuesta = cliente.post(
        "/api/ventas",
        json={"lineas": [{"tipo": "categoria", "categoria": "dulces", "monto": 15}]},
        headers=_auth(token),
    )

    assert respuesta.status_code == 201
    data = respuesta.get_json()
    assert data["total"] == 15.0
    assert data["usuario_id"] == "usuario-de-prueba"
    assert data["id"]


def test_venta_capturada_aparece_de_inmediato_en_ventas_del_dia(cliente, token):
    cliente.post(
        "/api/ventas",
        json={"lineas": [{"tipo": "categoria", "categoria": "helados", "monto": 25}]},
        headers=_auth(token),
    )
    cliente.post(
        "/api/ventas",
        json={"lineas": [{"tipo": "categoria", "categoria": "copias", "monto": 5}]},
        headers=_auth(token),
    )

    respuesta = cliente.get("/api/ventas/dia", headers=_auth(token))
    data = respuesta.get_json()

    assert data["num_ventas"] == 2
    assert data["total"] == 30.0
    assert {v["estado_local"] for v in data["ventas"]} == {"pendiente"}


def test_captura_invalida_no_llega_al_journal(cliente, token, tmp_path):
    respuesta = cliente.post(
        "/api/ventas",
        json={"lineas": [{"tipo": "categoria", "categoria": "no-existe", "monto": 10}]},
        headers=_auth(token),
    )

    assert respuesta.status_code == 400
    assert list(tmp_path.glob("*.jsonl")) == []


# ------------------------------------------------ cancelacion (#26) end-to-end


def _hoy_iso():
    import datetime

    return datetime.date.today().isoformat()


def test_cancelar_venta_deja_la_original_intacta_y_baja_el_total(cliente, token):
    creada = cliente.post(
        "/api/ventas",
        json={"lineas": [{"tipo": "categoria", "categoria": "dulces", "monto": 40}]},
        headers=_auth(token),
    ).get_json()

    respuesta = cliente.post(
        f"/api/ventas/{creada['id']}/cancelar",
        json={"motivo": "cobro doble", "fecha": _hoy_iso()},
        headers=_auth(token),
    )
    assert respuesta.status_code == 201
    reversion = respuesta.get_json()
    assert reversion["venta_original_id"] == creada["id"]
    assert reversion["total"] == -40.0

    dia = cliente.get("/api/ventas/dia", headers=_auth(token)).get_json()
    # El total del dia baja a 0 por neteo; la venta original sigue visible
    # y marcada, y la fila de reversion no se lista como una venta mas.
    assert dia["total"] == 0.0
    assert dia["num_ventas"] == 1
    assert len(dia["ventas"]) == 1
    original = dia["ventas"][0]
    assert original["id"] == creada["id"]
    assert original["total"] == 40.0  # intacta
    assert original["cancelada"] is True


def test_cancelar_venta_inexistente_da_404(cliente, token):
    respuesta = cliente.post(
        "/api/ventas/no-existe/cancelar",
        json={"motivo": "x", "fecha": _hoy_iso()},
        headers=_auth(token),
    )
    assert respuesta.status_code == 404


def test_cancelar_sin_motivo_da_400(cliente, token):
    creada = cliente.post(
        "/api/ventas",
        json={"lineas": [{"tipo": "categoria", "categoria": "dulces", "monto": 10}]},
        headers=_auth(token),
    ).get_json()

    respuesta = cliente.post(
        f"/api/ventas/{creada['id']}/cancelar",
        json={"fecha": _hoy_iso()},
        headers=_auth(token),
    )
    assert respuesta.status_code == 400
