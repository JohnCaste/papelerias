"""
Guardia estructural: evita que el journal (#14) o los cierres (#50)
escriban o lean la carpeta REAL del negocio mientras corren pruebas.

`backend/tests/conftest.py` ya redirige `CARPETA_POR_DEFECTO` a una
carpeta temporal para cada test (via monkeypatch) -- esta guardia es la
red de seguridad de respaldo, independiente del orden/tiempo en que ese
monkeypatch se aplique: si por cualquier motivo el codigo intenta
resolver la ruta REAL mientras `LAPAPE_ENTORNO_PRUEBAS` esta activa,
truena de inmediato en vez de escribir en silencio sobre datos reales
del negocio.

`conftest.py` activa la variable de entorno una sola vez, al importarse
(arranque de la sesion de pytest completa), no por cada test.
"""

import os

VARIABLE_ENTORNO = "LAPAPE_ENTORNO_PRUEBAS"


def bajo_pruebas() -> bool:
    return os.environ.get(VARIABLE_ENTORNO) == "1"


def verificar_no_es_carpeta_real(ruta_resuelta, ruta_real, nombre: str):
    if bajo_pruebas() and ruta_resuelta == ruta_real:
        raise RuntimeError(
            f"Se intento usar la carpeta REAL de {nombre} ({ruta_real}) "
            f"mientras {VARIABLE_ENTORNO} esta activa. Pasa `carpeta=` "
            "explicito (normalmente tmp_path) en el test que disparo esto."
        )
