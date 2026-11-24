"""
Cliente unico de BigQuery, reutilizado en todo el backend.

Antes cada funcion de catalogos/productos.py y registros/valores.py
instanciaba su propio bigquery.Client(). Esto lo centraliza: un solo
cliente construido una vez y compartido por todos los repositorios.
"""

from google.cloud import bigquery

import autentificacion.serviciosCloud as serviciosCloud

_cliente = None


def obtener_cliente():
    """Devuelve el cliente de BigQuery, construyendolo la primera vez."""
    global _cliente
    if _cliente is None:
        _cliente = bigquery.Client(
            credentials=serviciosCloud.get_credentials(),
            project=serviciosCloud.get_project_id(),
        )
    return _cliente


def resetear_cliente():
    """Solo para tests: fuerza que la siguiente llamada reconstruya el cliente."""
    global _cliente
    _cliente = None
