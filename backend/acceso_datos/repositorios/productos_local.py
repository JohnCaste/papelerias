"""
Repositorio de lectura del catalogo contra el espejo local en SQLite
(#13). Equivalente de acceso_datos/repositorios/productos.py y
acceso_datos/repositorios/categorias.py, pero contra
almacen_local/espejo_catalogo_sqlite.py en vez de BigQuery -- mismos
parametros y misma forma de retorno, para que catalogos/productos.py
pueda usar cualquiera de los dos indistintamente (ver el fallback en
catalogos/productos.py).

No es la fuente de verdad: es una proyeccion de lectura. Las escrituras
(crear/actualizar/eliminar producto) siguen yendo a
acceso_datos/repositorios/productos.py (BigQuery); este modulo solo
lee, mas las funciones de mantenimiento que usa
almacen_local/espejo_catalogo.py para refrescar y mantener la copia al
dia (`reemplazar_todo`, `upsert_producto`, `marcar_inactivo`).
"""

from almacen_local import espejo_catalogo_sqlite as espejo

_LIMITE_MAXIMO = 200  # mismo tope que acceso_datos/repositorios/productos.py

# Columnas de la fila que SI forman parte del contrato hacia quien llama
# (calcan lo que devuelve BigQuery) -- 'nombre_normalizado' es un detalle
# interno de este espejo y nunca debe salir de este modulo.
_COLUMNAS_PUBLICAS = (
    "id",
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
    "cantidad",
)


def _fila_publica(fila: dict) -> dict:
    return {campo: fila.get(campo) for campo in _COLUMNAS_PUBLICAS}


def _condiciones_busqueda(termino, categoria, marca, precio_min, precio_max):
    """
    Arma la clausula WHERE -- mismo criterio que
    acceso_datos/repositorios/productos.py::_condiciones_busqueda (texto
    fijo escrito por el propio codigo, valores siempre parametrizados con
    `?`), pero contra las columnas del espejo local.
    """
    condiciones = ["1 = 1"]
    valores = []

    if termino:
        # 'nombre_normalizado' ya viene sin acentos y en minusculas (ver
        # espejo_catalogo_sqlite.normalizar_texto); se normaliza el
        # termino de la misma forma antes de comparar -- equivalente a
        # LOWER(NORMALIZE(nombre, NFD)) LIKE ... en BigQuery.
        condiciones.append("(nombre_normalizado LIKE ? OR codigo_barras = ?)")
        valores.append(f"%{espejo.normalizar_texto(termino)}%")
        valores.append(termino)
    if categoria:
        condiciones.append("categoria = ?")
        valores.append(categoria)
    if marca:
        condiciones.append("LOWER(marca) = LOWER(?)")
        valores.append(marca)
    if precio_min is not None:
        condiciones.append("precio >= ?")
        valores.append(float(precio_min))
    if precio_max is not None:
        condiciones.append("precio <= ?")
        valores.append(float(precio_max))

    return condiciones, valores


def buscar_con_total(
    termino: str = "",
    categoria: str = "",
    marca: str = "",
    precio_min=None,
    precio_max=None,
    limite: int = 20,
    offset: int = 0,
    archivo=None,
):
    """Equivalente local de
    acceso_datos/repositorios/productos.py::buscar_con_total -- misma
    firma, mismo retorno `(filas, total)`, una sola consulta (SQLite
    soporta funciones de ventana desde 3.25; el proyecto ya corre sobre
    una version mas nueva)."""
    condiciones, valores = _condiciones_busqueda(
        termino, categoria, marca, precio_min, precio_max
    )

    limite = max(1, min(int(limite), _LIMITE_MAXIMO))
    offset = max(0, int(offset))

    sql = f"""
        SELECT *, COUNT(*) OVER() AS total_coincidencias
        FROM producto
        WHERE {' AND '.join(condiciones)}
        ORDER BY nombre
        LIMIT ? OFFSET ?
    """

    conexion = espejo.conectar(archivo)
    try:
        filas = conexion.execute(sql, [*valores, limite, offset]).fetchall()
    finally:
        conexion.close()

    if not filas:
        return [], 0

    total = int(filas[0]["total_coincidencias"])
    return [_fila_publica(dict(fila)) for fila in filas], total


def listar(limite: int = 50, offset: int = 0, archivo=None):
    """Equivalente local de
    acceso_datos/repositorios/productos.py::listar (usado por el
    paginador simple, GET /api/catalogo/paginador)."""
    limite = max(1, min(int(limite), _LIMITE_MAXIMO))
    offset = max(0, int(offset))

    conexion = espejo.conectar(archivo)
    try:
        filas = conexion.execute(
            "SELECT * FROM producto ORDER BY nombre LIMIT ? OFFSET ?",
            (limite, offset),
        ).fetchall()
    finally:
        conexion.close()

    return [_fila_publica(dict(fila)) for fila in filas]


def marcas_distintas(archivo=None):
    """Equivalente local de
    acceso_datos/repositorios/productos.py::marcas_distintas."""
    conexion = espejo.conectar(archivo)
    try:
        filas = conexion.execute(
            """
            SELECT DISTINCT marca FROM producto
            WHERE marca IS NOT NULL AND marca != ''
            ORDER BY marca
            """
        ).fetchall()
    finally:
        conexion.close()

    return [fila["marca"] for fila in filas]


def listar_categorias(archivo=None):
    """Equivalente local de
    acceso_datos/repositorios/categorias.py::listar."""
    conexion = espejo.conectar(archivo)
    try:
        filas = conexion.execute(
            "SELECT nombre FROM categoria ORDER BY orden"
        ).fetchall()
    finally:
        conexion.close()

    return [fila["nombre"] for fila in filas]


# --------------------------------------------------------------------------
# Escritura del espejo -- SOLO la usan almacen_local/espejo_catalogo.py (el
# refresco periodico) y catalogos/productos.py (la actualizacion puntual
# tras crear/actualizar/eliminar). Nunca se llama desde una vista que
# escriba directamente: BigQuery sigue siendo la unica fuente de verdad.
# --------------------------------------------------------------------------


def _fila_para_sqlite(producto: dict) -> dict:
    """Traduce un producto tal como lo devuelve BigQuery (con 'activo',
    'creado_en', Decimal, etc.) a los valores que necesita la tabla local.
    `cantidad` es el stock agregado, que en BigQuery vive aparte
    (movimiento_inventario) -- quien llama lo pasa ya calculado."""
    nombre = producto["nombre"]
    return {
        "id": producto["id"],
        "codigo_barras": producto.get("codigo_barras"),
        "codigo_interno": producto.get("codigo_interno"),
        "nombre": nombre,
        "nombre_normalizado": espejo.normalizar_texto(nombre),
        "categoria": producto["categoria"],
        "marca": producto.get("marca"),
        "descripcion": producto.get("descripcion"),
        "imagen": producto.get("imagen"),
        "precio": float(producto["precio"]),
        "costo": float(producto["costo"]) if producto.get("costo") is not None else None,
        "stock_minimo": (
            float(producto["stock_minimo"]) if producto.get("stock_minimo") is not None else None
        ),
        "cantidad": float(producto.get("cantidad") or 0),
        "actualizado_en": str(producto.get("actualizado_en") or ""),
    }


def reemplazar_todo(productos: list, categorias: list, archivo=None):
    """
    Reemplaza el contenido completo del espejo dentro de una sola
    transaccion -- nunca deja un estado a medias visible a una lectura
    concurrente (ver design.md, Decision 2). Lo usa el ciclo de refresco
    periodico de EspejoCatalogo.

    `productos`: lista de dicts tal como los devuelve BigQuery, cada uno
    ya con 'cantidad' (stock agregado) resuelto por quien llama.
    `categorias`: lista de nombres en el orden en que deben mostrarse
    (mismo formato que categorias_repo.listar()).
    """
    filas = [_fila_para_sqlite(p) for p in productos]

    conexion = espejo.conectar(archivo)
    try:
        with conexion:
            conexion.execute("DELETE FROM producto")
            conexion.execute("DELETE FROM categoria")
            if filas:
                conexion.executemany(
                    """
                    INSERT INTO producto (
                        id, codigo_barras, codigo_interno, nombre,
                        nombre_normalizado, categoria, marca, descripcion,
                        imagen, precio, costo, stock_minimo, cantidad,
                        actualizado_en
                    ) VALUES (
                        :id, :codigo_barras, :codigo_interno, :nombre,
                        :nombre_normalizado, :categoria, :marca, :descripcion,
                        :imagen, :precio, :costo, :stock_minimo, :cantidad,
                        :actualizado_en
                    )
                    """,
                    filas,
                )
            if categorias:
                conexion.executemany(
                    "INSERT INTO categoria (nombre, orden) VALUES (?, ?)",
                    [(nombre, orden) for orden, nombre in enumerate(categorias)],
                )
    finally:
        conexion.close()


def upsert_producto(producto: dict, archivo=None):
    """
    Inserta o reemplaza un producto puntual -- lo usa
    catalogos/productos.py justo despues de confirmar un alta/edicion en
    BigQuery, para que el mismo usuario no vea el dato viejo antes del
    siguiente ciclo de refresco (ver design.md, Decision 3).
    """
    fila = _fila_para_sqlite(producto)
    conexion = espejo.conectar(archivo)
    try:
        with conexion:
            conexion.execute(
                """
                INSERT INTO producto (
                    id, codigo_barras, codigo_interno, nombre,
                    nombre_normalizado, categoria, marca, descripcion,
                    imagen, precio, costo, stock_minimo, cantidad,
                    actualizado_en
                ) VALUES (
                    :id, :codigo_barras, :codigo_interno, :nombre,
                    :nombre_normalizado, :categoria, :marca, :descripcion,
                    :imagen, :precio, :costo, :stock_minimo, :cantidad,
                    :actualizado_en
                )
                ON CONFLICT(id) DO UPDATE SET
                    codigo_barras = excluded.codigo_barras,
                    codigo_interno = excluded.codigo_interno,
                    nombre = excluded.nombre,
                    nombre_normalizado = excluded.nombre_normalizado,
                    categoria = excluded.categoria,
                    marca = excluded.marca,
                    descripcion = excluded.descripcion,
                    imagen = excluded.imagen,
                    precio = excluded.precio,
                    costo = excluded.costo,
                    stock_minimo = excluded.stock_minimo,
                    cantidad = excluded.cantidad,
                    actualizado_en = excluded.actualizado_en
                """,
                fila,
            )
    finally:
        conexion.close()


def marcar_inactivo(id_: str, archivo=None):
    """Borrado logico en BigQuery (activo=FALSE) -- en el espejo, que
    solo guarda productos activos, equivale a quitar la fila."""
    conexion = espejo.conectar(archivo)
    try:
        with conexion:
            conexion.execute("DELETE FROM producto WHERE id = ?", (id_,))
    finally:
        conexion.close()
