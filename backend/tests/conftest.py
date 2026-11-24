"""
Aisla TODO el almacen local (journal de ventas #14, cierres de dia #50,
espejo local del catalogo #13) de disco real durante los tests: por
defecto, cada test corre contra su propia carpeta temporal, nunca contra
backend/datos_locales/.

Dos capas, no una:

1. Por test (autouse): redirige `CARPETA_POR_DEFECTO`/`ARCHIVO_POR_DEFECTO`
   a una carpeta temporal -- lo normal, transparente, no requiere nada de
   cada test.

2. Por sesion completa: activa `LAPAPE_ENTORNO_PRUEBAS=1` desde que
   arranca pytest (no por cada test). `almacen_local/_seguridad_pruebas.py`
   usa esta variable para hacer que journal.py/cierres.py/
   espejo_catalogo_sqlite.py truenen de inmediato si, por lo que sea,
   alguna llamada llega a resolver la ruta REAL -- en vez de escribir ahi
   en silencio. Es la red de seguridad de respaldo, independiente de si
   la capa 1 se aplico a tiempo para una llamada en particular (por
   ejemplo, un hilo en segundo plano que siga vivo mas alla del teardown
   de su test).
"""

import os

import pytest

from almacen_local import cierres, compras, espejo_catalogo_sqlite, faltantes, journal
from almacen_local._seguridad_pruebas import VARIABLE_ENTORNO

os.environ[VARIABLE_ENTORNO] = "1"


@pytest.fixture(autouse=True)
def _aislar_almacen_local(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "CARPETA_POR_DEFECTO", tmp_path / "journal")
    monkeypatch.setattr(cierres, "CARPETA_POR_DEFECTO", tmp_path / "cierres")
    monkeypatch.setattr(compras, "CARPETA_POR_DEFECTO", tmp_path / "compras")
    monkeypatch.setattr(faltantes, "CARPETA_POR_DEFECTO", tmp_path / "faltantes")
    monkeypatch.setattr(
        espejo_catalogo_sqlite, "ARCHIVO_POR_DEFECTO", tmp_path / "catalogo_espejo.sqlite3"
    )
