"""
Repositorio de usuario.

`buscar_por_nombre` es lo que #3/#4 necesitan para reescribir el login
sin concatenar SQL ni comparar contrasenas en texto plano: la query solo
busca por nombre (parametrizado), y la verificacion del password
(bcrypt) se hace en Python contra el hash que esta funcion devuelve --
nunca dentro del SQL.
"""

import datetime
import uuid

from acceso_datos.consultas import ejecutar_uno
from acceso_datos.escrituras import insertar_filas
from esquema.tablas import DATASET

TABLA = f"{DATASET}.usuario"


def buscar_por_nombre(nombre: str):
    sql = f"SELECT * FROM `{TABLA}` WHERE nombre = @nombre AND activo = TRUE LIMIT 1"
    return ejecutar_uno(sql, {"nombre": nombre})


def obtener_por_id(id_: str):
    sql = f"SELECT * FROM `{TABLA}` WHERE id = @id LIMIT 1"
    return ejecutar_uno(sql, {"id": id_})


def crear(nombre: str, password_hash: str, rol: str = "empleado"):
    """rol: 'dueno' | 'empleado' -- ver #46."""
    fila = {
        "id": str(uuid.uuid4()),
        "nombre": nombre,
        "password_hash": password_hash,
        "rol": rol,
        "activo": True,
        "creado_en": datetime.datetime.now(datetime.timezone.utc),
    }
    insertar_filas(TABLA, [fila])
    return fila
