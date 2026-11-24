"""
Tests de reportes/agregaciones.py (#34) -- vista de Flask, repositorio falseado.
"""

import datetime
import json

import pytest
from flask import Flask

import reportes.agregaciones as vista
import acceso_datos.repositorios.agregaciones as repo


@pytest.fixture
def app():
    app = Flask(__name__)
    app.testing = True
    return app


def _pedir(app, query, monkeypatch, buckets=None):
    monkeypatch.setattr(
        repo, "agregar_por_periodo", lambda g, d, h: list(buckets or [])
    )
    with app.test_request_context(f"/api/agregaciones?{query}"):
        return vista.obtener_agregaciones()


def _json(resp):
    return json.loads(resp.get_data(as_text=True))


# --------------------------------------------------------------- validacion

def test_granularidad_invalida_da_400(app, monkeypatch):
    resp = _pedir(app, "granularidad=quincena&desde=2026-01-01&hasta=2026-01-31", monkeypatch)
    _, status = resp
    assert status == 400


def test_fechas_invalidas_dan_400(app, monkeypatch):
    resp = _pedir(app, "granularidad=dia&desde=ayer&hasta=2026-01-31", monkeypatch)
    assert resp[1] == 400


def test_rango_invertido_da_400(app, monkeypatch):
    resp = _pedir(app, "granularidad=dia&desde=2026-05-01&hasta=2026-04-01", monkeypatch)
    assert resp[1] == 400


def test_rango_invertido_no_llama_al_repositorio(app, monkeypatch):
    llamado = {"n": 0}

    def espia(*a, **k):
        llamado["n"] += 1
        return []

    monkeypatch.setattr(repo, "agregar_por_periodo", espia)
    with app.test_request_context(
        "/api/agregaciones?granularidad=dia&desde=2026-05-01&hasta=2026-04-01"
    ):
        vista.obtener_agregaciones()
    assert llamado["n"] == 0


# --------------------------------------------------------------- relleno de huecos

def test_rellena_periodos_vacios_del_rango(app, monkeypatch):
    resp = _pedir(
        app, "granularidad=dia&desde=2026-02-01&hasta=2026-02-05", monkeypatch, buckets=[]
    )
    data = _json(resp)
    assert [b["periodo_inicio"] for b in data] == [
        "2026-02-01",
        "2026-02-02",
        "2026-02-03",
        "2026-02-04",
        "2026-02-05",
    ]
    assert all(b["total"] == 0 and b["num_ventas"] == 0 for b in data)
    assert all(b["desglose_categoria"] == [] for b in data)


def test_mezcla_buckets_reales_con_huecos(app, monkeypatch):
    buckets = [
        {
            "periodo_inicio": datetime.date(2026, 2, 3),
            "total": 120,
            "num_ventas": 3,
            "desglose_categoria": [{"clave": "copias", "monto": 120}],
            "desglose_servicio": [],
            "desglose_metodo_pago": [{"clave": "efectivo", "monto": 120}],
        }
    ]
    resp = _pedir(
        app, "granularidad=dia&desde=2026-02-01&hasta=2026-02-04", monkeypatch, buckets=buckets
    )
    data = _json(resp)
    dia3 = next(b for b in data if b["periodo_inicio"] == "2026-02-03")
    assert dia3["total"] == 120
    assert dia3["desglose_metodo_pago"] == [{"clave": "efectivo", "monto": 120}]
    assert next(b for b in data if b["periodo_inicio"] == "2026-02-01")["total"] == 0


# --------------------------------------------------------------- forma de salida

def test_cada_bucket_trae_etiqueta_y_periodo_fin(app, monkeypatch):
    resp = _pedir(app, "granularidad=mes&desde=2026-01-01&hasta=2026-03-31", monkeypatch)
    data = _json(resp)
    assert [b["periodo_inicio"] for b in data] == ["2026-01-01", "2026-02-01", "2026-03-01"]
    assert [b["periodo_fin"] for b in data] == ["2026-01-31", "2026-02-28", "2026-03-31"]
    assert data[0]["etiqueta"] == "Enero de 2026"


def test_orden_ascendente_por_periodo(app, monkeypatch):
    resp = _pedir(app, "granularidad=anio&desde=2024-06-01&hasta=2026-01-01", monkeypatch)
    data = _json(resp)
    assert [b["periodo_inicio"] for b in data] == ["2024-01-01", "2025-01-01", "2026-01-01"]
    assert [b["etiqueta"] for b in data] == ["2024", "2025", "2026"]


def test_json_valido_con_apostrofe_en_los_datos(app, monkeypatch):
    """Regresion del hack viejo str(...).replace(\"'\", '\"') de valores.py."""
    buckets = [
        {
            "periodo_inicio": datetime.date(2026, 2, 3),
            "total": 50,
            "num_ventas": 1,
            "desglose_categoria": [],
            "desglose_servicio": [{"clave": "Copia 'especial'", "monto": 50}],
            "desglose_metodo_pago": [{"clave": "efectivo", "monto": 50}],
        }
    ]
    resp = _pedir(
        app, "granularidad=dia&desde=2026-02-03&hasta=2026-02-03", monkeypatch, buckets=buckets
    )
    data = _json(resp)  # si el JSON fuera invalido, esto lanzaria
    assert data[0]["desglose_servicio"][0]["clave"] == "Copia 'especial'"


# --------------------------------------------------------------- semanas ISO

def test_semanas_iso_lunes_a_domingo(app, monkeypatch):
    resp = _pedir(app, "granularidad=semana&desde=2026-08-01&hasta=2026-08-31", monkeypatch)
    data = _json(resp)
    for b in data:
        inicio = datetime.date.fromisoformat(b["periodo_inicio"])
        fin = datetime.date.fromisoformat(b["periodo_fin"])
        assert inicio.weekday() == 0  # lunes
        assert fin.weekday() == 6  # domingo
        assert (fin - inicio).days == 6
    # sin huecos entre semanas consecutivas
    for a, b in zip(data, data[1:]):
        fin_a = datetime.date.fromisoformat(a["periodo_fin"])
        ini_b = datetime.date.fromisoformat(b["periodo_inicio"])
        assert ini_b == fin_a + datetime.timedelta(days=1)


def test_semanas_iso_en_anio_bisiesto(app, monkeypatch):
    # 2028 es bisiesto: el bug original de valores.py se rompia aqui.
    resp = _pedir(app, "granularidad=semana&desde=2028-02-01&hasta=2028-02-29", monkeypatch)
    data = _json(resp)
    ultimo_dia = datetime.date(2028, 2, 29)
    ultimo_bucket = data[-1]
    inicio = datetime.date.fromisoformat(ultimo_bucket["periodo_inicio"])
    fin = datetime.date.fromisoformat(ultimo_bucket["periodo_fin"])
    assert inicio <= ultimo_dia <= fin


def test_etiqueta_de_semana_que_cruza_mes(app, monkeypatch):
    # semana que empieza en un mes y termina en otro
    resp = _pedir(app, "granularidad=semana&desde=2026-01-28&hasta=2026-02-03", monkeypatch)
    data = _json(resp)
    etiqueta = data[0]["etiqueta"]
    assert "enero" in etiqueta and "febrero" in etiqueta
