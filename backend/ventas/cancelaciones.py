"""
Cancelacion de ventas (#26).

Cancelar NO borra ni modifica la venta original: escribe una fila NUEVA
de signo contrario en el journal local (#14), igual que la captura (#20)
-- para que funcione sin internet y sin bloquearse esperando a BigQuery.
El sincronizador (#15) sube esa fila y, como lleva `venta_original_id`,
genera los `movimiento_inventario` inversos que devuelven el stock.

El dinero cancelado se excluye del total del dia por NETEO, no por
filtro: sumar `total` de todas las filas del journal ya da el neto
correcto porque la reversion resta exactamente lo que sumo la original.

    POST /api/ventas/<venta_id>/cancelar
    body: { motivo (obligatorio), fecha (YYYY-MM-DD de la venta original),
            lineas? ([indices] para devolucion parcial) }
"""

import datetime
import uuid

from flask import jsonify, request
from flask_jwt_extended import get_jwt_identity

from almacen_local import journal

# Namespace fijo para derivar el id determinista de la fila de reversion
# -- un doble clic o un reintento del endpoint escribe el mismo id, y el
# journal lo colapsa al leer (dict por id) en vez de crear dos reversiones.
_NAMESPACE_REVERSION = uuid.uuid5(uuid.NAMESPACE_DNS, "lapape.cancelacion_venta")


def cancelar_venta(venta_id: str):
    datos = request.get_json(silent=True) or {}

    motivo = (datos.get("motivo") or "").strip()
    if not motivo:
        return jsonify(error="La cancelacion necesita un motivo"), 400

    fecha_texto = datos.get("fecha")
    try:
        fecha = datetime.date.fromisoformat(fecha_texto) if fecha_texto else None
    except (TypeError, ValueError):
        fecha = None
    if fecha is None:
        return jsonify(error="'fecha' debe tener formato YYYY-MM-DD"), 400

    original = journal.buscar_venta(venta_id, fecha)
    if original is None:
        return jsonify(error=f"No existe la venta {venta_id} en {fecha.isoformat()}"), 404
    if original.get("venta_original_id") is not None:
        return jsonify(error="No se puede cancelar una fila que ya es una reversion"), 400

    lineas_original = original.get("lineas") or []
    indices_pedidos = datos.get("lineas")
    if indices_pedidos is None:
        indices = list(range(len(lineas_original)))
    else:
        if not isinstance(indices_pedidos, list) or any(
            not isinstance(i, int) or i < 0 or i >= len(lineas_original)
            for i in indices_pedidos
        ):
            return jsonify(error="'lineas' trae un indice que no existe en la venta"), 400
        indices = sorted(set(indices_pedidos))

    if not indices:
        return jsonify(error="No hay lineas que revertir"), 400

    parcial = len(indices) < len(lineas_original)
    estado = "devolucion_parcial" if parcial else "cancelada"

    lineas_revertidas = [_revertir_linea(lineas_original[i]) for i in indices]
    # `subtotal` de cada linea revertida ya viene con signo negativo.
    total_revertido = sum(linea["subtotal"] for linea in lineas_revertidas)

    ahora = datetime.datetime.now(datetime.timezone.utc)
    reversion_id = str(
        uuid.uuid5(_NAMESPACE_REVERSION, f"{venta_id}:{estado}:{indices}")
    )

    fila = journal.escribir_venta(
        {
            "id": reversion_id,
            "fecha_hora": ahora,
            "total": total_revertido,
            "metodo_pago": original["metodo_pago"],
            "usuario_id": get_jwt_identity(),
            "estado": estado,
            "detallada": original.get("detallada", False),
            "origen": "pos",
            "extemporanea": False,
            "venta_original_id": venta_id,
            "motivo_cancelacion": motivo,
            "cancelada_por": get_jwt_identity(),
            "cancelada_en": ahora,
            "lineas": lineas_revertidas,
        }
    )

    return jsonify(_a_json(fila)), 201


def clasificar_ventas(ventas: list):
    """
    Separa las filas de ajuste (reversiones de #26 y ediciones de monto)
    de las ventas reales de un dia.

    Devuelve `(reales, canceladas_ids, editadas)`:
      - `reales`: las filas con `venta_original_id` nulo, en el mismo orden.
        NO incluye las reversiones ni las recapturas de edicion -- pero quien
        calcula el total del dia sigue sumando `total` sobre TODAS las filas:
        la reversion resta por neteo, no por filtro.
      - `canceladas_ids`: ids de venta que tienen una reversion TOTAL
        (`estado == 'cancelada'`) apuntandolas. Una devolucion parcial
        (`estado == 'devolucion_parcial'`) no marca la venta como cancelada.
      - `editadas`: `{venta_original_id -> monto_vigente}` para cada venta con
        una o mas recapturas de edicion (`estado == 'editada'`); el monto
        vigente es el `total` de la recaptura mas reciente (por `fecha_hora`).
        Las filas de edicion (`estado in {'editada', 'editada_reversa'}`) llevan
        `venta_original_id`, asi que ya quedan fuera de `reales`.

    Precedencia al leer el dia: `cancelada` gana a `editada` -- una venta que
    aparece en `canceladas_ids` se muestra cancelada aunque tambien este en
    `editadas`.
    """
    canceladas_ids = {
        v["venta_original_id"]
        for v in ventas
        if v.get("venta_original_id") is not None and v.get("estado") == "cancelada"
    }

    recapturas = sorted(
        (v for v in ventas if v.get("estado") == "editada" and v.get("venta_original_id")),
        key=lambda v: v.get("fecha_hora") or "",
    )
    editadas = {v["venta_original_id"]: float(v["total"]) for v in recapturas}

    reales = [v for v in ventas if v.get("venta_original_id") is None]
    return reales, canceladas_ids, editadas


def _revertir_linea(linea: dict) -> dict:
    """Misma linea con cantidad/subtotal/comision de signo contrario."""
    revertida = dict(linea)
    revertida["cantidad"] = -float(linea["cantidad"])
    revertida["subtotal"] = -float(linea["subtotal"])
    if linea.get("monto_comision") is not None:
        revertida["monto_comision"] = -float(linea["monto_comision"])
    return revertida


def _a_json(fila: dict) -> dict:
    """fecha_hora/creado_en/cancelada_en llegan como datetime; a texto ISO."""
    salida = dict(fila)
    for campo in ("fecha_hora", "creado_en", "cancelada_en"):
        valor = salida.get(campo)
        if isinstance(valor, (datetime.datetime, datetime.date)):
            salida[campo] = valor.isoformat()
    return salida
