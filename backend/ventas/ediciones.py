"""
Edicion del MONTO de una venta ya registrada (editar-ventas).

Editar NO borra ni modifica la venta original: escribe DOS filas nuevas
en el journal del dia de la VENTA (no el de hoy: `fecha_hora` cae en el
dia editado para que el neto -vigente + nuevo agrupe en ese dia civil,
no en el actual -- ver `_instante`), igual que la cancelacion (#26):

  1. una REVERSION del importe vigente (todas sus lineas negadas),
     `estado = "editada_reversa"`;
  2. una RECAPTURA con el monto nuevo, `estado = "editada"`, con las
     lineas del importe vigente escaladas en proporcion para que sumen
     exactamente `monto_nuevo` (la `cantidad` y las claves de cada linea
     no cambian -- "solo cambio el monto").

El delta (monto nuevo - monto vigente) ajusta el total del dia por
NETEO: -monto_vigente + monto_nuevo. La venta original se muestra con
`estado = "editada"` y su monto vigente al leer el dia (ver
`cancelaciones.clasificar_ventas`).

    POST /api/ventas/<venta_id>/editar
    body: { motivo (obligatorio), fecha (YYYY-MM-DD de la venta original),
            monto_nuevo (numero > 0, distinto del monto vigente) }
"""

import datetime
import uuid

from flask import jsonify, request
from flask_jwt_extended import get_jwt_identity

from almacen_local import journal
from ventas import cancelaciones

# Namespace fijo para derivar los ids deterministas de las filas de
# edicion -- un doble clic o un reintento del endpoint con el mismo
# `monto_nuevo` reescribe los mismos ids y el journal los colapsa (dict
# por id al leer) en vez de aplicar el delta dos veces.
_NAMESPACE_EDICION = uuid.uuid5(uuid.NAMESPACE_DNS, "lapape.edicion_venta")


def _instante(fecha: datetime.date, secuencia: int) -> datetime.datetime:
    """
    Instante para `fecha_hora` de las filas de edicion: 18:00 UTC del dia
    de la VENTA (no de hoy). En `America/Mexico_City` (UTC-6, sin horario
    de verano desde 2023) eso es mediodia -- el mismo dia civil con
    cualquier offset plausible. Mismo criterio que
    `acceso_datos/repositorios/resumen_diario._instante`.

    Por que el dia de la venta y no `ahora`: `journal.escribir_venta`
    archiva por `fecha_hora.date()` y las agregaciones agrupan por
    `DATE(fecha_hora, zona)`. Fechar la reversion/recaptura en `ahora`
    mandaria el neto (-vigente + nuevo) al journal y al bucket del dia en
    curso en vez del dia editado: editar una venta de ayer le sumaria el
    delta a HOY y no la tocaria en su dia. `cancelada_en` si es `ahora`
    -- es auditoria de cuando se edito.

    `secuencia` (0, 1, 2... = cuantas ediciones previas tiene la venta)
    se suma como segundos para que las recapturas de re-ediciones sucesivas
    queden ordenadas por `fecha_hora` y `clasificar_ventas` pueda tomar la
    mas reciente.
    """
    base = datetime.datetime(
        fecha.year, fecha.month, fecha.day, 18, 0, tzinfo=datetime.timezone.utc
    )
    return base + datetime.timedelta(seconds=secuencia)


def editar_venta(venta_id: str):
    datos = request.get_json(silent=True) or {}

    motivo = (datos.get("motivo") or "").strip()
    if not motivo:
        return jsonify(error="La edicion necesita un motivo"), 400

    fecha_texto = datos.get("fecha")
    try:
        fecha = datetime.date.fromisoformat(fecha_texto) if fecha_texto else None
    except (TypeError, ValueError):
        fecha = None
    if fecha is None:
        return jsonify(error="'fecha' debe tener formato YYYY-MM-DD"), 400

    try:
        monto_nuevo = float(datos.get("monto_nuevo"))
    except (TypeError, ValueError):
        return jsonify(error="'monto_nuevo' debe ser un numero"), 400
    if monto_nuevo <= 0:
        return jsonify(error="'monto_nuevo' debe ser mayor a cero"), 400

    dia = journal.leer_dia(fecha)
    original = next((v for v in dia if v["id"] == venta_id), None)
    if original is None:
        return jsonify(error=f"No existe la venta {venta_id} en {fecha.isoformat()}"), 404
    if original.get("venta_original_id") is not None:
        return jsonify(error="No se puede editar una fila de ajuste"), 400

    _, canceladas_ids, _ = cancelaciones.clasificar_ventas(dia)
    if venta_id in canceladas_ids:
        return jsonify(error="No se puede editar una venta cancelada"), 400

    # Monto vigente y secuencia: si la venta ya fue editada, se revierte
    # la RECAPTURA mas reciente, no la venta original.
    recapturas = sorted(
        (
            v
            for v in dia
            if v.get("estado") == "editada" and v.get("venta_original_id") == venta_id
        ),
        key=lambda v: v.get("fecha_hora") or "",
    )
    vigente = recapturas[-1] if recapturas else original
    monto_vigente = float(vigente["total"])
    lineas_vigentes = vigente.get("lineas") or []
    secuencia = len(recapturas)

    if abs(monto_nuevo - monto_vigente) < 1e-9:
        return jsonify(error="'monto_nuevo' es igual al monto vigente"), 400

    ahora = datetime.datetime.now(datetime.timezone.utc)
    comun = {
        "metodo_pago": original["metodo_pago"],
        "usuario_id": get_jwt_identity(),
        "detallada": original.get("detallada", False),
        "origen": "pos",
        "extemporanea": False,
        "venta_original_id": venta_id,
        "motivo_cancelacion": motivo,
        "cancelada_por": get_jwt_identity(),
        "cancelada_en": ahora,
        # el dia de la venta editada, NO hoy (ver `_instante`)
        "fecha_hora": _instante(fecha, secuencia),
    }

    reversion = journal.escribir_venta(
        {
            **comun,
            "id": str(
                uuid.uuid5(
                    _NAMESPACE_EDICION,
                    f"{venta_id}:editada_reversa:{secuencia}:{monto_nuevo}",
                )
            ),
            "total": -monto_vigente,
            "estado": "editada_reversa",
            "lineas": [_negar_linea(l) for l in lineas_vigentes],
        }
    )

    recaptura = journal.escribir_venta(
        {
            **comun,
            "id": str(
                uuid.uuid5(
                    _NAMESPACE_EDICION,
                    f"{venta_id}:editada:{secuencia}:{monto_nuevo}",
                )
            ),
            "total": monto_nuevo,
            "estado": "editada",
            "lineas": _escalar_lineas(lineas_vigentes, monto_vigente, monto_nuevo),
        }
    )

    return jsonify({"reversion": _a_json(reversion), "recaptura": _a_json(recaptura)}), 201


def _negar_linea(linea: dict) -> dict:
    """Misma linea con cantidad/subtotal/comision de signo contrario."""
    negada = dict(linea)
    negada["cantidad"] = -float(linea["cantidad"])
    negada["subtotal"] = -float(linea["subtotal"])
    if linea.get("monto_comision") is not None:
        negada["monto_comision"] = -float(linea["monto_comision"])
    return negada


def _escalar_lineas(lineas: list, monto_vigente: float, monto_nuevo: float) -> list:
    """
    Las lineas del importe vigente escaladas por `monto_nuevo / monto_vigente`,
    redondeando cada `subtotal` a 2 decimales y volcando el residuo en la
    ultima linea para que la suma sea EXACTA. `cantidad` y las claves de la
    linea (tipo, categoria, producto_id...) no cambian.
    """
    if not lineas:
        return []
    factor = monto_nuevo / monto_vigente
    escaladas = []
    for linea in lineas:
        nueva = dict(linea)
        nueva["subtotal"] = round(float(linea["subtotal"]) * factor, 2)
        nueva["precio_unitario"] = round(float(linea["precio_unitario"]) * factor, 2)
        if linea.get("monto_comision") is not None:
            nueva["monto_comision"] = round(float(linea["monto_comision"]) * factor, 2)
        escaladas.append(nueva)

    residuo = round(monto_nuevo - sum(l["subtotal"] for l in escaladas), 2)
    if residuo:
        escaladas[-1]["subtotal"] = round(escaladas[-1]["subtotal"] + residuo, 2)
    return escaladas


def _a_json(fila: dict) -> dict:
    """fecha_hora/creado_en/cancelada_en llegan como datetime; a texto ISO."""
    salida = dict(fila)
    for campo in ("fecha_hora", "creado_en", "cancelada_en"):
        valor = salida.get(campo)
        if isinstance(valor, (datetime.datetime, datetime.date)):
            salida[campo] = valor.isoformat()
    return salida
