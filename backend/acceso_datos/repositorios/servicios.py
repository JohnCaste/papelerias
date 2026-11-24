"""
Repositorio de servicio (copias, impresion, escaneo, etc. -- #22, #23).
Sin stock: los servicios no tienen existencia, solo precio.
"""

import datetime
import uuid

from acceso_datos.consultas import ejecutar_query, ejecutar_uno
from acceso_datos.escrituras import insertar_filas
from esquema.tablas import DATASET

TABLA = f"{DATASET}.servicio"


def _ahora():
    return datetime.datetime.now(datetime.timezone.utc)


def listar_activos():
    sql = f"SELECT * FROM `{TABLA}` WHERE activo = TRUE ORDER BY nombre"
    return ejecutar_query(sql)


def obtener_por_id(id_: str):
    sql = f"SELECT * FROM `{TABLA}` WHERE id = @id LIMIT 1"
    return ejecutar_uno(sql, {"id": id_})


def crear(datos: dict):
    ahora = _ahora()
    fila = {
        "id": str(uuid.uuid4()),
        "nombre": datos["nombre"],
        "unidad": datos["unidad"],
        "precio": float(datos["precio"]),
        "activo": True,
        "creado_en": ahora,
        "actualizado_en": ahora,
    }
    insertar_filas(TABLA, [fila])
    return fila


def actualizar(id_: str, datos: dict):
    campos = ("nombre", "unidad", "precio")
    cambios = {c: datos[c] for c in campos if c in datos}
    if not cambios:
        return

    asignaciones = ", ".join(f"{c} = @{c}" for c in cambios)
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
    sql = f"UPDATE `{TABLA}` SET activo = FALSE, actualizado_en = @ahora WHERE id = @id"
    ejecutar_query(sql, {"id": id_, "ahora": _ahora()})
