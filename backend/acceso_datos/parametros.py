"""
Construccion de parametros para consultas parametrizadas.

Todas las consultas del sistema deben pasar por aqui en vez de interpolar
valores en el texto del SQL -- es la forma en que se cierra la inyeccion
SQL (#4). Ver `consultas.ejecutar_query`.
"""

import datetime
import decimal

from google.cloud import bigquery


# El orden importa: en Python `bool` es subclase de `int`, asi que bool
# debe revisarse primero o un True/False terminaria mapeado a INT64.
_TIPOS_POR_CLASE = [
    (bool, "BOOL"),
    (int, "INT64"),
    (float, "NUMERIC"),
    (decimal.Decimal, "NUMERIC"),
    (datetime.datetime, "TIMESTAMP"),
    (datetime.date, "DATE"),
    (str, "STRING"),
]


def _tipo_bigquery(valor):
    for clase, tipo in _TIPOS_POR_CLASE:
        if isinstance(valor, clase):
            return tipo
    raise TypeError(
        f"No se sabe mapear el tipo Python {type(valor).__name__!r} a "
        "BigQuery. Pasa el tipo explicito en `tipos`, o agregalo a "
        "_TIPOS_POR_CLASE en acceso_datos/parametros.py."
    )


def _construir_uno(nombre, valor, tipo_forzado):
    if isinstance(valor, (list, tuple)):
        # Para `WHERE columna IN UNNEST(@nombre)`. BigQuery exige un tipo
        # de elemento aunque el arreglo venga vacio.
        if not valor:
            if tipo_forzado is None:
                raise TypeError(
                    f"El parametro '{nombre}' es un arreglo vacio; su tipo "
                    "de elemento no se puede inferir. Pasalo explicito en "
                    "`tipos` (por ejemplo {'"
                    + nombre
                    + "': 'STRING'})."
                )
            return bigquery.ArrayQueryParameter(nombre, tipo_forzado, [])
        tipo_elemento = tipo_forzado or _tipo_bigquery(valor[0])
        return bigquery.ArrayQueryParameter(nombre, tipo_elemento, list(valor))

    tipo = tipo_forzado
    if tipo is None:
        if valor is None:
            raise TypeError(
                f"El parametro '{nombre}' es None; su tipo BigQuery no se "
                "puede inferir. Pasalo explicito en `tipos`."
            )
        tipo = _tipo_bigquery(valor)
    return bigquery.ScalarQueryParameter(nombre, tipo, valor)


def construir_parametros(valores: dict, tipos: dict | None = None):
    """
    valores: {"nombre_parametro": valor_python}. Una lista/tupla se
             traduce a ArrayQueryParameter, para usar con
             `columna IN UNNEST(@nombre)`.
    tipos:   opcional, {"nombre_parametro": "TIPO_BIGQUERY"} para forzar
             el tipo cuando no se puede inferir (un valor None, un
             arreglo vacio, o para distinguir INT64 de NUMERIC).
    """
    tipos = tipos or {}
    return [
        _construir_uno(nombre, valor, tipos.get(nombre))
        for nombre, valor in valores.items()
    ]
