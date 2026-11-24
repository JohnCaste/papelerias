"""
Tests de reportes/dashboard.py (#35) -- vista de Flask, journal falseado.
"""

import datetime
import json

import pytest
from flask import Flask

import reportes.dashboard as vista
from almacen_local import cierres, journal
from utilidades import categorias


def _con_monto(desglose):
    """
    {clave: monto} dejando fuera las categorias en cero: el desglose
    devuelve SIEMPRE la lista canonica completa (utilidades/categorias.py),
    y estos tests solo comprueban las que tuvieron venta.
    """
    return {d["clave"]: d["monto"] for d in desglose if d["monto"]}


@pytest.fixture
def app():
    app = Flask(__name__)
    app.testing = True
    return app


@pytest.fixture(autouse=True)
def _sin_cierres(monkeypatch):
    """Por defecto: nada cerrado. Cada test que lo necesite lo sobreescribe."""
    monkeypatch.setattr(cierres, "obtener_cierre_local", lambda *a, **k: None)
    monkeypatch.setattr(cierres, "ya_cerrado", lambda *a, **k: True)  # sin "dias sin cerrar"


def _venta(hora, total, metodo="efectivo", detallada=False, categoria="dulces", id_="v",
           vendedor="Ana"):
    return {
        "id": id_,
        "fecha_hora": datetime.datetime(2026, 9, 1, hora, 0, tzinfo=datetime.timezone.utc).isoformat(),
        "total": total,
        "metodo_pago": metodo,
        "vendedor": vendedor,
        "detallada": detallada,
        "estado_local": "pendiente",
        "lineas": [
            {"tipo": "categoria", "categoria": categoria, "cantidad": 1,
             "precio_unitario": total, "subtotal": total}
        ],
    }


def _pedir(app, monkeypatch, query="", dia=None, semana_pasada=None):
    def falso_leer_dia(fecha, carpeta=None):
        hoy = datetime.date(2026, 9, 1)
        if fecha == hoy:
            return list(dia or [])
        if fecha == hoy - datetime.timedelta(days=7):
            return list(semana_pasada or [])
        return []

    monkeypatch.setattr(journal, "leer_dia", falso_leer_dia)
    with app.test_request_context(f"/api/dashboard/dia?{query}"):
        return vista.resumen_dia()


def _json(resp):
    return json.loads(resp.get_data(as_text=True))


# --------------------------------------------------------------- validacion / vacio

def test_fecha_invalida_da_400(app, monkeypatch):
    resp = _pedir(app, monkeypatch, query="fecha=13-2026")
    assert resp[1] == 400


def test_dia_vacio(app, monkeypatch):
    resp = _pedir(app, monkeypatch, query="fecha=2026-09-01", dia=[])
    data = _json(resp)
    assert data["total"] == 0
    assert data["num_ventas"] == 0
    # El desglose trae SIEMPRE la lista canonica completa, en cero.
    assert {d["monto"] for d in data["desglose_categoria"]} == {0}
    assert [d["clave"] for d in data["desglose_categoria"]] == list(categorias.CLAVES)
    assert data["ultimas_ventas"] == []
    assert data["detalle"]["porcentaje"] == 0


# --------------------------------------------------------------- totales y desglose

def test_totales_y_desglose(app, monkeypatch):
    dia = [
        _venta(9, 100, metodo="efectivo", categoria="copias", id_="a"),
        _venta(10, 200, metodo="tarjeta", categoria="dulces", id_="b"),
        _venta(11, 50, metodo="efectivo", categoria="copias", id_="c"),
    ]
    data = _json(_pedir(app, monkeypatch, query="fecha=2026-09-01", dia=dia))

    assert data["total"] == 350
    assert data["num_ventas"] == 3
    cat = _con_monto(data["desglose_categoria"])
    assert cat == {"copias": 150, "dulces": 200}
    mp = {d["clave"]: d["monto"] for d in data["desglose_metodo_pago"]}
    assert mp == {"efectivo": 150, "tarjeta": 200}
    assert sum(d["monto"] for d in data["desglose_metodo_pago"]) == data["total"]


def test_desglose_reparte_venta_multi_categoria(app, monkeypatch):
    venta = {
        "id": "x",
        "fecha_hora": datetime.datetime(2026, 9, 1, 12, tzinfo=datetime.timezone.utc).isoformat(),
        "total": 50,
        "metodo_pago": "efectivo",
        "detallada": False,
        "estado_local": "enviada",
        "lineas": [
            {"tipo": "categoria", "categoria": "copias", "cantidad": 1, "precio_unitario": 30, "subtotal": 30},
            {"tipo": "categoria", "categoria": "dulces", "cantidad": 1, "precio_unitario": 20, "subtotal": 20},
        ],
    }
    data = _json(_pedir(app, monkeypatch, query="fecha=2026-09-01", dia=[venta]))
    cat = _con_monto(data["desglose_categoria"])
    assert cat == {"copias": 30, "dulces": 20}


# --------------------------------------------------------------- % detalle

def test_porcentaje_capturado_con_detalle(app, monkeypatch):
    dia = [
        _venta(9, 620, detallada=True, id_="a"),
        _venta(10, 270, detallada=False, id_="b"),
    ]
    data = _json(_pedir(app, monkeypatch, query="fecha=2026-09-01", dia=dia))
    assert data["detalle"] == {"monto_detallado": 620, "monto_total": 890, "porcentaje": 70}


def test_porcentaje_cero_sin_ventas_detalladas(app, monkeypatch):
    dia = [_venta(9, 100, detallada=False)]
    data = _json(_pedir(app, monkeypatch, query="fecha=2026-09-01", dia=dia))
    assert data["detalle"]["porcentaje"] == 0


# --------------------------------------------------------------- comparacion semana anterior

def test_comparacion_con_datos(app, monkeypatch):
    dia = [_venta(9, 1200, id_="a")]
    semana = [_venta(9, 1000, id_="p")]
    data = _json(_pedir(app, monkeypatch, query="fecha=2026-09-01", dia=dia, semana_pasada=semana))
    comp = data["comparacion_semana_anterior"]
    assert comp["fecha"] == "2026-08-25"
    assert comp["total"] == 1000
    assert comp["delta_total"] == 200
    assert comp["delta_pct"] == 20


def test_comparacion_sin_datos(app, monkeypatch):
    dia = [_venta(9, 500, id_="a")]
    data = _json(_pedir(app, monkeypatch, query="fecha=2026-09-01", dia=dia, semana_pasada=[]))
    comp = data["comparacion_semana_anterior"]
    assert comp["total"] == 0
    assert comp["num_ventas"] == 0
    assert comp["delta_pct"] is None


# --------------------------------------------------------------- ultimas ventas

def test_ultimas_ventas_mas_reciente_primero(app, monkeypatch):
    dia = [
        _venta(9, 10, id_="temprano"),
        _venta(18, 20, id_="tarde"),
    ]
    data = _json(_pedir(app, monkeypatch, query="fecha=2026-09-01", dia=dia))
    ids = [v["id"] for v in data["ultimas_ventas"]]
    assert ids == ["tarde", "temprano"]
    v = data["ultimas_ventas"][0]
    assert set(v) == {
        "id", "hora", "total", "metodo_pago", "vendedor", "detallada", "estado",
        "cancelable", "editable",
    }
    assert v["vendedor"] == "Ana"
    assert v["estado"] == "pendiente"
    assert v["cancelable"] is True
    # 18:00 UTC -> 12:00 hora del negocio (UTC-6)
    assert v["hora"] == "12:00"


def _reversion(hora, total, original_id, estado="cancelada", id_="r"):
    fila = _venta(hora, total, id_=id_)
    fila["venta_original_id"] = original_id
    fila["estado"] = estado
    fila["lineas"][0]["subtotal"] = total
    return fila


def test_venta_cancelada_netea_el_total_y_se_lista_marcada(app, monkeypatch):
    dia = [
        _venta(9, 100, id_="v1"),
        _reversion(10, -100, "v1", id_="v1-rev"),
    ]
    data = _json(_pedir(app, monkeypatch, query="fecha=2026-09-01", dia=dia))

    # neteo: el total baja a 0, pero num_ventas cuenta solo la venta real
    assert data["total"] == 0
    assert data["num_ventas"] == 1

    # la reversion no se lista como venta; la original aparece cancelada
    ids = [v["id"] for v in data["ultimas_ventas"]]
    assert ids == ["v1"]
    assert data["ultimas_ventas"][0]["estado"] == "cancelada"
    assert data["ultimas_ventas"][0]["cancelable"] is False


def test_devolucion_parcial_no_marca_la_venta_como_cancelada(app, monkeypatch):
    dia = [
        _venta(9, 100, id_="v1"),
        _reversion(10, -40, "v1", estado="devolucion_parcial", id_="v1-rev"),
    ]
    data = _json(_pedir(app, monkeypatch, query="fecha=2026-09-01", dia=dia))

    assert data["total"] == 60
    assert data["num_ventas"] == 1
    assert data["ultimas_ventas"][0]["estado"] == "pendiente"
    assert data["ultimas_ventas"][0]["cancelable"] is True


# --------------------------------------------------------------- estado de cierre

def test_estado_dia_cerrado(app, monkeypatch):
    monkeypatch.setattr(
        cierres, "obtener_cierre_local",
        lambda *a, **k: {"generado_en": "2026-09-01T20:00:00+00:00"},
    )
    data = _json(_pedir(app, monkeypatch, query="fecha=2026-09-01", dia=[]))
    assert data["estado_dia"] == {"cerrado": True, "cerrado_en": "2026-09-01T20:00:00+00:00"}


def test_dias_sin_cerrar_lista_solo_los_no_cerrados(app, monkeypatch):
    antier = datetime.date(2026, 8, 30)
    monkeypatch.setattr(cierres, "ya_cerrado", lambda f, *a, **k: f != antier)

    data = _json(_pedir(app, monkeypatch, query="fecha=2026-09-01", dia=[]))
    assert data["dias_sin_cerrar"] == ["2026-08-30"]
