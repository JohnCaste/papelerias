"""
Tests de utilidades/registro.py (logging a archivo, #13) y del manejador
de errores no capturados de main.py.
"""

import logging

import pytest

import main as modulo_main
import utilidades.registro as registro


@pytest.fixture(autouse=True)
def _resetear_logging():
    """Cada test arranca sin handlers previos y deja el logger raiz limpio
    al terminar -- si no, un test que configura logging afecta a los que
    corren despues (el logger raiz es un singleton del proceso)."""
    registro.resetear_configuracion()
    yield
    registro.resetear_configuracion()


def test_configurar_logging_crea_el_archivo(tmp_path):
    archivo = registro.configurar_logging(carpeta=tmp_path, entorno="produccion")

    assert archivo == tmp_path / registro._NOMBRE_ARCHIVO
    assert archivo.exists()


def test_configurar_logging_es_idempotente(tmp_path):
    """Llamarla dos veces no duplica handlers (no se duplicarian los
    mensajes en el archivo)."""
    registro.configurar_logging(carpeta=tmp_path, entorno="produccion")
    handlers_antes = len(logging.getLogger().handlers)

    registro.configurar_logging(carpeta=tmp_path, entorno="produccion")
    handlers_despues = len(logging.getLogger().handlers)

    assert handlers_antes == handlers_despues


def test_un_mensaje_de_un_logger_de_modulo_queda_en_el_archivo(tmp_path):
    """Simula lo que ya hacen almacen_local/sincronizador.py y
    programador_cierre.py: loguean con logging.getLogger(__name__) sin
    configurar nada ellos mismos -- deben heredar del logger raiz."""
    archivo = registro.configurar_logging(carpeta=tmp_path, entorno="produccion")

    logger_de_modulo = logging.getLogger("almacen_local.sincronizador")
    logger_de_modulo.error("fallo al subir el dia 2026-09-08 a BigQuery")

    contenido = archivo.read_text(encoding="utf-8")
    assert "ERROR" in contenido
    assert "almacen_local.sincronizador" in contenido
    assert "fallo al subir el dia 2026-09-08 a BigQuery" in contenido


def test_nivel_debug_solo_en_desarrollo(tmp_path):
    archivo = registro.configurar_logging(carpeta=tmp_path, entorno="desarrollo")

    logging.getLogger("x").debug("mensaje de depuracion")

    assert "mensaje de depuracion" in archivo.read_text(encoding="utf-8")


def test_nivel_info_en_produccion_descarta_debug(tmp_path):
    archivo = registro.configurar_logging(carpeta=tmp_path, entorno="produccion")

    logging.getLogger("x").debug("no deberia aparecer")
    logging.getLogger("x").info("si deberia aparecer")

    contenido = archivo.read_text(encoding="utf-8")
    assert "no deberia aparecer" not in contenido
    assert "si deberia aparecer" in contenido


def test_desarrollo_tambien_agrega_handler_de_consola(tmp_path):
    registro.configurar_logging(carpeta=tmp_path, entorno="desarrollo")

    tipos = [type(h).__name__ for h in logging.getLogger().handlers]
    assert "StreamHandler" in tipos
    assert "RotatingFileHandler" in tipos


def test_produccion_no_agrega_handler_de_consola(tmp_path):
    registro.configurar_logging(carpeta=tmp_path, entorno="produccion")

    tipos = [type(h).__name__ for h in logging.getLogger().handlers]
    assert "StreamHandler" not in tipos


# --------------------------------------------------------------------------
# Excepciones no capturadas en un endpoint quedan registradas (main.py)
# --------------------------------------------------------------------------


def test_excepcion_no_capturada_en_un_endpoint_queda_registrada(tmp_path, caplog):
    registro.configurar_logging(carpeta=tmp_path, entorno="produccion")

    app = modulo_main.crear_app(carpeta_frontend=str(tmp_path))
    app.testing = True
    # Sin esto, Flask en modo testing relanza la excepcion en vez de
    # pasarla por el errorhandler -- aqui interesa probar justo ese
    # manejador, que es el que corre de verdad en produccion (Waitress).
    app.config["PROPAGATE_EXCEPTIONS"] = False

    @app.route("/_reventar_a_proposito")
    def _reventar():
        raise RuntimeError("boom")

    cliente = app.test_client()

    with caplog.at_level(logging.ERROR):
        respuesta = cliente.get("/_reventar_a_proposito")

    assert respuesta.status_code == 500
    assert respuesta.get_json() == {"error": "Error interno del servidor"}
    assert any(
        registro_de_log.levelname == "ERROR" and "boom" in registro_de_log.exc_text
        for registro_de_log in caplog.records
        if registro_de_log.exc_text
    )


def test_error_http_a_proposito_no_se_registra_como_error(tmp_path, caplog):
    """Un abort(404) es una respuesta normal, no una falla inesperada --
    no debe inflar el log con ruido."""
    registro.configurar_logging(carpeta=tmp_path, entorno="produccion")

    app = modulo_main.crear_app(carpeta_frontend=str(tmp_path))
    app.testing = True
    app.config["PROPAGATE_EXCEPTIONS"] = False
    cliente = app.test_client()

    with caplog.at_level(logging.ERROR):
        respuesta = cliente.get("/api/ruta-que-no-existe")

    assert respuesta.status_code == 404
    assert not any(r.levelname == "ERROR" for r in caplog.records)
