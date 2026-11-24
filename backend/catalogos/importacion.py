"""
Importacion de productos al catalogo desde Excel (.xlsx) o CSV -- ver
openspec/changes/importacion-catalogo-excel.

Flujo en dos pasos, sin estado en el servidor (design.md, Decision 1):
  1. previsualizar: lee y valida el archivo, NO escribe nada; devuelve las
     filas validas ya normalizadas y las filas con error.
  2. confirmar: el frontend reenvia las filas validas; se REVALIDAN todas
     (el payload pudo cambiar, o alguien dio de alta un codigo entre ambos
     pasos) y se crean en lote solo las que siguen siendo validas.

Escribe en el dataset de la sucursal (DATASET en esquema/tablas.py, via los
repositorios). Las categorias son las de PRODUCTO (tabla `categoria`), no
las de venta de utilidades/categorias.py.

Solo la duena (rol `dueno`, ver autentificacion/permisos.py) llega aqui.
"""

import csv
import io
import logging

from flask import jsonify, request, send_file
from flask_jwt_extended import get_jwt_identity

import acceso_datos.repositorios.categorias as categorias_repo
import acceso_datos.repositorios.movimientos_inventario as movimientos_repo
import acceso_datos.repositorios.productos as productos_repo
import acceso_datos.repositorios.productos_local as productos_local
import catalogos.validacion_producto as validacion
from catalogos import productos as vistas_catalogo

logger = logging.getLogger(__name__)

MAX_BYTES = 5 * 1024 * 1024
MAX_FILAS = 2000
TAMANO_BLOQUE_MOVIMIENTOS = 500

# Orden de la plantilla (spec: "Plantilla de importacion descargable").
COLUMNAS = (
    "nombre",
    "categoria",
    "precio",
    "codigo_barras",
    "marca",
    "costo",
    "cantidad",
    "stock_minimo",
    "codigo_interno",
    "descripcion",
)
COLUMNAS_CODIGO = ("codigo_barras", "codigo_interno")

# Alias de encabezado (ya normalizados: minusculas, sin acentos, '_' -> ' ').
# Ajustar cuando se tenga el Excel real del negocio (tasks.md 1.2).
_ALIAS = {
    "nombre": ("nombre", "producto", "nombre del producto", "articulo"),
    "categoria": ("categoria",),
    "precio": ("precio", "precio de venta", "precio venta", "precio publico"),
    "codigo_barras": ("codigo barras", "codigo de barras", "codigo", "ean", "upc"),
    "marca": ("marca",),
    "costo": ("costo", "precio de compra", "costo unitario"),
    "cantidad": ("cantidad", "existencia", "existencias", "stock", "inventario", "cantidad inicial"),
    "stock_minimo": ("stock minimo", "minimo", "existencia minima"),
    "codigo_interno": ("codigo interno", "sku", "clave"),
    "descripcion": ("descripcion",),
}
_CAMPO_POR_ALIAS = {alias: campo for campo, alias_ in _ALIAS.items() for alias in alias_}

# Columna que agrega el CSV de "filas con error": al resubirlo no se avisa.
_COLUMNAS_SILENCIOSAS = {"error", "fila"}


class ErrorArchivo(ValueError):
    """Archivo rechazado entero (400): tipo, tamano, encabezados, filas."""


# ------------------------------------------------------------ lectura


def _clave_encabezado(texto) -> str:
    return validacion.normalizar_clave(str(texto or "").replace("_", " "))


def _mapear_encabezados(encabezados):
    """[campo | None por columna], advertencias. Error si faltan requeridos."""
    campos, ignoradas, advertencias, vistos = [], [], [], set()
    for encabezado in encabezados:
        clave = _clave_encabezado(encabezado)
        campo = _CAMPO_POR_ALIAS.get(clave)
        if campo and campo in vistos:
            advertencias.append(f'La columna "{encabezado}" se repite; se uso la primera')
            campo = None
        elif campo:
            vistos.add(campo)
        elif clave and clave not in _COLUMNAS_SILENCIOSAS:
            ignoradas.append(str(encabezado).strip())
        campos.append(campo)

    faltan = [c for c in validacion.CAMPOS_REQUERIDOS if c not in vistos]
    if faltan:
        raise ErrorArchivo(f"Faltan columnas requeridas: {', '.join(faltan)}")
    if ignoradas:
        advertencias.append(f"Se ignoraron las columnas: {', '.join(ignoradas)}")
    return campos, advertencias


def _fila_vacia(valores) -> bool:
    return all(v is None or (isinstance(v, str) and not v.strip()) for v in valores)


def _armar_filas(renglones, campos):
    """renglones: [(numero_de_fila_del_archivo, valores)] sin el encabezado."""
    filas = []
    for numero, valores in renglones:
        if _fila_vacia(valores):
            continue
        datos = {}
        for campo, valor in zip(campos, valores):
            if campo is None:
                continue
            if campo in COLUMNAS_CODIGO:
                valor = validacion.normalizar_codigo(valor)
            elif isinstance(valor, str):
                valor = valor.strip()
            datos[campo] = valor
        filas.append({"fila": numero, "datos": datos})
        if len(filas) > MAX_FILAS:
            raise ErrorArchivo(f"El archivo supera el maximo de {MAX_FILAS} filas de productos")
    return filas


def _leer_xlsx(contenido: bytes):
    from openpyxl import load_workbook

    try:
        libro = load_workbook(io.BytesIO(contenido), read_only=True, data_only=True)
    except Exception as error:  # noqa: BLE001 -- zip corrupto, no es xlsx, etc.
        raise ErrorArchivo("No se pudo leer el archivo de Excel") from error
    try:
        hoja = libro.worksheets[0]
        renglones = []
        encabezados = None
        for numero, valores in enumerate(hoja.iter_rows(values_only=True), start=1):
            if encabezados is None:
                if _fila_vacia(valores):
                    continue
                encabezados = list(valores)
                continue
            renglones.append((numero, list(valores)))
            if len(renglones) > MAX_FILAS * 3:  # tope duro ante hojas con basura
                break
    finally:
        libro.close()
    return encabezados, renglones


def _decodificar_csv(contenido: bytes) -> str:
    try:
        return contenido.decode("utf-8-sig")
    except UnicodeDecodeError:
        # "CSV" por defecto de Excel en Windows en espanol.
        return contenido.decode("cp1252", errors="replace")


def _leer_csv(contenido: bytes):
    texto = _decodificar_csv(contenido)
    primera_linea = texto.split("\n", 1)[0]
    try:
        separador = csv.Sniffer().sniff(primera_linea, delimiters=",;\t").delimiter
    except csv.Error:
        separador = ","
    lector = csv.reader(io.StringIO(texto), delimiter=separador)
    encabezados = None
    renglones = []
    for numero, valores in enumerate(lector, start=1):
        if encabezados is None:
            if _fila_vacia(valores):
                continue
            encabezados = valores
            continue
        renglones.append((numero, valores))
    return encabezados, renglones


def leer_archivo(nombre_archivo: str, contenido: bytes):
    """-> (filas, advertencias). filas = [{"fila": n, "datos": {...}}]."""
    nombre = (nombre_archivo or "").lower()
    if len(contenido) > MAX_BYTES:
        raise ErrorArchivo(f"El archivo supera el maximo de {MAX_BYTES // (1024 * 1024)} MB")
    if nombre.endswith(".xlsx"):
        encabezados, renglones = _leer_xlsx(contenido)
    elif nombre.endswith(".csv"):
        encabezados, renglones = _leer_csv(contenido)
    else:
        raise ErrorArchivo("Solo se aceptan archivos .xlsx y .csv")

    if not encabezados:
        raise ErrorArchivo("El archivo esta vacio o no tiene encabezados")
    campos, advertencias = _mapear_encabezados(encabezados)
    filas = _armar_filas(renglones, campos)
    if not filas:
        raise ErrorArchivo("El archivo no tiene filas de productos")
    return filas, advertencias


# --------------------------------------------------- validacion de lote


def _lista_filas(numeros) -> str:
    numeros = [str(n) for n in sorted(numeros)]
    if len(numeros) == 1:
        return f"fila {numeros[0]}"
    return f"filas {', '.join(numeros[:-1])} y {numeros[-1]}"


def validar_lote(filas, categorias=None, codigos_existentes=None, nombres_existentes=None):
    """
    Valida un lote completo con datos precargados (2-3 consultas en total,
    no una por fila). Los parametros opcionales son para tests; en uso
    normal se consultan aqui.

    -> {"total", "validas": [{fila, producto, advertencias}],
        "errores": [{fila, datos, motivos}], "advertencias": [...]}
    """
    if categorias is None:
        categorias = _categorias_vigentes()
    mapa = validacion.mapa_categorias(categorias)

    preliminar = []
    for entrada in filas:
        datos = entrada.get("datos") or {}
        producto, motivos = validacion.validar_fila(datos, mapa)
        preliminar.append((entrada.get("fila"), datos, producto, motivos))

    codigos = [p["codigo_barras"] for _, _, p, _ in preliminar if p["codigo_barras"]]
    if codigos_existentes is None:
        codigos_existentes = productos_repo.codigos_barras_existentes(codigos)
    if nombres_existentes is None:
        nombres_existentes = productos_repo.nombres_activos()
    nombres_catalogo = {validacion.normalizar_clave(n) for n in nombres_existentes}

    filas_por_codigo, filas_por_nombre = {}, {}
    for numero, _, producto, _ in preliminar:
        if producto["codigo_barras"]:
            filas_por_codigo.setdefault(producto["codigo_barras"], []).append(numero)
        if producto["nombre"]:
            clave = validacion.normalizar_clave(producto["nombre"])
            filas_por_nombre.setdefault(clave, []).append(numero)

    validas, errores = [], []
    for numero, datos, producto, motivos in preliminar:
        codigo = producto["codigo_barras"]
        if codigo:
            if codigo in codigos_existentes:
                motivos.append(validacion.MENSAJE_CODIGO_EN_USO)
            repetidas = filas_por_codigo[codigo]
            if len(repetidas) > 1:
                motivos.append(
                    f"El codigo de barras se repite en el archivo ({_lista_filas(repetidas)})"
                )
        if motivos:
            errores.append({"fila": numero, "datos": datos, "motivos": motivos})
            continue

        avisos = []
        if not codigo:
            clave = validacion.normalizar_clave(producto["nombre"])
            if clave in nombres_catalogo or len(filas_por_nombre.get(clave, [])) > 1:
                avisos.append("Posible duplicado por nombre")
        validas.append({"fila": numero, "producto": producto, "advertencias": avisos})

    advertencias = []
    if not categorias:
        advertencias.append(
            "Esta sucursal no tiene categorias de producto cargadas; ninguna fila puede importarse"
        )
    return {
        "total": len(filas),
        "validas": validas,
        "errores": errores,
        "advertencias": advertencias,
    }


def _categorias_vigentes():
    """Espejo local si esta listo, BigQuery de respaldo (igual que
    GET /api/catalogo/categorias)."""
    return vistas_catalogo._con_fallback(
        productos_local.listar_categorias, categorias_repo.listar
    )


# ------------------------------------------------------- confirmacion


def confirmar_lote(filas, usuario_id: str, **precargados):
    """
    Revalida `filas` y crea en lote las validas, con su movimiento
    `inventario_inicial` si traen cantidad > 0, y las refleja en el espejo
    local. -> {"creados": n, "omitidos": [{fila, motivos}], "error"?: str}
    """
    resultado = validar_lote(filas, **precargados)
    omitidos = [{"fila": e["fila"], "motivos": e["motivos"]} for e in resultado["errores"]]
    validas = resultado["validas"]
    respuesta = {"creados": 0, "omitidos": omitidos}
    if not validas:
        return respuesta

    try:
        creados = productos_repo.crear_varios([v["producto"] for v in validas])
        error_insercion = None
    except productos_repo.ErrorInsercionParcial as error:
        creados, error_insercion = error.creados, error
        logger.error("Importacion: fallo un bloque tras %d productos: %s", len(creados), error)

    pares = list(zip(validas, creados))
    respuesta["creados"] = len(creados)
    if error_insercion is not None:
        for valida in validas[len(creados):]:
            omitidos.append(
                {"fila": valida["fila"], "motivos": ["No se guardo: fallo la conexion con la base de datos"]}
            )
        primera = validas[len(creados)]["fila"]
        respuesta["error"] = (
            f"Se guardaron {len(creados)} productos; desde la fila {primera} no se guardo nada. "
            "Puedes volver a subir el archivo: los codigos de barras ya creados se detectan."
        )

    movimientos = [
        {
            "producto_id": fila_creada["id"],
            "tipo": "inventario_inicial",
            "cantidad": valida["producto"]["cantidad"],
            "usuario_id": usuario_id,
        }
        for valida, fila_creada in pares
        if (valida["producto"].get("cantidad") or 0) > 0
    ]
    try:
        for inicio in range(0, len(movimientos), TAMANO_BLOQUE_MOVIMIENTOS):
            movimientos_repo.insertar_varios(movimientos[inicio : inicio + TAMANO_BLOQUE_MOVIMIENTOS])
    except Exception as error:  # noqa: BLE001
        logger.error("Importacion: no se registro el inventario inicial: %s", error)
        aviso = "Los productos se crearon pero no se registro su cantidad inicial; ajustala desde el formulario."
        respuesta["error"] = " ".join(filter(None, [respuesta.get("error"), aviso]))

    _reflejar_en_espejo(pares)
    return respuesta


def _reflejar_en_espejo(pares):
    try:
        for valida, fila_creada in pares:
            producto = dict(fila_creada)
            producto["cantidad"] = valida["producto"].get("cantidad") or 0
            productos_local.upsert_producto(producto)
    except Exception as excepcion:  # noqa: BLE001 -- nunca cambia la respuesta
        logger.warning("Espejo de catalogo: no se reflejo la importacion: %s", excepcion)


# ----------------------------------------------------------- plantilla


def generar_plantilla(categorias) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation

    libro = Workbook()
    hoja = libro.active
    hoja.title = "Productos"
    requerido = PatternFill("solid", fgColor="C6EFCE")
    opcional = PatternFill("solid", fgColor="EDEDED")
    for indice, columna in enumerate(COLUMNAS, start=1):
        celda = hoja.cell(row=1, column=indice, value=columna)
        es_requerido = columna in validacion.CAMPOS_REQUERIDOS
        celda.font = Font(bold=es_requerido)
        celda.fill = requerido if es_requerido else opcional
        letra = celda.column_letter
        hoja.column_dimensions[letra].width = 28 if columna in ("nombre", "descripcion") else 16
        if columna in COLUMNAS_CODIGO:
            # Texto: que Excel no lo pase a notacion cientifica ni quite ceros.
            for fila in range(2, MAX_FILAS + 2):
                hoja.cell(row=fila, column=indice).number_format = "@"
    hoja.freeze_panes = "A2"

    hoja_cat = libro.create_sheet("Categorias")
    hoja_cat.cell(row=1, column=1, value="categoria").font = Font(bold=True)
    hoja_cat.column_dimensions["A"].width = 28
    for fila, nombre in enumerate(categorias, start=2):
        hoja_cat.cell(row=fila, column=1, value=nombre)

    if categorias:
        lista = DataValidation(
            type="list",
            formula1=f"=Categorias!$A$2:$A${len(categorias) + 1}",
            allow_blank=True,
            showErrorMessage=False,  # el backend tolera mayusculas/acentos
        )
        hoja.add_data_validation(lista)
        lista.add(f"B2:B{MAX_FILAS + 1}")

    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


# --------------------------------------------------------------- vistas


def vista_plantilla():
    contenido = generar_plantilla(_categorias_vigentes())
    return send_file(
        io.BytesIO(contenido),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="plantilla_productos.xlsx",
    )


def vista_previsualizar():
    archivo = request.files.get("archivo")
    if archivo is None or not archivo.filename:
        return jsonify(error="Falta el archivo ('archivo')"), 400
    contenido = archivo.read(MAX_BYTES + 1)
    try:
        filas, advertencias = leer_archivo(archivo.filename, contenido)
    except ErrorArchivo as error:
        return jsonify(error=str(error)), 400

    resultado = validar_lote(filas)
    resultado["advertencias"] = advertencias + resultado["advertencias"]
    return jsonify(resultado)


def vista_confirmar():
    cuerpo = request.get_json(silent=True) or {}
    filas = cuerpo.get("filas")
    if not isinstance(filas, list) or not filas:
        return jsonify(error="Faltan las filas a importar ('filas')"), 400
    if len(filas) > MAX_FILAS:
        return jsonify(error=f"Maximo {MAX_FILAS} filas por importacion"), 400
    if not all(isinstance(f, dict) and isinstance(f.get("datos"), dict) for f in filas):
        return jsonify(error="Formato de filas invalido"), 400

    return jsonify(confirmar_lote(filas, usuario_id=str(get_jwt_identity())))
