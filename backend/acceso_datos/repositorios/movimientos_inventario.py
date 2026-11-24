"""
Repositorio de movimiento_inventario. El stock NO es una columna (#8):
es SUM(cantidad) de esta tabla, agrupada por producto. Vender, comprar o
ajustar siempre INSERTA un movimiento; nada actualiza `producto`.
"""

import datetime
import uuid

from acceso_datos.consultas import ejecutar_query, ejecutar_uno
from acceso_datos.escrituras import insertar_filas
from esquema.tablas import DATASET

TABLA = f"{DATASET}.movimiento_inventario"
TABLA_PRODUCTO = f"{DATASET}.producto"


def _fila(datos: dict):
    return {
        "id": str(uuid.uuid4()),
        "producto_id": datos["producto_id"],
        # 'compra' | 'venta' | 'ajuste' | 'merma' | 'cancelacion'
        # | 'inventario_inicial'
        "tipo": datos["tipo"],
        # Con signo: positivo entra, negativo sale.
        "cantidad": float(datos["cantidad"]),
        "costo_unitario": (
            float(datos["costo_unitario"])
            if datos.get("costo_unitario") is not None
            else None
        ),
        "referencia_id": datos.get("referencia_id"),
        "fecha": datos.get("fecha") or datetime.datetime.now(datetime.timezone.utc),
        "usuario_id": datos["usuario_id"],
    }


def insertar(datos: dict):
    fila = _fila(datos)
    insertar_filas(TABLA, [fila])
    return fila


def insertar_varios(movimientos: list):
    """Para descontar varias lineas de producto de una sola venta (#21)."""
    filas = [_fila(datos) for datos in movimientos]
    insertar_filas(TABLA, filas)
    return filas


def stock_actual(producto_id: str):
    sql = f"""
        SELECT COALESCE(SUM(cantidad), 0) AS stock
        FROM `{TABLA}`
        WHERE producto_id = @producto_id
    """
    fila = ejecutar_uno(sql, {"producto_id": producto_id})
    return fila["stock"] if fila else 0


def stock_de_varios(producto_ids: list):
    """
    {producto_id: stock} para una lista de productos, en una sola
    consulta -- evita hacer una llamada a BigQuery por producto al
    listar un catalogo con existencia (#28).
    """
    if not producto_ids:
        return {}

    sql = f"""
        SELECT producto_id, COALESCE(SUM(cantidad), 0) AS stock
        FROM `{TABLA}`
        WHERE producto_id IN UNNEST(@producto_ids)
        GROUP BY producto_id
    """
    filas = ejecutar_query(
        sql, {"producto_ids": list(producto_ids)}, {"producto_ids": "STRING"}
    )
    return {fila["producto_id"]: fila["stock"] for fila in filas}


def stock_de_todos():
    """
    {producto_id: stock} para TODOS los productos con movimientos, en una
    sola consulta -- lo usa el refresco periodico del espejo local del
    catalogo (#13, ver almacen_local/espejo_catalogo.py), que necesita el
    stock agregado completo en cada ciclo, no solo el de una pagina.
    """
    sql = f"""
        SELECT producto_id, COALESCE(SUM(cantidad), 0) AS stock
        FROM `{TABLA}`
        GROUP BY producto_id
    """
    filas = ejecutar_query(sql)
    return {fila["producto_id"]: fila["stock"] for fila in filas}


def stock_bajo(umbral_por_defecto=5):
    """
    Productos cuyo stock calculado esta en o por debajo de su
    stock_minimo, o del umbral por defecto si no tienen uno definido (#31).
    """
    sql = f"""
        SELECT
            p.id, p.nombre, p.stock_minimo,
            COALESCE(SUM(m.cantidad), 0) AS stock
        FROM `{TABLA_PRODUCTO}` p
        LEFT JOIN `{TABLA}` m ON m.producto_id = p.id
        WHERE p.activo = TRUE
        GROUP BY p.id, p.nombre, p.stock_minimo
        HAVING stock <= COALESCE(p.stock_minimo, @umbral_por_defecto)
        ORDER BY stock ASC
    """
    return ejecutar_query(
        sql,
        {"umbral_por_defecto": umbral_por_defecto},
        {"umbral_por_defecto": "NUMERIC"},
    )


def kardex(producto_id: str, fecha_inicio=None, fecha_fin=None):
    """Historial de movimientos de un producto, en orden (#31)."""
    condiciones = ["producto_id = @producto_id"]
    valores = {"producto_id": producto_id}
    tipos = {}
    if fecha_inicio is not None:
        condiciones.append("DATE(fecha) >= @fecha_inicio")
        valores["fecha_inicio"] = fecha_inicio
        tipos["fecha_inicio"] = "DATE"
    if fecha_fin is not None:
        condiciones.append("DATE(fecha) <= @fecha_fin")
        valores["fecha_fin"] = fecha_fin
        tipos["fecha_fin"] = "DATE"

    sql = f"""
        SELECT * FROM `{TABLA}`
        WHERE {' AND '.join(condiciones)}
        ORDER BY fecha
    """
    return ejecutar_query(sql, valores, tipos)
