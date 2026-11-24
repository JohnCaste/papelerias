"""
Logging a archivo del backend (#13 -- primer paso hacia correr sin
consola visible, camino a servicio de Windows / startup app).

Hasta esta version, `sincronizador.py` y `programador_cierre.py` ya
llamaban a `logging.getLogger(__name__)` y emitian mensajes, pero sin
ningun handler configurado esos mensajes se perdian (o solo se veian si
la ventana de la consola seguia abierta). `configurar_logging()` se
llama UNA VEZ al arrancar el proceso (ver backend/main.py) y deja todo
el logging del backend -- incluidos esos hilos en segundo plano --
escribiendo a archivo con rotacion, sin que esos modulos cambien nada.

    logging.getLogger(__name__) en cualquier modulo
                    |
                    v (hereda del logger raiz, configurado aqui una vez)
    backend/datos_locales/logs/backend.log  (+ consola en desarrollo)
"""

import logging
import logging.handlers
import os
from pathlib import Path

from almacen_local._seguridad_pruebas import verificar_no_es_carpeta_real

_CARPETA_REAL = Path(__file__).resolve().parent.parent / "datos_locales" / "logs"
CARPETA_POR_DEFECTO = _CARPETA_REAL

_NOMBRE_ARCHIVO = "backend.log"

# 5MB x 5 respaldos: acota el total en disco (~25MB) sin intervencion
# manual, cubre semanas de operacion normal de un negocio de este
# volumen. Por tamano, no por tiempo (TimedRotatingFileHandler) --
# el volumen de logs es impredecible (un ciclo de reintentos del
# sincronizador sin internet puede generar muchas lineas en poco tiempo).
TAMANO_MAXIMO_BYTES = 5 * 1024 * 1024
RESPALDOS_MAXIMOS = 5

_FORMATO = "%(asctime)s %(levelname)s %(name)s: %(message)s"

_configurado = False


def resolver_carpeta(carpeta=None) -> Path:
    ruta = Path(carpeta) if carpeta else CARPETA_POR_DEFECTO
    verificar_no_es_carpeta_real(ruta, _CARPETA_REAL, "logs")
    ruta.mkdir(parents=True, exist_ok=True)
    return ruta


def configurar_logging(carpeta=None, entorno: str | None = None) -> Path:
    """
    Configura el logger raiz con un RotatingFileHandler (+ StreamHandler a
    consola si `entorno == "desarrollo"`). Idempotente: si ya se llamo
    antes en este proceso, no duplica handlers -- solo devuelve la ruta
    del archivo.

    `entorno`: por defecto lee la variable de entorno ENTORNO (la misma
    que ya distingue produccion/desarrollo en main.py), para no agregar
    una variable nueva. INFO en produccion, DEBUG en desarrollo.
    """
    global _configurado

    carpeta_resuelta = resolver_carpeta(carpeta)
    archivo = carpeta_resuelta / _NOMBRE_ARCHIVO

    if _configurado:
        return archivo

    entorno = entorno if entorno is not None else os.environ.get("ENTORNO", "produccion")
    nivel = logging.DEBUG if entorno == "desarrollo" else logging.INFO

    formateador = logging.Formatter(_FORMATO)

    handler_archivo = logging.handlers.RotatingFileHandler(
        archivo,
        maxBytes=TAMANO_MAXIMO_BYTES,
        backupCount=RESPALDOS_MAXIMOS,
        encoding="utf-8",
    )
    handler_archivo.setFormatter(formateador)

    logger_raiz = logging.getLogger()
    logger_raiz.setLevel(nivel)
    logger_raiz.addHandler(handler_archivo)

    if entorno == "desarrollo":
        handler_consola = logging.StreamHandler()
        handler_consola.setFormatter(formateador)
        logger_raiz.addHandler(handler_consola)

    _configurado = True
    return archivo


def resetear_configuracion():
    """Solo para tests: permite que un test siguiente vuelva a configurar
    el logging (quita los handlers agregados por configurar_logging)."""
    global _configurado
    logger_raiz = logging.getLogger()
    for handler in list(logger_raiz.handlers):
        logger_raiz.removeHandler(handler)
        handler.close()
    _configurado = False
