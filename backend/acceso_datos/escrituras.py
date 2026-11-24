"""
Insercion de filas por streaming (tabledata.insertAll), nunca por DML
INSERT -- ver la regla de #8: el camino caliente (venta,
movimiento_inventario, cierre) es append-only y no debe chocar con las
cuotas de DML de BigQuery.

Se eligio `insert_rows_json` (streaming clasico) sobre la Storage Write
API por simplicidad: a la escala del negocio (decenas de ventas al dia)
el streaming clasico sobra por mucho margen y no requiere generar
esquemas protobuf ni una dependencia adicional. Si el volumen creciera
varios ordenes de magnitud, migrar a la Storage Write API es un cambio
localizado a este archivo -- ningun repositorio tendria que cambiar.
"""

import datetime
import decimal

from acceso_datos.cliente import obtener_cliente


class ErrorInsercion(Exception):
    """BigQuery acepto la peticion pero rechazo una o mas filas."""

    def __init__(self, errores):
        self.errores = errores
        super().__init__(f"BigQuery rechazo filas al insertar: {errores}")


def _serializable(valor):
    """insert_rows_json necesita JSON puro: fechas y decimales a texto."""
    if isinstance(valor, (datetime.datetime, datetime.date)):
        return valor.isoformat()
    if isinstance(valor, decimal.Decimal):
        return str(valor)
    if isinstance(valor, dict):
        return {k: _serializable(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_serializable(v) for v in valor]
    return valor


def insertar_filas(tabla: str, filas: list, cliente=None):
    """
    tabla: "dataset.tabla" (sin project id; se resuelve con el cliente).
    filas: lista de dicts, cada una con su propio 'id' (UUID) puesto por
    quien llama.

    El 'id' de cada fila se manda ademas como `row_id` de streaming, que
    activa la deduplicacion de BigQuery ante reintentos -- pero esa
    deduplicacion es "best effort" y solo cubre una ventana corta (del
    orden de minutos), no una garantia indefinida. Para el reenvio desde
    el journal local tras una caida larga de internet (#55), no confiar
    solo en esto: la cola de sincronizacion debe llevar su propio
    registro de que ya se envio, y una limpieza periodica de duplicados
    (por 'id') es la red de seguridad final si algo se cuela.
    """
    if not filas:
        return

    cliente = cliente or obtener_cliente()
    tabla_id = f"{cliente.project}.{tabla}"
    filas_json = [_serializable(fila) for fila in filas]
    row_ids = [fila["id"] for fila in filas]

    errores = cliente.insert_rows_json(tabla_id, filas_json, row_ids=row_ids)
    if errores:
        raise ErrorInsercion(errores)
