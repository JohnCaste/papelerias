"""
Agregacion de ventas por periodo (#34). Solo lectura sobre `venta`.

La regla de #8 es que solo se almacena la venta: dia / semana / mes / anio
son consultas agregadas, nunca tablas propias. Este repositorio arma esas
consultas.

Decisiones que valen para las cuatro granularidades:

  - El periodo se corta con la fecha CIVIL de `fecha_hora` en
    `America/Mexico_City`, no en UTC -- una venta de las 11pm cuenta en el
    dia local correcto, igual que el cierre de dia (#50). Las semanas son
    ISO (lunes-domingo).

  - El rango se filtra por `fecha_hora >= TIMESTAMP(@desde, tz)` y
    `< TIMESTAMP(@hasta + 1 dia, tz)`. Es exacto (el instante UTC de la
    medianoche local) y ademas deja que BigQuery pode la particion por
    `fecha_hora` en vez de escanear toda la tabla.

  - Cancelaciones (#26): se suma `total` de TODAS las filas del rango. La
    fila de reversion trae `total` (y `subtotal` de cada linea) en
    negativo, asi que netea sola. `num_ventas` cuenta solo filas con
    `venta_original_id IS NULL` para no contar una cancelacion como venta.

  - Los desgloses por categoria y por servicio suman `lineas.subtotal`
    agrupando por `UNNEST(lineas)`, no el `total` de la venta contra su
    primera linea (atajo que usa el cierre local, incorrecto con varias
    lineas). El desglose por metodo de pago suma `venta.total`.
"""

import datetime

from acceso_datos.consultas import ejecutar_query
from esquema.tablas import DATASET

TABLA_VENTA = f"{DATASET}.venta"
TABLA_SERVICIO = f"{DATASET}.servicio"

ZONA = "America/Mexico_City"

GRANULARIDADES = ("dia", "semana", "mes", "anio")

# Expresion que reduce `fecha_hora` a la fecha de inicio del periodo, en
# hora local. `{col}` es el alias de la columna TIMESTAMP en cada query.
_PERIODO_SQL = {
    "dia": f"DATE({{col}}, '{ZONA}')",
    "semana": f"DATE_TRUNC(DATE({{col}}, '{ZONA}'), WEEK(MONDAY))",
    "mes": f"DATE_TRUNC(DATE({{col}}, '{ZONA}'), MONTH)",
    "anio": f"DATE_TRUNC(DATE({{col}}, '{ZONA}'), YEAR)",
}

# Filtro de rango comun a todas las consultas. Exacto y podable por particion.
_RANGO_SQL = (
    "{col} >= TIMESTAMP(@desde, '{zona}') "
    "AND {col} < TIMESTAMP(DATE_ADD(@hasta, INTERVAL 1 DAY), '{zona}')"
).format(col="{col}", zona=ZONA)


def _valores(desde: datetime.date, hasta: datetime.date):
    return {"desde": desde, "hasta": hasta}, {"desde": "DATE", "hasta": "DATE"}


def _num(valor):
    """NUMERIC de BigQuery llega como Decimal; se pasa a int/float para JSON."""
    if valor is None:
        return 0
    numero = float(valor)
    return int(numero) if numero.is_integer() else numero


def _totales(periodo_expr, valores, tipos):
    sql = f"""
        SELECT
            {periodo_expr.format(col="fecha_hora")} AS periodo,
            SUM(total) AS total,
            COUNTIF(venta_original_id IS NULL) AS num_ventas
        FROM `{TABLA_VENTA}`
        WHERE {_RANGO_SQL.format(col="fecha_hora")}
        GROUP BY periodo
    """
    return ejecutar_query(sql, valores, tipos)


def _por_metodo_pago(periodo_expr, valores, tipos):
    sql = f"""
        SELECT
            {periodo_expr.format(col="fecha_hora")} AS periodo,
            metodo_pago AS clave,
            SUM(total) AS monto
        FROM `{TABLA_VENTA}`
        WHERE {_RANGO_SQL.format(col="fecha_hora")}
        GROUP BY periodo, clave
    """
    return ejecutar_query(sql, valores, tipos)


def _por_categoria(periodo_expr, valores, tipos):
    sql = f"""
        SELECT
            {periodo_expr.format(col="v.fecha_hora")} AS periodo,
            l.categoria AS clave,
            SUM(l.subtotal) AS monto
        FROM `{TABLA_VENTA}` v, UNNEST(v.lineas) l
        WHERE {_RANGO_SQL.format(col="v.fecha_hora")}
            AND l.tipo = 'categoria'
        GROUP BY periodo, clave
    """
    return ejecutar_query(sql, valores, tipos)


def _por_servicio(periodo_expr, valores, tipos):
    sql = f"""
        SELECT
            {periodo_expr.format(col="v.fecha_hora")} AS periodo,
            COALESCE(s.nombre, l.servicio_id) AS clave,
            SUM(l.subtotal) AS monto
        FROM `{TABLA_VENTA}` v, UNNEST(v.lineas) l
        LEFT JOIN `{TABLA_SERVICIO}` s ON s.id = l.servicio_id
        WHERE {_RANGO_SQL.format(col="v.fecha_hora")}
            AND l.tipo = 'servicio'
        GROUP BY periodo, clave
    """
    return ejecutar_query(sql, valores, tipos)


def _plegar_desglose(filas, destino, campo):
    """Agrega [{clave, monto}] al bucket `destino[periodo][campo]`."""
    for fila in filas:
        bucket = destino.get(fila["periodo"])
        if bucket is None:
            continue
        bucket[campo].append({"clave": fila["clave"], "monto": _num(fila["monto"])})


def agregar_por_periodo(granularidad: str, desde: datetime.date, hasta: datetime.date):
    """
    Devuelve una lista de buckets con datos reales (los periodos sin
    ventas NO aparecen; el endpoint rellena los huecos). Cada bucket:
    {periodo_inicio: date, total, num_ventas,
     desglose_categoria, desglose_servicio, desglose_metodo_pago}.

    Lanza ValueError si `granularidad` no es una de GRANULARIDADES.
    """
    if granularidad not in GRANULARIDADES:
        raise ValueError(
            f"granularidad invalida: {granularidad!r}. Validas: {', '.join(GRANULARIDADES)}"
        )

    periodo_expr = _PERIODO_SQL[granularidad]
    valores, tipos = _valores(desde, hasta)

    buckets: dict[datetime.date, dict] = {}
    for fila in _totales(periodo_expr, valores, tipos):
        buckets[fila["periodo"]] = {
            "periodo_inicio": fila["periodo"],
            "total": _num(fila["total"]),
            "num_ventas": int(fila["num_ventas"] or 0),
            "desglose_categoria": [],
            "desglose_servicio": [],
            "desglose_metodo_pago": [],
        }

    _plegar_desglose(
        _por_categoria(periodo_expr, valores, tipos), buckets, "desglose_categoria"
    )
    _plegar_desglose(
        _por_servicio(periodo_expr, valores, tipos), buckets, "desglose_servicio"
    )
    _plegar_desglose(
        _por_metodo_pago(periodo_expr, valores, tipos), buckets, "desglose_metodo_pago"
    )

    return [buckets[periodo] for periodo in sorted(buckets)]
