"""
Repositorio de producto. Ver esquema en esquema/tablas.py.

Nota de diseno: 'eliminar' es un borrado logico (activo = FALSE), no un
DELETE fisico. Un DELETE dejaria huerfanas las referencias `producto_id`
en `venta.lineas` y en `movimiento_inventario` de ventas ya hechas -- se
perderia la trazabilidad de que se vendio ese producto. Ademas, DELETE es
DML y esta tabla ya usa UPDATE para editar (ver esquema/README.md).
"""

import datetime
import uuid

from acceso_datos.consultas import ejecutar_query, ejecutar_uno
from acceso_datos.escrituras import insertar_filas
from esquema.tablas import DATASET

TABLA = f"{DATASET}.producto"

_LIMITE_MAXIMO = 200


def _ahora():
    return datetime.datetime.now(datetime.timezone.utc)


def listar(limite: int = 50, offset: int = 0):
    limite = max(1, min(int(limite), _LIMITE_MAXIMO))
    offset = max(0, int(offset))
    sql = f"""
        SELECT * FROM `{TABLA}`
        WHERE activo = TRUE
        ORDER BY nombre
        LIMIT @limite OFFSET @offset
    """
    return ejecutar_query(sql, {"limite": limite, "offset": offset})


def listar_todos_activos():
    """
    TODOS los productos activos, sin paginar -- a diferencia de `listar`,
    que esta acotado a `_LIMITE_MAXIMO` porque alimenta un endpoint HTTP
    directo. Lo usa el refresco periodico del espejo local del catalogo
    (#13, ver almacen_local/espejo_catalogo.py), que necesita el
    catalogo completo en cada ciclo para poder reemplazarlo entero. A la
    escala de este negocio (cientos de productos, no millones) una
    lectura completa sigue siendo barata; si el catalogo creciera ordenes
    de magnitud, aqui es donde convendria paginar el refresco.
    """
    sql = f"""
        SELECT * FROM `{TABLA}`
        WHERE activo = TRUE
        ORDER BY nombre
    """
    return ejecutar_query(sql)


def contar(termino="", categoria="", marca="", precio_min=None, precio_max=None):
    condiciones, valores, tipos = _condiciones_busqueda(
        termino, categoria, marca, precio_min, precio_max
    )
    sql = f"SELECT COUNT(*) AS total FROM `{TABLA}` WHERE {' AND '.join(condiciones)}"
    fila = ejecutar_uno(sql, valores, tipos)
    return fila["total"] if fila else 0


def buscar(
    termino: str = "",
    categoria: str = "",
    marca: str = "",
    precio_min=None,
    precio_max=None,
    limite: int = 20,
    offset: int = 0,
):
    """Busqueda server-side por nombre, categoria, marca y rango de precio (#28)."""
    condiciones, valores, tipos = _condiciones_busqueda(
        termino, categoria, marca, precio_min, precio_max
    )

    limite = max(1, min(int(limite), _LIMITE_MAXIMO))
    offset = max(0, int(offset))
    valores["limite"] = limite
    valores["offset"] = offset

    sql = f"""
        SELECT * FROM `{TABLA}`
        WHERE {' AND '.join(condiciones)}
        ORDER BY nombre
        LIMIT @limite OFFSET @offset
    """
    return ejecutar_query(sql, valores, tipos)


def buscar_con_total(
    termino: str = "",
    categoria: str = "",
    marca: str = "",
    precio_min=None,
    precio_max=None,
    limite: int = 20,
    offset: int = 0,
):
    """
    Igual que `buscar`, pero en una sola consulta a BigQuery en vez de dos
    (antes `buscar_productos()` en catalogos/productos.py llamaba a
    `buscar()` y luego a `contar()` por separado). `COUNT(*) OVER()` calcula
    el total de coincidencias en todo el catalogo sin una segunda pasada --
    BigQuery lo repite en cada fila de la pagina, pero como `limite` esta
    acotado a `_LIMITE_MAXIMO` el costo es insignificante.

    Devuelve (filas, total): `filas` sin la columna auxiliar
    `total_coincidencias`, y `total` como int (0 si no hay resultados, ya
    que ahi no hay fila de la que leerlo).
    """
    condiciones, valores, tipos = _condiciones_busqueda(
        termino, categoria, marca, precio_min, precio_max
    )

    limite = max(1, min(int(limite), _LIMITE_MAXIMO))
    offset = max(0, int(offset))
    valores["limite"] = limite
    valores["offset"] = offset

    sql = f"""
        SELECT *, COUNT(*) OVER() AS total_coincidencias FROM `{TABLA}`
        WHERE {' AND '.join(condiciones)}
        ORDER BY nombre
        LIMIT @limite OFFSET @offset
    """
    filas = ejecutar_query(sql, valores, tipos)
    if not filas:
        return [], 0

    total = int(filas[0]["total_coincidencias"])
    for fila in filas:
        del fila["total_coincidencias"]
    return filas, total


def _condiciones_busqueda(termino, categoria, marca, precio_min, precio_max):
    """
    Arma la clausula WHERE. Las condiciones que entran son texto FIJO
    escrito por el propio codigo (nunca contenido del usuario); los
    valores variables siempre van como parametro.
    """
    condiciones = ["activo = TRUE"]
    valores = {}
    tipos = {}

    if termino:
        # Coincide por NOMBRE (insensible a mayusculas y acentos) O por
        # CODIGO DE BARRAS exacto -- asi una lectura de la pistola (que
        # llega como texto en `q`) encuentra el producto aunque su nombre
        # no contenga el numero. El match por codigo es exacto, no por
        # subcadena: teclear "750" no debe traer decenas de productos por
        # prefijo de codigo.
        #
        # NORMALIZE(x, NFD) por si solo NO quita los acentos: descompone
        # "a" con acento en "a" + marca combinante (U+0301), pero la marca
        # se queda ahi. Buscar "lapiz" (sin acento) nunca encontraba
        # "Lapiz" (con acento) porque esa marca combinante seguia rota la
        # coincidencia de subcadena -- solo funcionaba si el termino
        # llevaba el mismo acento que el nombre guardado. REGEXP_REPLACE
        # quita esas marcas (categoria Unicode "M") DESPUES de normalizar,
        # en los dos lados de la comparacion, para que el acento deje de
        # importar de verdad.
        condiciones.append(
            r"(REGEXP_REPLACE(LOWER(NORMALIZE(nombre, NFD)), r'\pM', '')"
            r" LIKE REGEXP_REPLACE(LOWER(NORMALIZE(@termino, NFD)), r'\pM', '')"
            " OR codigo_barras = @codigo_barras_exacto)"
        )
        valores["termino"] = f"%{termino}%"
        valores["codigo_barras_exacto"] = termino
    if categoria:
        condiciones.append("categoria = @categoria")
        valores["categoria"] = categoria
    if marca:
        condiciones.append("LOWER(marca) = LOWER(@marca)")
        valores["marca"] = marca
    if precio_min is not None:
        condiciones.append("precio >= @precio_min")
        valores["precio_min"] = float(precio_min)
        tipos["precio_min"] = "NUMERIC"
    if precio_max is not None:
        condiciones.append("precio <= @precio_max")
        valores["precio_max"] = float(precio_max)
        tipos["precio_max"] = "NUMERIC"

    return condiciones, valores, tipos


def marcas_distintas():
    """Marcas unicas de productos activos, ordenadas -- pobla el filtro
    por marca del catalogo."""
    sql = f"""
        SELECT DISTINCT marca FROM `{TABLA}`
        WHERE activo = TRUE AND marca IS NOT NULL AND marca != ''
        ORDER BY marca
    """
    return [fila["marca"] for fila in ejecutar_query(sql)]


def obtener_por_id(id_: str):
    sql = f"SELECT * FROM `{TABLA}` WHERE id = @id AND activo = TRUE LIMIT 1"
    return ejecutar_uno(sql, {"id": id_})


def obtener_por_codigo_barras(codigo: str):
    """Consulta para la pistola de codigo de barras (#38, #39)."""
    sql = f"SELECT * FROM `{TABLA}` WHERE codigo_barras = @codigo AND activo = TRUE LIMIT 1"
    return ejecutar_uno(sql, {"codigo": codigo})


def _fila_nueva(datos: dict, ahora):
    return {
        "id": str(uuid.uuid4()),
        "codigo_barras": datos.get("codigo_barras"),
        "codigo_interno": datos.get("codigo_interno"),
        "nombre": datos["nombre"],
        "categoria": datos["categoria"],
        "marca": datos.get("marca"),
        "descripcion": datos.get("descripcion"),
        "imagen": datos.get("imagen"),
        "precio": float(datos["precio"]),
        "costo": datos.get("costo"),
        "stock_minimo": datos.get("stock_minimo"),
        "activo": True,
        "creado_en": ahora,
        "actualizado_en": ahora,
    }


def crear(datos: dict):
    fila = _fila_nueva(datos, _ahora())
    insertar_filas(TABLA, [fila])
    return fila


TAMANO_BLOQUE = 500  # bajo el limite recomendado de insertAll por peticion


class ErrorInsercionParcial(Exception):
    """Fallo un bloque de `crear_varios`. `creados` son las filas que SI se
    insertaron antes del fallo (streaming no es transaccional, no se
    revierten); `causa` es la excepcion original."""

    def __init__(self, creados: list, causa: Exception):
        super().__init__(str(causa))
        self.creados = creados
        self.causa = causa


def crear_varios(lista: list, tamano_bloque: int = TAMANO_BLOQUE):
    """
    Alta en lote (importacion desde Excel). Arma cada fila igual que
    `crear` -- el 'id' se genera una sola vez, asi que row_ids deduplica un
    reintento inmediato -- e inserta por streaming en bloques. Si falla un
    bloque se detiene y lanza ErrorInsercionParcial con lo ya creado.
    """
    ahora = _ahora()
    filas = [_fila_nueva(datos, ahora) for datos in lista]
    creados = []
    for inicio in range(0, len(filas), tamano_bloque):
        bloque = filas[inicio : inicio + tamano_bloque]
        try:
            insertar_filas(TABLA, bloque)
        except Exception as error:  # noqa: BLE001 -- se reporta hasta donde se llego
            raise ErrorInsercionParcial(creados, error) from error
        creados.extend(bloque)
    return creados


def codigos_barras_existentes(codigos) -> set:
    """Cuales de `codigos` ya usa un producto activo, en UNA consulta.
    Siempre contra BigQuery (fuente de verdad), no el espejo local, que
    puede ir atrasado un ciclo."""
    codigos = sorted({c for c in codigos if c})
    if not codigos:
        return set()
    sql = f"""
        SELECT DISTINCT codigo_barras FROM `{TABLA}`
        WHERE activo = TRUE AND codigo_barras IN UNNEST(@codigos)
    """
    filas = ejecutar_query(sql, {"codigos": codigos}, {"codigos": "STRING"})
    return {fila["codigo_barras"] for fila in filas}


def nombres_activos():
    """Nombres de todos los productos activos (advertencia de posible
    duplicado por nombre en la importacion)."""
    sql = f"SELECT nombre FROM `{TABLA}` WHERE activo = TRUE"
    return [fila["nombre"] for fila in ejecutar_query(sql)]


_CAMPOS_EDITABLES = (
    "codigo_barras",
    "codigo_interno",
    "nombre",
    "categoria",
    "marca",
    "descripcion",
    "imagen",
    "precio",
    "costo",
    "stock_minimo",
)


def actualizar(id_: str, datos: dict):
    """UPDATE parametrizado. Baja frecuencia: cabe dentro de la cuota de DML."""
    cambios = {campo: datos[campo] for campo in _CAMPOS_EDITABLES if campo in datos}
    if not cambios:
        return

    asignaciones = ", ".join(f"{campo} = @{campo}" for campo in cambios)
    valores = dict(cambios)
    valores["id"] = id_
    valores["actualizado_en"] = _ahora()

    sql = f"""
        UPDATE `{TABLA}`
        SET {asignaciones}, actualizado_en = @actualizado_en
        WHERE id = @id
    """
    ejecutar_query(sql, valores)


def eliminar(id_: str):
    """Borrado logico -- ver nota de diseno al inicio del archivo."""
    sql = f"UPDATE `{TABLA}` SET activo = FALSE, actualizado_en = @ahora WHERE id = @id"
    ejecutar_query(sql, {"id": id_, "ahora": _ahora()})
