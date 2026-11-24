"""
Repositorio de la foto de perfil de un usuario (tabla `lapape.usuario_foto`,
ver esquema/tablas.py).

Una fila por usuario. `guardar` hace upsert: UPDATE si el usuario ya tiene
foto, INSERT si es la primera. Se usa DML (no streaming) a proposito --
son unos pocos usuarios y una escritura muy esporadica, y asi un UPDATE
posterior no choca con el streaming buffer de BigQuery.
"""

import datetime

from google.api_core import exceptions as api_exceptions

from acceso_datos.consultas import ejecutar_query, ejecutar_uno
from esquema.tablas import DATASET

TABLA = f"{DATASET}.usuario_foto"


def listar() -> dict:
    """
    {usuario_id: foto_url} de todos los usuarios que tienen foto.

    Si la tabla todavia no existe (falta correr `python -m
    esquema.crear_dataset`), devuelve {} en vez de reventar -- asi la
    lista de usuarios se puede ver aunque nadie tenga foto aun.
    """
    try:
        filas = ejecutar_query(f"SELECT usuario_id, foto_url FROM `{TABLA}`")
    except api_exceptions.NotFound:
        return {}
    return {fila["usuario_id"]: fila["foto_url"] for fila in filas}


def obtener(usuario_id: str):
    """La URL de la foto de `usuario_id`, o None si no tiene."""
    fila = ejecutar_uno(
        f"SELECT foto_url FROM `{TABLA}` WHERE usuario_id = @id LIMIT 1",
        {"id": usuario_id},
    )
    return fila["foto_url"] if fila else None


def guardar(usuario_id: str, foto_url: str) -> str:
    """Upsert de la foto de perfil. Devuelve la URL guardada."""
    ahora = datetime.datetime.now(datetime.timezone.utc)
    if obtener(usuario_id) is None:
        ejecutar_query(
            f"INSERT INTO `{TABLA}` (usuario_id, foto_url, actualizado_en) "
            "VALUES (@id, @url, @ts)",
            {"id": usuario_id, "url": foto_url, "ts": ahora},
        )
    else:
        ejecutar_query(
            f"UPDATE `{TABLA}` SET foto_url = @url, actualizado_en = @ts "
            "WHERE usuario_id = @id",
            {"id": usuario_id, "url": foto_url, "ts": ahora},
        )
    return foto_url
