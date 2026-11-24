"""
Ejecucion de consultas de lectura contra BigQuery, siempre parametrizadas.

Regla del proyecto: ninguna funcion arma `sql` concatenando datos de
entrada con f-strings. Los valores variables van en `valores`, que se
traduce a `ScalarQueryParameter` -- eso es lo que cierra la inyeccion
SQL (#4). El unico texto que puede variar en el SQL son nombres de
columna fijos elegidos por el propio codigo (por ejemplo, la lista de
condiciones de un filtro), nunca contenido que venga del usuario.
"""

from google.api_core import exceptions as api_exceptions
from google.api_core import retry as api_retry
from google.cloud import bigquery

from acceso_datos.cliente import obtener_cliente
from acceso_datos.parametros import construir_parametros

# Reintenta solo errores transitorios (red, servicio ocupado). Un error
# de sintaxis SQL o de permisos no se reintenta: fallaria igual.
REINTENTO_DEFECTO = api_retry.Retry(
    predicate=api_retry.if_exception_type(
        api_exceptions.ServiceUnavailable,
        api_exceptions.InternalServerError,
        api_exceptions.TooManyRequests,
        api_exceptions.DeadlineExceeded,
    ),
    initial=1.0,
    maximum=10.0,
    multiplier=2.0,
    deadline=30.0,
)


def ejecutar_query(
    sql: str,
    valores: dict | None = None,
    tipos: dict | None = None,
    cliente=None,
    retry=REINTENTO_DEFECTO,
):
    """
    Corre una consulta parametrizada y devuelve la lista de filas, cada
    una como dict.
    """
    cliente = cliente or obtener_cliente()
    valores = valores or {}

    config = bigquery.QueryJobConfig(
        query_parameters=construir_parametros(valores, tipos)
    )

    job = cliente.query(sql, job_config=config, retry=retry)
    resultados = job.result(retry=retry)
    return [dict(fila) for fila in resultados]


def ejecutar_uno(sql: str, valores: dict | None = None, tipos: dict | None = None, cliente=None):
    """Igual que ejecutar_query, pero devuelve la primera fila o None."""
    filas = ejecutar_query(sql, valores, tipos, cliente)
    return filas[0] if filas else None
