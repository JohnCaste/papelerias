"""
Tests de utilidades/categorias.py -- la lista canonica de categorias de
venta.

El test que importa de verdad es el ultimo: la lista vive duplicada en
dos idiomas (Python y TypeScript) porque el frontend no puede importar
del backend. Duplicada pero no divergente: si alguien agrega una
categoria en un lado y se olvida del otro, el POS manda una clave que el
backend rechaza (o al reves, una categoria del backend que nadie puede
capturar). Esto lo detecta en CI en vez de en el mostrador.
"""

import pathlib
import re

from utilidades import categorias

RAIZ = pathlib.Path(__file__).resolve().parents[2]
ESPEJO_FRONTEND = RAIZ / "frontend" / "src" / "categorias.ts"


def test_claves_sin_duplicados_y_en_el_mismo_orden_que_la_tabla():
    assert len(categorias.CLAVES) == len(set(categorias.CLAVES))
    assert categorias.CLAVES == tuple(c for c, _ in categorias.CATEGORIAS)


def test_toda_clave_tiene_etiqueta():
    assert set(categorias.ETIQUETAS) == set(categorias.CLAVES)
    assert all(categorias.ETIQUETAS[c] for c in categorias.CLAVES)


def test_terramar_es_una_categoria_valida():
    assert "terramar" in categorias.CLAVES_VALIDAS


def test_dulces_conserva_su_clave_aunque_cambie_la_etiqueta():
    # La etiqueta paso de "Dulces" a "Dulces y Bebidas"; la clave NO se
    # toca, porque la historia en BigQuery ya esta escrita con 'dulces'.
    assert "dulces" in categorias.CLAVES_VALIDAS
    assert categorias.ETIQUETAS["dulces"] == "Dulces y Bebidas"


def test_claves_legadas_se_pliegan():
    assert categorias.canonica("productos") == "papeleria"
    assert categorias.canonica("hojas") == "copias"
    assert categorias.canonica("dulces") == "dulces"


def test_el_frontend_tiene_exactamente_las_mismas_claves_en_el_mismo_orden():
    fuente = ESPEJO_FRONTEND.read_text(encoding="utf-8")
    claves_ts = re.findall(r'clave:\s*"([^"]+)"', fuente)
    assert tuple(claves_ts) == categorias.CLAVES, (
        "frontend/src/categorias.ts se desincronizo de "
        "backend/utilidades/categorias.py -- tienen que ser la misma lista, "
        "en el mismo orden."
    )
