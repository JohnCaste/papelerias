"""
Esquema y conexion del espejo local de solo lectura del catalogo (#13 --
paso previo a evaluar una migracion a MySQL). Ver
openspec/changes/espejo-local-catalogo-sqlite/design.md.

No es una fuente de verdad: es una proyeccion de lectura de `producto` y
`categoria` (mas el stock agregado de `movimiento_inventario`), refrescada
periodicamente desde BigQuery por `almacen_local/espejo_catalogo.py`. Se
puede borrar en cualquier momento sin perder nada -- el siguiente ciclo de
refresco la reconstruye sola.

    BigQuery --(refresco periodico, EspejoCatalogo)--> catalogo_espejo.sqlite3
                                                              |
                                                              v
                                          acceso_datos/repositorios/productos_local.py
                                                              |
                                                              v
                                                    catalogos/productos.py (lectura)
"""

import sqlite3
import unicodedata
from pathlib import Path

from almacen_local._seguridad_pruebas import verificar_no_es_carpeta_real

_ARCHIVO_REAL = (
    Path(__file__).resolve().parent.parent / "datos_locales" / "catalogo_espejo.sqlite3"
)
ARCHIVO_POR_DEFECTO = _ARCHIVO_REAL


def resolver_archivo(archivo=None) -> Path:
    ruta = Path(archivo) if archivo else ARCHIVO_POR_DEFECTO
    verificar_no_es_carpeta_real(ruta, _ARCHIVO_REAL, "espejo_catalogo")
    ruta.parent.mkdir(parents=True, exist_ok=True)
    return ruta


def normalizar_texto(texto) -> str:
    """
    Equivalente en Python de `LOWER(NORMALIZE(texto, NFD))`, que es como
    BigQuery compara nombres de forma insensible a mayusculas/acentos
    (ver acceso_datos/repositorios/productos.py::_condiciones_busqueda).
    SQLite no tiene una funcion NORMALIZE -- se resuelve aqui, guardando
    el resultado en la columna auxiliar `nombre_normalizado` y aplicando
    la misma normalizacion al termino de busqueda antes de comparar.
    """
    if not texto:
        return ""
    descompuesto = unicodedata.normalize("NFD", texto)
    sin_acentos = "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")
    return sin_acentos.lower()


def crear_esquema(conexion: sqlite3.Connection):
    conexion.executescript(
        """
        CREATE TABLE IF NOT EXISTS producto (
            id TEXT PRIMARY KEY,
            codigo_barras TEXT,
            codigo_interno TEXT,
            nombre TEXT NOT NULL,
            nombre_normalizado TEXT NOT NULL,
            categoria TEXT NOT NULL,
            marca TEXT,
            descripcion TEXT,
            imagen TEXT,
            precio REAL NOT NULL,
            costo REAL,
            stock_minimo REAL,
            cantidad REAL NOT NULL DEFAULT 0,
            actualizado_en TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_espejo_producto_nombre_normalizado
            ON producto(nombre_normalizado);
        CREATE INDEX IF NOT EXISTS idx_espejo_producto_codigo_barras
            ON producto(codigo_barras);
        CREATE INDEX IF NOT EXISTS idx_espejo_producto_categoria
            ON producto(categoria);
        CREATE INDEX IF NOT EXISTS idx_espejo_producto_marca
            ON producto(marca);
        CREATE INDEX IF NOT EXISTS idx_espejo_producto_precio
            ON producto(precio);

        CREATE TABLE IF NOT EXISTS categoria (
            nombre TEXT PRIMARY KEY,
            orden INTEGER NOT NULL
        );
        """
    )
    conexion.commit()


def conectar(archivo=None) -> sqlite3.Connection:
    """Abre (creando si hace falta) el archivo del espejo, con el esquema
    ya garantizado. `row_factory = sqlite3.Row` para poder pedir
    `dict(fila)` como ya se acostumbra en el resto del proyecto
    (ver acceso_datos/consultas.py)."""
    ruta = resolver_archivo(archivo)
    conexion = sqlite3.connect(str(ruta))
    conexion.row_factory = sqlite3.Row
    crear_esquema(conexion)
    return conexion
