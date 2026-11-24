"""
Repositorio del rol de un usuario (tabla `lapape.usuario_rol`, ver
esquema/tablas.py). Mismo patron que usuario_fotos: una fila por usuario,
upsert por DML.

Un usuario sin fila aqui es 'empleado' (el minimo). Solo 'dueno' ve las
pantallas de Ventas y Corte -- el bloqueo hoy es solo en el frontend
(navbar + rutas), la API no lo aplica.
"""

import datetime

from google.api_core import exceptions as api_exceptions

from acceso_datos.consultas import ejecutar_query, ejecutar_uno
from esquema.tablas import DATASET

TABLA = f"{DATASET}.usuario_rol"

ROL_DUENO = "dueno"
ROL_EMPLEADO = "empleado"
ROLES_VALIDOS = frozenset({ROL_DUENO, ROL_EMPLEADO})


def listar() -> dict:
    """
    {usuario_id: rol} de los usuarios que tienen un rol asignado. Si la
    tabla todavia no existe (falta `python -m esquema.crear_dataset`),
    devuelve {} -- todos se tratan como 'empleado'.
    """
    try:
        filas = ejecutar_query(f"SELECT usuario_id, rol FROM `{TABLA}`")
    except api_exceptions.NotFound:
        return {}
    return {fila["usuario_id"]: fila["rol"] for fila in filas}


def obtener(usuario_id: str):
    """El rol de `usuario_id`, o None si no tiene fila (=> 'empleado')."""
    try:
        fila = ejecutar_uno(
            f"SELECT rol FROM `{TABLA}` WHERE usuario_id = @id LIMIT 1",
            {"id": usuario_id},
        )
    except api_exceptions.NotFound:
        return None
    return fila["rol"] if fila else None


def guardar(usuario_id: str, rol: str) -> str:
    """Upsert del rol. `rol` debe estar en ROLES_VALIDOS (lo valida quien llama)."""
    ahora = datetime.datetime.now(datetime.timezone.utc)
    if obtener(usuario_id) is None:
        ejecutar_query(
            f"INSERT INTO `{TABLA}` (usuario_id, rol, actualizado_en) "
            "VALUES (@id, @rol, @ts)",
            {"id": usuario_id, "rol": rol, "ts": ahora},
        )
    else:
        ejecutar_query(
            f"UPDATE `{TABLA}` SET rol = @rol, actualizado_en = @ts "
            "WHERE usuario_id = @id",
            {"id": usuario_id, "rol": rol, "ts": ahora},
        )
    return rol
