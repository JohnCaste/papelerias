"""
Repositorio de venta. La venta completa (con sus lineas) es UNA fila --
ver el diseno de #8. Insertar es la unica operacion normal; nunca se
hace UPDATE ni DELETE sobre esta tabla (ver esquema/README.md).

Cancelar una venta (#26) NO modifica la fila original: inserta una fila
nueva de signo contrario que la referencia por `venta_original_id`. Esto
respeta el append-only de #8 y tiene una consecuencia en como se suman
los totales: sumar `total` de TODAS las filas del periodo (sin filtrar
por `estado`) ya da el neto correcto, porque la fila de reversion resta
exactamente lo que sumo la original. `estado` es informativo para el
historial (que fila es cual), no un filtro para el calculo del dinero.
"""

import datetime

from acceso_datos.consultas import ejecutar_query, ejecutar_uno
from acceso_datos.escrituras import insertar_filas
from acceso_datos.modelos_venta import construir_venta
from esquema.tablas import DATASET

TABLA = f"{DATASET}.venta"


def insertar(datos: dict):
    """
    Ver `acceso_datos.modelos_venta.construir_venta` para la forma de
    `datos`. La construccion de la fila se comparte con el journal
    local (#14) para que las dos rutas de escritura nunca diverjan.
    """
    fila = construir_venta(datos)
    insertar_filas(TABLA, [fila])
    return fila


def obtener_por_id(id_: str):
    sql = f"SELECT * FROM `{TABLA}` WHERE id = @id LIMIT 1"
    return ejecutar_uno(sql, {"id": id_})


def listar_por_rango(fecha_inicio, fecha_fin):
    """fecha_inicio/fecha_fin: datetime.date. Aprovecha la particion por fecha_hora."""
    sql = f"""
        SELECT * FROM `{TABLA}`
        WHERE DATE(fecha_hora) BETWEEN @fecha_inicio AND @fecha_fin
        ORDER BY fecha_hora
    """
    return ejecutar_query(
        sql,
        {"fecha_inicio": fecha_inicio, "fecha_fin": fecha_fin},
        {"fecha_inicio": "DATE", "fecha_fin": "DATE"},
    )


def total_del_rango(fecha_inicio, fecha_fin):
    """
    Suma TODAS las filas del rango (activas + reversiones). Ver nota del
    modulo: no se filtra por `estado`, la resta ya esta incluida en las
    filas de reversion. `num_ventas` cuenta solo filas que no son
    reversion, para no contar una cancelacion como una venta mas.
    """
    sql = f"""
        SELECT
            COALESCE(SUM(total), 0) AS total,
            COUNTIF(venta_original_id IS NULL) AS num_ventas
        FROM `{TABLA}`
        WHERE DATE(fecha_hora) BETWEEN @fecha_inicio AND @fecha_fin
    """
    return ejecutar_uno(
        sql,
        {"fecha_inicio": fecha_inicio, "fecha_fin": fecha_fin},
        {"fecha_inicio": "DATE", "fecha_fin": "DATE"},
    )


def cancelar(venta_original_id: str, usuario_id: str, motivo: str):
    """Inserta la fila de reversion (#26). No modifica la fila original."""
    original = obtener_por_id(venta_original_id)
    if original is None:
        raise ValueError(f"No existe la venta {venta_original_id}")
    if original.get("venta_original_id") is not None:
        raise ValueError("No se puede cancelar una fila que ya es una reversion")

    lineas_revertidas = [
        {
            **linea,
            "cantidad": -linea["cantidad"],
            "subtotal": -linea["subtotal"],
            "monto_comision": (
                -linea["monto_comision"]
                if linea.get("monto_comision") is not None
                else None
            ),
        }
        for linea in original["lineas"]
    ]

    ahora = datetime.datetime.now(datetime.timezone.utc)
    return insertar(
        {
            "fecha_hora": ahora,
            "total": -original["total"],
            "metodo_pago": original["metodo_pago"],
            "usuario_id": usuario_id,
            "estado": "cancelada",
            "detallada": original["detallada"],
            "origen": "pos",
            "extemporanea": False,
            "venta_original_id": venta_original_id,
            "motivo_cancelacion": motivo,
            "cancelada_por": usuario_id,
            "cancelada_en": ahora,
            "lineas": lineas_revertidas,
        }
    )
