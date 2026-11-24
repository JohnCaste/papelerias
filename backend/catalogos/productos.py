"""
Endpoints de catalogo. Reescrito sobre acceso_datos/repositorios/productos.py
(#7, #11) -- ya no hay SQL armado con f-strings ni un bigquery.Client()
por funcion.

NOTA DE ESTADO: este modulo apunta al esquema nuevo (dataset `lapape`,
ver esquema/tablas.py). El dataset y las tablas ya existen en GCP
(crear_dataset.py corrido el 2026-09-01) y el catalogo viejo
(`nuevas_tablas.catalogos`) ya se migro a `lapape.producto` (#9, ver
esquema/migrar_catalogo.py). Estos endpoints ya operan sobre datos
reales.

Cambios de forma respecto al contrato anterior (ver #11 y el hilo del
issue para el detalle):
  - 'papeleria' desaparece: era un campo de texto libre sin significado
    documentado y no existe en el esquema nuevo. Si el negocio le daba
    un uso real, hay que decirlo para modelarlo como columna con nombre
    claro -- no se adivino su semantica.
  - 'cantidad' se mantiene como nombre de campo en las respuestas (para
    no romper el frontend actual), pero ya NO es una columna: se calcula
    sumando movimiento_inventario (#8, #31). Renombrarlo a 'stock' en
    frontend y backend a la vez es trabajo pendiente, no de este issue.
  - Editar 'cantidad' desde el formulario de administracion ya no
    sobreescribe un numero: inserta un movimiento de tipo 'ajuste' por
    la diferencia. Ver `_ajustar_cantidad_si_cambio`.
"""

import logging

from flask import current_app, jsonify, request

import acceso_datos.repositorios.categorias as categorias_repo
import acceso_datos.repositorios.movimientos_inventario as movimientos_repo
import acceso_datos.repositorios.productos as productos_repo
import acceso_datos.repositorios.productos_local as productos_local
import catalogos.imagenes as imagenes

logger = logging.getLogger(__name__)

_LIMITE_TRAER_TODO = 500  # tope de seguridad; el paginador es el camino real.

# Columnas NUMERIC de `producto`. BigQuery las devuelve como decimal.Decimal
# y Flask serializa Decimal como STRING (`"294"`), no como numero -- el
# frontend espera number (hace `precio * n`, `cantidad + 1`). Se convierten
# aqui. El catalogo legado tenia `precio` como FLOAT y no daba este problema.
_CAMPOS_NUMERICOS = ("precio", "costo", "stock_minimo")


def _a_numero(valor):
    """Decimal/str -> int si es entero, float si tiene fraccion; None se respeta."""
    if valor is None:
        return None
    numero = float(valor)
    return int(numero) if numero.is_integer() else numero


def _con_stock(productos: list) -> list:
    """Adjunta 'cantidad' (stock calculado) a cada producto consultando
    BigQuery, en una sola consulta -- ver
    acceso_datos/repositorios/movimientos_inventario.stock_de_varios. SOLO
    para el camino de BigQuery directo: el espejo local (#13) ya trae
    'cantidad' resuelta de antemano por el refresco periodico, usar esto
    ahi haria una llamada a BigQuery de mas por cada busqueda -- justo lo
    que el espejo existe para evitar (ver _normalizar_numeros)."""
    ids = [p["id"] for p in productos]
    stock_por_id = movimientos_repo.stock_de_varios(ids)
    salida = []
    for producto in productos:
        producto = dict(producto)
        producto["cantidad"] = stock_por_id.get(producto["id"], 0)
        salida.append(producto)
    return _normalizar_numeros(salida)


def _normalizar_numeros(productos: list) -> list:
    """Convierte 'precio'/'costo'/'stock_minimo'/'cantidad' a number (ver
    _CAMPOS_NUMERICOS y _a_numero). Comun a los dos caminos de lectura:
    BigQuery devuelve Decimal, el espejo local (SQLite) ya devuelve
    float/int nativos -- aplicarlo ahi tambien es inofensivo (idempotente)
    y deja el formato de salida identico sin importar cual respondio."""
    salida = []
    for producto in productos:
        producto = dict(producto)
        for campo in (*_CAMPOS_NUMERICOS, "cantidad"):
            if campo in producto:
                producto[campo] = _a_numero(producto[campo])
        salida.append(producto)
    return salida


def _espejo_disponible() -> bool:
    """
    True si hay una instancia de EspejoCatalogo asociada a la app actual
    (`current_app.espejo_catalogo`, ver main.py::crear_app) Y ya tuvo al
    menos un refresco exitoso. `getattr` con default: una app de test que
    no pasa por crear_app() (varios tests de este modulo construyen un
    Flask() a pelo) simplemente no tiene el atributo -- se trata igual
    que "espejo no disponible todavia", cae a BigQuery sin romper nada.
    """
    espejo = getattr(current_app, "espejo_catalogo", None)
    return bool(espejo) and espejo.disponible()


def _con_fallback(operacion_local, operacion_bigquery):
    """
    Intenta `operacion_local` (callable sin argumentos) si el espejo esta
    disponible; si no lo esta, o si lanza cualquier excepcion inesperada
    (archivo corrupto, lo que sea), cae a `operacion_bigquery` -- el
    catalogo nunca debe romperse por culpa del espejo (ver design.md,
    Decision 4). Solo se registra con logger.warning cuando el fallback
    ocurre por una excepcion real; "todavia no hay primer refresco" es
    esperado en cada arranque y no amerita ruido en el log.
    """
    if _espejo_disponible():
        try:
            return operacion_local()
        except Exception as excepcion:  # noqa: BLE001 -- cualquier fallo del espejo cae a BigQuery
            logger.warning(
                "Espejo de catalogo: fallo una lectura local, usando BigQuery de respaldo: %s",
                excepcion,
            )
    return operacion_bigquery()


def _entero_seguro(valor, defecto, minimo=0):
    """Convierte un query param a int sin reventar con texto invalido."""
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        return defecto
    return max(minimo, numero)


def _limite_seguro(valor, defecto=12):
    """Query param -> limit valido (>= 1); vacio, texto o <= 0 -> defecto."""
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        return defecto
    return numero if numero >= 1 else defecto


def _numero_seguro(valor):
    """Query param -> float, o None si viene vacio o con texto invalido."""
    if valor in (None, ""):
        return None
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def _validar_precio(datos: dict):
    """Devuelve un mensaje de error si 'precio' viene y es negativo; si no, None."""
    precio = datos.get("precio")
    if precio in (None, ""):
        return None
    try:
        if float(precio) < 0:
            return "El precio no puede ser negativo"
    except (TypeError, ValueError):
        return "El precio no es un numero valido"
    return None


def _normalizar_codigo_barras(datos: dict):
    """
    Devuelve el codigo de barras recortado, o None si no viene o queda vacio.
    Se usa para no guardar cadenas vacias (romperia la unicidad: '' == '') y
    para comparar contra el catalogo antes de crear/editar.
    """
    valor = datos.get("codigo_barras")
    if not isinstance(valor, str):
        return None
    valor = valor.strip()
    return valor or None


def _codigo_barras_en_conflicto(codigo: str, id_propio: str | None = None):
    """
    True si `codigo` ya lo usa OTRO producto activo. `id_propio` exime al
    producto que se esta editando (conservar su mismo codigo es valido).
    El esquema declara `codigo_barras` unico cuando no es nulo y delega la
    validacion al codigo (ver esquema/tablas.py).
    """
    existente = productos_repo.obtener_por_codigo_barras(codigo)
    return existente is not None and existente.get("id") != id_propio


# -----------------------------------GET -- catalogo completo (paginado
# internamente por seguridad, ver _LIMITE_TRAER_TODO)
def traer_productos():
    productos = productos_repo.listar(limite=_LIMITE_TRAER_TODO, offset=0)
    return jsonify(_con_stock(productos))


# .................................GET -- limit/offset (paginador real)
def limite_productos():
    limite = _entero_seguro(request.args.get("limit"), defecto=12, minimo=1)
    offset = _entero_seguro(request.args.get("offset"), defecto=0, minimo=0)

    def _local():
        return _normalizar_numeros(productos_local.listar(limite=limite, offset=offset))

    def _bigquery():
        return _con_stock(productos_repo.listar(limite=limite, offset=offset))

    return jsonify(_con_fallback(_local, _bigquery))


# .................................GET -- busqueda server-side sobre todo el
# catalogo (termino global, categoria, marca, rango de precio) + total.
# Lee del espejo local (#13) cuando esta disponible; BigQuery directo de
# respaldo -- ver _con_fallback.
def buscar_productos():
    args = request.args
    termino = (args.get("q") or "").strip()
    categoria = (args.get("categoria") or "").strip()
    marca = (args.get("marca") or "").strip()
    precio_min = _numero_seguro(args.get("precio_min"))
    precio_max = _numero_seguro(args.get("precio_max"))
    limite = _limite_seguro(args.get("limit"), defecto=12)
    offset = _entero_seguro(args.get("offset"), defecto=0, minimo=0)

    def _local():
        filas, total = productos_local.buscar_con_total(
            termino=termino,
            categoria=categoria,
            marca=marca,
            precio_min=precio_min,
            precio_max=precio_max,
            limite=limite,
            offset=offset,
        )
        return {"items": _normalizar_numeros(filas), "total": total}

    def _bigquery():
        filas, total = productos_repo.buscar_con_total(
            termino=termino,
            categoria=categoria,
            marca=marca,
            precio_min=precio_min,
            precio_max=precio_max,
            limite=limite,
            offset=offset,
        )
        return {"items": _con_stock(filas), "total": total}

    return jsonify(_con_fallback(_local, _bigquery))


# .................................GET -- categorias canonicas (tabla fija;
# pobla el selector de los formularios y el filtro del catalogo)
def listar_categorias():
    return jsonify(_con_fallback(productos_local.listar_categorias, categorias_repo.listar))


# .................................GET -- marcas distintas (pobla filtro por marca)
def listar_marcas():
    return jsonify(_con_fallback(productos_local.marcas_distintas, productos_repo.marcas_distintas))


# ...............................POST -- agregar producto
def agregar_productos():
    datos = request.get_json(silent=True) or {}

    campos_requeridos = ("nombre", "categoria", "precio")
    # 'precio' = 0 es un valor valido: se comprueba presencia, no verdad.
    faltantes = [c for c in campos_requeridos if datos.get(c) in (None, "")]
    if faltantes:
        return jsonify(error=f"Faltan campos requeridos: {', '.join(faltantes)}"), 400

    error_precio = _validar_precio(datos)
    if error_precio:
        return jsonify(error=error_precio), 400

    codigo_barras = _normalizar_codigo_barras(datos)
    datos["codigo_barras"] = codigo_barras  # "" -> None; no guardar cadena vacia
    if codigo_barras and _codigo_barras_en_conflicto(codigo_barras):
        return jsonify(error="El codigo de barras ya esta en uso"), 400

    try:
        producto = productos_repo.crear(datos)
    except (TypeError, ValueError) as error:
        return jsonify(error=str(error)), 400

    cantidad_inicial = datos.get("cantidad")
    if cantidad_inicial not in (None, "", 0, "0"):
        movimientos_repo.insertar(
            {
                "producto_id": producto["id"],
                "tipo": "inventario_inicial",
                "cantidad": float(cantidad_inicial),
                "usuario_id": datos.get("usuario_id", "sistema"),
            }
        )

    producto_con_stock = _con_stock([producto])[0]
    _actualizar_espejo_tras_escribir(producto_con_stock)
    return jsonify(producto_con_stock), 201


# .................................POST -- subir imagen de producto
# (camara o archivo). Convierte a .webp optimizado y la sube a GCS;
# devuelve la URL publica para guardarla luego en producto.imagen.
def subir_imagen():
    archivo = request.files.get("archivo")
    if archivo is None or not archivo.filename:
        return jsonify(error="Falta el archivo de imagen ('archivo')"), 400

    datos = archivo.read()
    if len(datos) > imagenes.MAX_SUBIDA_MB * 1024 * 1024:
        return jsonify(
            error=f"La imagen supera el maximo de {imagenes.MAX_SUBIDA_MB} MB"
        ), 400

    try:
        webp = imagenes.procesar_a_webp(datos)
    except ValueError as error:
        return jsonify(error=str(error)), 400

    try:
        url = imagenes.subir_a_gcs(webp)
    except imagenes.BucketNoConfigurado as error:
        return jsonify(error=str(error)), 500

    return jsonify({"url": url})


# .................................DELETE -- eliminar producto (borrado
# logico, ver acceso_datos/repositorios/productos.py)
def eliminar_productos():
    id_ = request.args.get("id")
    if not id_:
        return jsonify(error="Falta 'id'"), 400

    productos_repo.eliminar(id_)
    _quitar_del_espejo_tras_escribir(id_)
    return jsonify(ok=True)


# ................................... PATCH -- actualizar producto
def actualizar_productos():
    datos = request.get_json(silent=True) or {}
    id_ = datos.get("id")
    if not id_:
        return jsonify(error="Falta 'id'"), 400

    error_precio = _validar_precio(datos)
    if error_precio:
        return jsonify(error=error_precio), 400

    if "codigo_barras" in datos:
        codigo_barras = _normalizar_codigo_barras(datos)
        datos["codigo_barras"] = codigo_barras  # "" -> None
        if codigo_barras and _codigo_barras_en_conflicto(codigo_barras, id_):
            return jsonify(error="El codigo de barras ya esta en uso"), 400

    productos_repo.actualizar(id_, datos)
    _ajustar_cantidad_si_cambio(id_, datos)

    producto = productos_repo.obtener_por_id(id_)
    if producto is None:
        return jsonify(error="Producto no encontrado"), 404

    producto_con_stock = _con_stock([producto])[0]
    _actualizar_espejo_tras_escribir(producto_con_stock)
    return jsonify(producto_con_stock)


def _actualizar_espejo_tras_escribir(producto: dict):
    """
    Refleja de inmediato en el espejo local (#13) un alta/edicion que ya
    se confirmo en BigQuery, para que el mismo usuario no vea el dato
    viejo antes del siguiente ciclo de refresco periodico (ver
    design.md, Decision 3). Un fallo aqui NUNCA cambia la respuesta
    HTTP: BigQuery (la fuente de verdad) ya confirmo el cambio, y el
    siguiente refresco corrige el espejo de todos modos.
    """
    try:
        productos_local.upsert_producto(producto)
    except Exception as excepcion:  # noqa: BLE001 -- nunca debe tumbar la escritura real
        logger.warning(
            "Espejo de catalogo: no se pudo reflejar el producto %s de inmediato: %s",
            producto.get("id"),
            excepcion,
        )


def _quitar_del_espejo_tras_escribir(producto_id: str):
    """Misma idea que _actualizar_espejo_tras_escribir, para la baja
    logica (eliminar_productos)."""
    try:
        productos_local.marcar_inactivo(producto_id)
    except Exception as excepcion:  # noqa: BLE001
        logger.warning(
            "Espejo de catalogo: no se pudo quitar el producto %s de inmediato: %s",
            producto_id,
            excepcion,
        )


def _ajustar_cantidad_si_cambio(producto_id: str, datos: dict):
    """
    El formulario de administracion sigue mandando 'cantidad' como un
    numero absoluto (asi lo espera el frontend actual). Como el stock ya
    no es una columna, la diferencia contra el stock calculado se
    registra como un movimiento de tipo 'ajuste' -- nunca se sobreescribe
    nada (ver #8: append-only).
    """
    if "cantidad" not in datos or datos["cantidad"] in (None, ""):
        return

    nueva_cantidad = float(datos["cantidad"])
    actual = float(movimientos_repo.stock_actual(producto_id))
    diferencia = nueva_cantidad - actual
    if diferencia == 0:
        return

    movimientos_repo.insertar(
        {
            "producto_id": producto_id,
            "tipo": "ajuste",
            "cantidad": diferencia,
            "usuario_id": datos.get("usuario_id", "sistema"),
        }
    )
