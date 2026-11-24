"""
Endpoint de agregacion de ventas (#34).

    GET /api/agregaciones?granularidad=<dia|semana|mes|anio>&desde=YYYY-MM-DD&hasta=YYYY-MM-DD

Reemplaza a `registros/valores.py`, que leia la tabla legada, traia el
anio a memoria y calculaba las semanas del mes con `%W` y `round(...)`
-- fragil en bisiestos y meses que cruzan semana. Aqui el agrupado por
periodo lo hace BigQuery sobre `venta` (ver
acceso_datos/repositorios/agregaciones.py) y las semanas son ISO.

Responde una lista de buckets planos ordenados por `periodo_inicio`. Los
periodos del rango sin ninguna venta se devuelven igual, con `total = 0`,
`num_ventas = 0` y desgloses vacios: el frontend no tiene que adivinar
huecos.
"""

import calendar
import datetime

from flask import jsonify, request

import acceso_datos.repositorios.agregaciones as agregaciones_repo
import utilidades.utils as utils


def obtener_agregaciones():
    granularidad = request.args.get("granularidad", "")
    if granularidad not in agregaciones_repo.GRANULARIDADES:
        return (
            jsonify(
                error=(
                    "'granularidad' debe ser uno de: "
                    + ", ".join(agregaciones_repo.GRANULARIDADES)
                )
            ),
            400,
        )

    try:
        desde = datetime.date.fromisoformat(request.args.get("desde", ""))
        hasta = datetime.date.fromisoformat(request.args.get("hasta", ""))
    except ValueError:
        return jsonify(error="'desde' y 'hasta' deben tener formato YYYY-MM-DD"), 400

    if desde > hasta:
        return jsonify(error="'desde' no puede ser posterior a 'hasta'"), 400

    reales = {
        b["periodo_inicio"]: b
        for b in agregaciones_repo.agregar_por_periodo(granularidad, desde, hasta)
    }

    respuesta = []
    for inicio in _periodos(granularidad, desde, hasta):
        bucket = reales.get(inicio) or {
            "periodo_inicio": inicio,
            "total": 0,
            "num_ventas": 0,
            "desglose_categoria": [],
            "desglose_servicio": [],
            "desglose_metodo_pago": [],
        }
        fin = _fin_periodo(granularidad, inicio)
        respuesta.append(
            {
                "periodo_inicio": inicio.isoformat(),
                "periodo_fin": fin.isoformat(),
                "etiqueta": _etiqueta(granularidad, inicio, fin),
                "total": bucket["total"],
                "num_ventas": bucket["num_ventas"],
                "desglose_categoria": bucket["desglose_categoria"],
                "desglose_servicio": bucket["desglose_servicio"],
                "desglose_metodo_pago": bucket["desglose_metodo_pago"],
            }
        )

    return jsonify(respuesta)


# --------------------------------------------------------------- periodos

def _inicio_periodo(granularidad: str, fecha: datetime.date) -> datetime.date:
    if granularidad == "dia":
        return fecha
    if granularidad == "semana":
        return fecha - datetime.timedelta(days=fecha.weekday())  # lunes ISO
    if granularidad == "mes":
        return fecha.replace(day=1)
    return fecha.replace(month=1, day=1)  # anio


def _fin_periodo(granularidad: str, inicio: datetime.date) -> datetime.date:
    if granularidad == "dia":
        return inicio
    if granularidad == "semana":
        return inicio + datetime.timedelta(days=6)
    if granularidad == "mes":
        ultimo = calendar.monthrange(inicio.year, inicio.month)[1]
        return inicio.replace(day=ultimo)
    return inicio.replace(month=12, day=31)  # anio


def _siguiente(granularidad: str, inicio: datetime.date) -> datetime.date:
    if granularidad == "dia":
        return inicio + datetime.timedelta(days=1)
    if granularidad == "semana":
        return inicio + datetime.timedelta(days=7)
    if granularidad == "mes":
        return (inicio.replace(day=1) + datetime.timedelta(days=32)).replace(day=1)
    return inicio.replace(year=inicio.year + 1, month=1, day=1)


def _periodos(granularidad: str, desde: datetime.date, hasta: datetime.date):
    """Inicios de periodo que tocan [desde, hasta], en orden."""
    actual = _inicio_periodo(granularidad, desde)
    fin = _inicio_periodo(granularidad, hasta)
    while actual <= fin:
        yield actual
        actual = _siguiente(granularidad, actual)


# --------------------------------------------------------------- etiquetas

def _etiqueta(granularidad: str, inicio: datetime.date, fin: datetime.date) -> str:
    if granularidad == "dia":
        return f"{inicio.day} de {utils.obtenerMes(inicio.month)} de {inicio.year}"
    if granularidad == "semana":
        if (inicio.month, inicio.year) == (fin.month, fin.year):
            return (
                f"Semana del {inicio.day} al {fin.day} de "
                f"{utils.obtenerMes(inicio.month)} de {inicio.year}"
            )
        return (
            f"Semana del {inicio.day} de {utils.obtenerMes(inicio.month)} "
            f"al {fin.day} de {utils.obtenerMes(fin.month)} de {fin.year}"
        )
    if granularidad == "mes":
        mes = utils.obtenerMes(inicio.month)
        return f"{mes.capitalize()} de {inicio.year}"
    return str(inicio.year)  # anio
