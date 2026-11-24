"""
Tests de acceso_datos/repositorios/agregaciones.py (#34) -- sin BigQuery.

Se parchea `ejecutar_query` del modulo para capturar el SQL generado y
devolver filas de prueba.
"""

import datetime

import pytest

import acceso_datos.repositorios.agregaciones as repo

DESDE = datetime.date(2026, 2, 2)
HASTA = datetime.date(2026, 3, 1)


@pytest.fixture
def sqls(monkeypatch):
    """Captura todos los SQL ejecutados; devuelve [] para cada consulta."""
    capturados = []

    def falso(sql, valores=None, tipos=None):
        capturados.append({"sql": sql, "valores": valores, "tipos": tipos})
        return []

    monkeypatch.setattr(repo, "ejecutar_query", falso)
    return capturados


def test_granularidad_invalida_lanza():
    with pytest.raises(ValueError):
        repo.agregar_por_periodo("quincena", DESDE, HASTA)


def test_usa_la_zona_horaria_del_negocio(sqls):
    repo.agregar_por_periodo("dia", DESDE, HASTA)
    for consulta in sqls:
        assert "America/Mexico_City" in consulta["sql"]


@pytest.mark.parametrize(
    "granularidad, fragmento",
    [
        ("dia", "DATE(fecha_hora, 'America/Mexico_City') AS periodo"),
        ("semana", "DATE_TRUNC(DATE(fecha_hora, 'America/Mexico_City'), WEEK(MONDAY))"),
        ("mes", "DATE_TRUNC(DATE(fecha_hora, 'America/Mexico_City'), MONTH)"),
        ("anio", "DATE_TRUNC(DATE(fecha_hora, 'America/Mexico_City'), YEAR)"),
    ],
)
def test_expresion_de_periodo_por_granularidad(sqls, granularidad, fragmento):
    repo.agregar_por_periodo(granularidad, DESDE, HASTA)
    assert any(fragmento in c["sql"] for c in sqls)


def test_filtro_de_rango_es_podable_por_particion(sqls):
    repo.agregar_por_periodo("mes", DESDE, HASTA)
    consulta = sqls[0]
    # Rango exacto sobre la columna de particion, no un DATE() envolviendo fecha_hora.
    assert "fecha_hora >= TIMESTAMP(@desde, 'America/Mexico_City')" in consulta["sql"]
    assert "DATE_ADD(@hasta, INTERVAL 1 DAY)" in consulta["sql"]
    assert consulta["valores"] == {"desde": DESDE, "hasta": HASTA}
    assert consulta["tipos"] == {"desde": "DATE", "hasta": "DATE"}


def test_desglose_categoria_suma_subtotal_de_lineas(sqls):
    repo.agregar_por_periodo("dia", DESDE, HASTA)
    sql_categoria = next(c["sql"] for c in sqls if "l.tipo = 'categoria'" in c["sql"])
    assert "UNNEST(v.lineas) l" in sql_categoria
    assert "SUM(l.subtotal)" in sql_categoria


def test_desglose_servicio_resuelve_nombre(sqls):
    repo.agregar_por_periodo("dia", DESDE, HASTA)
    sql_servicio = next(c["sql"] for c in sqls if "l.tipo = 'servicio'" in c["sql"])
    assert "LEFT JOIN" in sql_servicio and "servicio" in sql_servicio
    assert "COALESCE(s.nombre, l.servicio_id)" in sql_servicio


def test_totales_no_filtran_por_estado(sqls):
    repo.agregar_por_periodo("dia", DESDE, HASTA)
    sql_totales = next(c["sql"] for c in sqls if "COUNTIF(venta_original_id IS NULL)" in c["sql"])
    assert "SUM(total)" in sql_totales
    assert "estado" not in sql_totales


def test_arma_buckets_y_pliega_desgloses(monkeypatch):
    p1 = datetime.date(2026, 2, 2)
    p2 = datetime.date(2026, 2, 9)

    respuestas = {
        "num_ventas": [
            {"periodo": p1, "total": 100, "num_ventas": 2},
            {"periodo": p2, "total": 50, "num_ventas": 1},
        ],
        "'categoria'": [
            {"periodo": p1, "clave": "copias", "monto": 30},
            {"periodo": p1, "clave": "dulces", "monto": 70},
        ],
        "'servicio'": [{"periodo": p2, "clave": "Copia B/N", "monto": 50}],
        "metodo_pago AS clave": [
            {"periodo": p1, "clave": "efectivo", "monto": 100},
            {"periodo": p2, "clave": "tarjeta", "monto": 50},
        ],
    }

    def falso(sql, valores=None, tipos=None):
        for marca, filas in respuestas.items():
            if marca in sql:
                return filas
        return []

    monkeypatch.setattr(repo, "ejecutar_query", falso)

    buckets = repo.agregar_por_periodo("semana", DESDE, HASTA)

    assert [b["periodo_inicio"] for b in buckets] == [p1, p2]
    assert buckets[0]["total"] == 100
    assert buckets[0]["num_ventas"] == 2
    assert {d["clave"] for d in buckets[0]["desglose_categoria"]} == {"copias", "dulces"}
    assert buckets[1]["desglose_servicio"] == [{"clave": "Copia B/N", "monto": 50}]
    assert buckets[0]["desglose_metodo_pago"] == [{"clave": "efectivo", "monto": 100}]


def test_num_convierte_decimal_a_numero():
    import decimal

    assert repo._num(decimal.Decimal("100")) == 100
    assert repo._num(decimal.Decimal("100.50")) == 100.5
    assert repo._num(None) == 0
