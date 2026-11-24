"""
Tests de main.py -- servir el frontend, fallback de SPA, y que las
rutas /api/* nunca se las trague el catch-all del frontend (#12).

Usa una carpeta temporal como 'frontend/dist' en vez del build real:
asi no depende de nombres de archivo con hash que cambian en cada build.
"""

import os

import pytest

import main as modulo_main


@pytest.fixture
def carpeta_frontend(tmp_path):
    (tmp_path / "index.html").write_text("<html>spa</html>", encoding="utf-8")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    return tmp_path


@pytest.fixture
def cliente(carpeta_frontend):
    app = modulo_main.crear_app(carpeta_frontend=str(carpeta_frontend))
    app.testing = True
    # Los endpoints de /api/* requieren JWT -- para estos tests solo
    # importa el ruteo del frontend, no la autenticacion.
    return app.test_client()


def test_raiz_sirve_index_html(cliente):
    respuesta = cliente.get("/")
    assert respuesta.status_code == 200
    assert b"spa" in respuesta.data


def test_ruta_de_react_router_hace_fallback_a_index_html(cliente):
    """/catalogo no es un archivo real; el SPA lo resuelve del lado del cliente."""
    respuesta = cliente.get("/catalogo")
    assert respuesta.status_code == 200
    assert b"spa" in respuesta.data


def test_archivo_estatico_real_se_sirve_tal_cual(cliente):
    respuesta = cliente.get("/assets/app.js")
    assert respuesta.status_code == 200
    assert b"console.log" in respuesta.data


def test_api_inexistente_da_404_no_index_html(cliente):
    """
    Una ruta /api/* que no coincide con ningun endpoint registrado no
    debe caer al fallback del SPA -- eso ocultaria el error real detras
    de una respuesta 200 con HTML.
    """
    respuesta = cliente.get("/api/esto-no-existe")
    assert respuesta.status_code == 404
    assert b"spa" not in respuesta.data


def test_rutas_api_reales_no_las_intercepta_el_catchall(cliente):
    """
    Las rutas /api/* registradas deben resolver a su vista real (aqui,
    dan 401 por jwt_required, no 200 con el HTML del SPA) -- confirma
    que Werkzeug prioriza las rutas especificas sobre el catch-all.
    """
    respuesta = cliente.get("/api/catalogo")
    assert respuesta.status_code != 200
    assert b"spa" not in respuesta.data


def test_dist_sin_index_html_da_404_con_mensaje_claro(tmp_path):
    carpeta_vacia = tmp_path / "vacia"
    carpeta_vacia.mkdir()
    app = modulo_main.crear_app(carpeta_frontend=str(carpeta_vacia))
    app.testing = True
    cliente = app.test_client()

    respuesta = cliente.get("/")
    assert respuesta.status_code == 404
    assert b"npm run build" in respuesta.data


def test_produccion_no_registra_cors(carpeta_frontend, monkeypatch):
    monkeypatch.setattr(modulo_main, "ENTORNO", "produccion")
    app = modulo_main.crear_app(carpeta_frontend=str(carpeta_frontend))
    respuesta = app.test_client().get("/api/catalogo")
    assert "Access-Control-Allow-Origin" not in respuesta.headers


def test_desarrollo_si_registra_cors(carpeta_frontend, monkeypatch):
    monkeypatch.setattr(modulo_main, "ENTORNO", "desarrollo")
    app = modulo_main.crear_app(carpeta_frontend=str(carpeta_frontend))
    respuesta = app.test_client().get(
        "/api/catalogo", headers={"Origin": "http://localhost:5173"}
    )
    assert respuesta.headers.get("Access-Control-Allow-Origin") == "http://localhost:5173"


# --------------------------------------------------------------------------
# JWT_SECRET_KEY viene de variable de entorno, no del codigo (#13)
# --------------------------------------------------------------------------


def test_usa_jwt_secret_key_de_la_variable_de_entorno(carpeta_frontend, monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "un-secreto-cualquiera-de-prueba")
    app = modulo_main.crear_app(carpeta_frontend=str(carpeta_frontend))
    assert app.config["JWT_SECRET_KEY"] == "un-secreto-cualquiera-de-prueba"


def test_desarrollo_sin_variable_usa_el_valor_fijo_de_desarrollo(carpeta_frontend, monkeypatch):
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    monkeypatch.setattr(modulo_main, "ENTORNO", "desarrollo")
    app = modulo_main.crear_app(carpeta_frontend=str(carpeta_frontend))
    assert app.config["JWT_SECRET_KEY"] == modulo_main._JWT_SECRET_KEY_DESARROLLO


def test_bajo_pytest_sin_variable_no_falla(carpeta_frontend, monkeypatch):
    """Los tests corren bajo pytest (LAPAPE_ENTORNO_PRUEBAS=1, ver
    conftest.py) incluso con ENTORNO='produccion' -- no deben requerir un
    .env real para construir la app."""
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    monkeypatch.setattr(modulo_main, "ENTORNO", "produccion")
    app = modulo_main.crear_app(carpeta_frontend=str(carpeta_frontend))
    assert app.config["JWT_SECRET_KEY"] == modulo_main._JWT_SECRET_KEY_DESARROLLO


def test_produccion_sin_variable_y_sin_pruebas_no_arranca(carpeta_frontend, monkeypatch):
    """Simula una corrida real en produccion (fuera del contexto de
    pytest): sin JWT_SECRET_KEY, crear_app() debe rehusarse a construir
    la app en vez de arrancar con un secreto debil o vacio."""
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    monkeypatch.setattr(modulo_main, "ENTORNO", "produccion")
    monkeypatch.setattr(modulo_main, "bajo_pruebas", lambda: False)

    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        modulo_main.crear_app(carpeta_frontend=str(carpeta_frontend))


# --------------------------------------------------------------------------
# iniciar_hilos_de_fondo / iniciar_servidor -- reutilizables entre
# `python main.py` en consola y el servicio de Windows (#servicio).
# --------------------------------------------------------------------------


def test_construir_la_app_no_arranca_ningun_hilo(carpeta_frontend):
    """Criterio de seguridad ya existente (ver comentario en crear_app):
    construir la app -- incluida la de un test -- nunca debe disparar un
    hilo real hablandole a BigQuery."""
    app = modulo_main.crear_app(carpeta_frontend=str(carpeta_frontend))

    assert app.sincronizador._hilo is None
    assert app.programador_cierre._hilo is None
    assert app.espejo_catalogo._hilo is None


def test_iniciar_hilos_de_fondo_arranca_los_tres(carpeta_frontend, monkeypatch):
    app = modulo_main.crear_app(carpeta_frontend=str(carpeta_frontend))

    llamados = []
    monkeypatch.setattr(app.sincronizador, "iniciar", lambda: llamados.append("sincronizador"))
    monkeypatch.setattr(
        app.programador_cierre, "iniciar", lambda: llamados.append("programador_cierre")
    )
    monkeypatch.setattr(
        app.espejo_catalogo, "iniciar", lambda: llamados.append("espejo_catalogo")
    )

    modulo_main.iniciar_hilos_de_fondo(app)

    assert set(llamados) == {"sincronizador", "programador_cierre", "espejo_catalogo"}
