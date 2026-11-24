"""
Forma de una fila de 'venta', independiente de a donde se escriba.

Se comparte entre:
  - acceso_datos/repositorios/ventas.py  (destino: BigQuery)
  - almacen_local/journal.py             (destino: archivo local, #14)

Sin esto, las dos rutas de escritura (local y BigQuery) tendrian cada
una su propia idea de que campos lleva una venta y como se normalizan
las lineas -- y tarde o temprano se desincronizarian.
"""

import datetime
import uuid


def construir_venta(datos: dict) -> dict:
    """
    datos: {
      id (opcional -- pasarlo permite que quien capture controle el id
          desde el origen, para que un reintento sea idempotente),
      fecha_hora (opcional, default ahora),
      total, metodo_pago, usuario_id, detallada,
      vendedor (opcional -- nombre de quien capturo la venta, para el
          reporte "quien vendio"; None en filas migradas o de ajuste),
      origen ('pos' | 'migracion', default 'pos'),
      extemporanea (default False), motivo_extemporanea (default None),
      venta_original_id (solo si es una fila de ajuste: reversion de
          cancelacion #26, o reversion/recaptura de edicion de monto),
      estado ('activa' por defecto; 'cancelada'/'devolucion_parcial' en una
          reversion de #26; 'editada'/'editada_reversa' en las filas de
          edicion de monto),
      motivo_cancelacion, cancelada_por, cancelada_en
          (solo en una fila de ajuste -- #26 y edicion de monto; None en una
          venta normal),
      lineas: [ {tipo, categoria, producto_id, servicio_id, descripcion,
                 cantidad, precio_unitario, costo_unitario, subtotal,
                 monto_comision}, ... ]
    }

    No valida que `total` sea igual a la suma de las lineas -- esa es
    una regla de negocio de la pantalla de venta (#20/#21/#22), no de
    este modulo.
    """
    return {
        "id": datos.get("id") or str(uuid.uuid4()),
        "fecha_hora": datos.get("fecha_hora") or datetime.datetime.now(datetime.timezone.utc),
        "total": float(datos["total"]),
        "metodo_pago": datos["metodo_pago"],
        "usuario_id": datos["usuario_id"],
        "vendedor": datos.get("vendedor"),
        "estado": datos.get("estado", "activa"),
        "detallada": bool(datos.get("detallada", False)),
        "origen": datos.get("origen", "pos"),
        "extemporanea": bool(datos.get("extemporanea", False)),
        "motivo_extemporanea": datos.get("motivo_extemporanea"),
        "venta_original_id": datos.get("venta_original_id"),
        "motivo_cancelacion": datos.get("motivo_cancelacion"),
        "cancelada_por": datos.get("cancelada_por"),
        "cancelada_en": datos.get("cancelada_en"),
        "creado_en": datetime.datetime.now(datetime.timezone.utc),
        "lineas": normalizar_lineas(datos.get("lineas", [])),
    }


def normalizar_lineas(lineas):
    normalizadas = []
    for linea in lineas:
        normalizadas.append(
            {
                "tipo": linea["tipo"],
                "categoria": linea.get("categoria"),
                "producto_id": linea.get("producto_id"),
                "servicio_id": linea.get("servicio_id"),
                "descripcion": linea.get("descripcion"),
                "cantidad": float(linea["cantidad"]),
                "precio_unitario": float(linea["precio_unitario"]),
                "costo_unitario": (
                    float(linea["costo_unitario"])
                    if linea.get("costo_unitario") is not None
                    else None
                ),
                "subtotal": float(linea["subtotal"]),
                "monto_comision": (
                    float(linea["monto_comision"])
                    if linea.get("monto_comision") is not None
                    else None
                ),
            }
        )
    return normalizadas
