"""
Tests de /api/sincronizacion/estado (#55) -- y de que construir la app
(crear_app) nunca toque disco, ni siquiera al importarse durante la
recoleccion de pytest (la causa real de una fuga de datos investigada
durante el desarrollo de este issue).
"""

import threading

import pytest
from flask_jwt_extended import create_access_token

import main as modulo_main


def test_crear_app_no_toca_disco(tmp_path, monkeypatch):
    """
    Antes de la carga perezosa (#55), construir la app -- que pasa en
    cuanto pytest IMPORTA un archivo de test, antes de que cualquier
    fixture corra -- tocaba la carpeta real vía Sincronizador.__init__.
    Este test es la prueba directa de que ya no pasa.
    """
    from almacen_local import journal

    carpeta_vigilada = tmp_path / "no_debe_tocarse"
    monkeypatch.setattr(journal, "CARPETA_POR_DEFECTO", carpeta_vigilada)

    modulo_main.crear_app(carpeta_frontend=str(tmp_path))

    assert not carpeta_vigilada.exists()


def test_crear_app_no_arranca_hilos(tmp_path):
    antes = threading.active_count()
    modulo_main.crear_app(carpeta_frontend=str(tmp_path))
    despues = threading.active_count()
    assert antes == despues


@pytest.fixture
def app(tmp_path, monkeypatch):
    from almacen_local import cierres, journal

    monkeypatch.setattr(journal, "CARPETA_POR_DEFECTO", tmp_path)
    monkeypatch.setattr(cierres, "CARPETA_POR_DEFECTO", tmp_path)

    app = modulo_main.crear_app(carpeta_frontend=str(tmp_path))
    app.testing = True
    return app


@pytest.fixture
def token(app):
    with app.app_context():
        return create_access_token(identity="u1")


def test_estado_sincronizacion_sin_token_da_401(app):
    respuesta = app.test_client().get("/api/sincronizacion/estado")
    assert respuesta.status_code == 401


def test_estado_sincronizacion_recien_creada_no_ha_sincronizado(app, token):
    respuesta = app.test_client().get(
        "/api/sincronizacion/estado", headers={"Authorization": f"Bearer {token}"}
    )
    data = respuesta.get_json()

    assert data["ultima_sincronizacion_exitosa"] is None
    assert data["fallos_consecutivos"] == 0
    assert data["ultimo_error"] is None


def test_estado_sincronizacion_refleja_el_sincronizador_de_la_app(app, token, monkeypatch):
    """
    El endpoint debe reflejar el MISMO objeto que main.py arrancaria en
    __main__ -- no un valor inventado ni una instancia nueva por
    request.
    """
    monkeypatch.setattr(app.sincronizador, "ultimo_error", "sin internet")
    monkeypatch.setattr(app.sincronizador, "_fallos_consecutivos", 3)

    respuesta = app.test_client().get(
        "/api/sincronizacion/estado", headers={"Authorization": f"Bearer {token}"}
    )
    data = respuesta.get_json()

    assert data["ultimo_error"] == "sin internet"
    assert data["fallos_consecutivos"] == 3
