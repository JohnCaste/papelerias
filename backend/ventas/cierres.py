"""
Endpoints de cierre de dia (#50).

Igual que la captura de ventas (#20), esto opera sobre el journal y el
cierre LOCALES -- nunca espera a BigQuery. Cerrar el dia funciona sin
internet, exactamente como capturar una venta.
"""

import datetime

from flask import jsonify, request

from almacen_local import cierres
from utilidades import zona_negocio


def _parsear_fecha(datos_o_args, *, default_hoy=True):
    """Lee 'fecha' (YYYY-MM-DD) del cuerpo/query. Devuelve (fecha, error_response)."""
    fecha_texto = datos_o_args.get("fecha")
    if fecha_texto:
        try:
            return datetime.date.fromisoformat(fecha_texto), None
        except ValueError:
            return None, (jsonify(error="'fecha' debe tener formato YYYY-MM-DD"), 400)
    if default_hoy:
        return zona_negocio.hoy(), None
    return None, None


def cerrar_dia_manual():
    """
    POST /api/cierres/dia -- "forzar cierre ahora" (#50/#54), disparado
    desde la pantalla por quien esta en el mostrador. Idempotente: si el
    dia ya estaba cerrado (por cualquier disparador), regresa el mismo
    acta sin duplicar. Un cierre forzado antes de la hora de cierre queda
    `provisional` (el campo viaja en la respuesta via `_a_json`).
    """
    datos = request.get_json(silent=True) or {}
    fecha, error = _parsear_fecha(datos)
    if error:
        return error

    cierre = cierres.generar_cierre_dia(fecha, "manual")
    return jsonify(_a_json(cierre)), 201


def regenerar_cierre_dia():
    """
    POST /api/cierres/dia/regenerar (#54) -- rehace el acta del dia en
    CURSO con los valores del journal al momento. Solo hoy: las actas de
    dias anteriores son historial inmutable (`409`).
    """
    datos = request.get_json(silent=True) or {}
    fecha, error = _parsear_fecha(datos)
    if error:
        return error

    if fecha != zona_negocio.hoy():
        return jsonify(error="Solo se puede regenerar el acta del día en curso"), 409

    if cierres.obtener_cierre_local(fecha) is None:
        cierre = cierres.generar_cierre_dia(fecha, "manual")
    else:
        cierre = cierres.regenerar_cierre_dia(fecha, "regeneracion")
    return jsonify(_a_json(cierre)), 201


def obtener_estado_dia():
    """
    GET /api/cierres/dia?fecha=YYYY-MM-DD -- estado del dia: cerrado
    (con su acta) o abierto. Por defecto, hoy.

    Cuando la fecha es hoy, agrega `antes_de_hora_cierre` y `hora_cierre`
    para que la pantalla VENDER decida el estado del boton de cierre sin
    depender del reloj del navegador (#54).
    """
    fecha, error = _parsear_fecha(request.args)
    if error:
        return error

    cierre = cierres.obtener_cierre_local(fecha)
    extra = {}
    if fecha == zona_negocio.hoy():
        extra["antes_de_hora_cierre"] = cierres.es_antes_de_hora_cierre()
        extra["hora_cierre"] = cierres.HORA_CIERRE_POR_DEFECTO.strftime("%H:%M")

    if cierre is None:
        return jsonify(fecha=fecha.isoformat(), cerrado=False, cierre=None, **extra)

    return jsonify(fecha=fecha.isoformat(), cerrado=True, cierre=_a_json(cierre), **extra)


def _a_json(cierre: dict) -> dict:
    """fecha_inicio/fecha_fin/generado_en pueden llegar como date/datetime real."""
    salida = dict(cierre)
    for campo in ("fecha_inicio", "fecha_fin", "generado_en"):
        valor = salida.get(campo)
        if isinstance(valor, (datetime.datetime, datetime.date)):
            salida[campo] = valor.isoformat()
    return salida
