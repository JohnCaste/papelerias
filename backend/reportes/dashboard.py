"""
Dashboard del dia (#35): el resumen que sustituye a mirar la hoja de
papel al cerrar.

    GET /api/dashboard/dia?fecha=YYYY-MM-DD   (por defecto, hoy)

Lee del JOURNAL LOCAL (#14), no de BigQuery: el dia en curso puede no
estar sincronizado todavia y aun asi tiene que cuadrar, y la pantalla
tiene que cargar sin internet igual que la captura y el cierre.

La comparacion con "el mismo dia de la semana pasada" tambien sale del
journal (`leer_dia(fecha - 7d)`), no de BigQuery, para no mezclar dos
fuentes que pueden discrepar mientras el sincronizador trabaja.
"""

import datetime

from flask import jsonify, request

from almacen_local import cierres, journal
from utilidades import zona_negocio
from ventas import cancelaciones, desglose

VENTANA_DIAS_SIN_CERRAR = cierres.DIAS_HACIA_ATRAS_PEREZOSO


def resumen_dia():
    fecha_texto = request.args.get("fecha")
    if fecha_texto:
        try:
            fecha = datetime.date.fromisoformat(fecha_texto)
        except ValueError:
            return jsonify(error="'fecha' debe tener formato YYYY-MM-DD"), 400
    else:
        fecha = zona_negocio.hoy()

    ventas = journal.leer_dia(fecha)
    # `total` y los desgloses suman TODAS las filas (ventas + reversiones
    # de #26): la cancelacion resta por neteo, sin filtrar por `estado`.
    # `num_ventas` y `ultimas_ventas`, en cambio, solo cuentan/listan las
    # ventas reales, marcando las canceladas.
    total = sum(float(v["total"]) for v in ventas)
    reales, canceladas_ids, editadas = cancelaciones.clasificar_ventas(ventas)

    return jsonify(
        {
            "fecha": fecha.isoformat(),
            "total": total,
            "num_ventas": len(reales),
            "desglose_categoria": desglose.por_categoria(ventas),
            "desglose_metodo_pago": desglose.por_metodo_pago(ventas),
            "detalle": _detalle(ventas, total),
            "comparacion_semana_anterior": _comparacion(fecha, total),
            "ultimas_ventas": _ultimas_ventas(reales, canceladas_ids, editadas),
            "estado_dia": _estado_dia(fecha),
            "dias_sin_cerrar": _dias_sin_cerrar(fecha),
        }
    )


def _detalle(ventas: list, total: float) -> dict:
    """% del DINERO capturado con lineas de producto (detallada = true)."""
    detallado = sum(float(v["total"]) for v in ventas if v.get("detallada"))
    return {
        "monto_detallado": detallado,
        "monto_total": total,
        "porcentaje": round(detallado / total * 100) if total else 0,
    }


def _comparacion(fecha: datetime.date, total_hoy: float) -> dict:
    fecha_ant = fecha - datetime.timedelta(days=7)
    ventas_ant = journal.leer_dia(fecha_ant)
    total_ant = sum(float(v["total"]) for v in ventas_ant)
    return {
        "fecha": fecha_ant.isoformat(),
        "total": total_ant,
        "num_ventas": len(ventas_ant),
        "delta_total": total_hoy - total_ant,
        "delta_pct": (
            round((total_hoy - total_ant) / total_ant * 100) if total_ant else None
        ),
    }


def _hora_local(fecha_hora) -> str:
    """`fecha_hora` llega como texto ISO desde journal.leer_dia (releido de disco)."""
    return zona_negocio.a_hora_negocio(fecha_hora).strftime("%H:%M")


def _ultimas_ventas(reales: list, canceladas_ids: set, editadas: dict) -> list:
    # journal.leer_dia las devuelve ascendentes por fecha_hora; aqui se
    # quieren de la mas reciente a la mas antigua. `reales` ya excluye las
    # filas de reversion de #26 y las de edicion de monto; una venta
    # cancelada o editada se muestra marcada, sin desaparecer del historial.
    # Precedencia: cancelada > editada.
    salida = []
    for v in reversed(reales):
        cancelada = v["id"] in canceladas_ids
        editada = not cancelada and v["id"] in editadas
        if cancelada:
            estado = "cancelada"
        elif editada:
            estado = "editada"
        else:
            estado = v.get("estado_local")
        salida.append(
            {
                "id": v["id"],
                "hora": _hora_local(v["fecha_hora"]),
                "total": editadas[v["id"]] if editada else float(v["total"]),
                "metodo_pago": v.get("metodo_pago"),
                "vendedor": v.get("vendedor"),
                "detallada": bool(v.get("detallada")),
                "estado": estado,
                "cancelable": not cancelada,
                "editable": not cancelada,
            }
        )
    return salida


def _estado_dia(fecha: datetime.date) -> dict:
    cierre = cierres.obtener_cierre_local(fecha)
    if cierre is None:
        return {"cerrado": False, "cerrado_en": None}
    cerrado_en = cierre.get("generado_en")
    if isinstance(cerrado_en, (datetime.datetime, datetime.date)):
        cerrado_en = cerrado_en.isoformat()
    return {"cerrado": True, "cerrado_en": cerrado_en}


def _dias_sin_cerrar(fecha: datetime.date) -> list:
    dias = (fecha - datetime.timedelta(days=d) for d in range(1, VENTANA_DIAS_SIN_CERRAR + 1))
    return [d.isoformat() for d in dias if not cierres.ya_cerrado(d)]
