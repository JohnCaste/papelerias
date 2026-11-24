"""
Repositorio de `categoria`: la lista canonica y fija de categorias de
producto. Ver esquema en esquema/tablas.py y el sembrado en
esquema/sembrar_categorias.py.

A diferencia de `producto`, esta tabla NO se edita desde la UI: es un
catalogo administrado por script. El formulario de alta/edicion de
producto solo ofrece estos nombres (selector cerrado, sin texto libre).
"""

import datetime

from acceso_datos.consultas import ejecutar_query
from acceso_datos.escrituras import insertar_filas
from esquema.tablas import DATASET

TABLA = f"{DATASET}.categoria"


def _ahora():
    return datetime.datetime.now(datetime.timezone.utc)


def listar():
    """Nombres de categoria activos, en el orden con el que se sembraron."""
    sql = f"""
        SELECT nombre FROM `{TABLA}`
        WHERE activo = TRUE
        ORDER BY orden
    """
    return [fila["nombre"] for fila in ejecutar_query(sql)]


def borrar_todas():
    """DELETE de todas las filas -- lo usa el sembrado antes de reinsertar.
    Baja frecuencia (script manual), cabe en la cuota de DML."""
    ejecutar_query(f"DELETE FROM `{TABLA}` WHERE TRUE")


def sembrar(nombres):
    """Inserta la lista dada asignando 'orden' por posicion (0..n-1).
    No borra: llamar antes borrar_todas() si se quiere reemplazo limpio."""
    ahora = _ahora()
    filas = [
        {
            "id": nombre,
            "nombre": nombre,
            "orden": indice,
            "activo": True,
            "creado_en": ahora,
        }
        for indice, nombre in enumerate(nombres)
    ]
    insertar_filas(TABLA, filas)
    return filas
