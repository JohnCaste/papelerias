"""
Tests de ventas/cierres.py -- vistas de Flask, cierre local falseado.
"""

import datetime
import json

import pytest
from flask import Flask

import ventas.cierres as vista
from almacen_local import cierres


@pytest.fixture
def app():
    app = Flask(__name__)
    app.testing = True
    return app


def test_cerrar_dia_manual_sin_fecha_usa_hoy(app, monkeypatch):
    capturado = {}

    def falso_generar(fecha, generado_por):
        capturado["fecha"] = fecha
        capturado["generado_por"] = generado_por
        return {
            "id": "c1",
            "tipo": "dia",
            "fecha_inicio": fecha,
            "fecha_fin": fecha,
            "total": 0,
            "num_ventas": 0,
            "generado_por": generado_por,
            "estado": "cerrado",
            "sincronizado": False,
        }

    monkeypatch.setattr(cierres, "generar_cierre_dia", falso_generar)

    with app.test_request_context("/api/cierres/dia", method="POST", json={}):
        body, status = vista.cerrar_dia_manual()

    assert status == 201
    assert capturado["fecha"] == datetime.date.today()
    assert capturado["generado_por"] == "manual"


def test_cerrar_dia_manual_con_fecha_invalida_da_400(app):
    with app.test_request_context(
        "/api/cierres/dia", method="POST", json={"fecha": "no-es-fecha"}
    ):
        body, status = vista.cerrar_dia_manual()
    assert status == 400


def test_cerrar_dia_manual_serializa_fechas(app, monkeypatch):
    fecha = datetime.date(2026, 8, 31)
    monkeypatch.setattr(
        cierres,
        "generar_cierre_dia",
        lambda f, g: {
            "id": "c1",
            "fecha_inicio": fecha,
            "fecha_fin": fecha,
            "generado_en": datetime.datetime(2026, 8, 31, 20, 0, tzinfo=datetime.timezone.utc),
            "total": 0,
            "sincronizado": False,
        },
    )

    with app.test_request_context(
        "/api/cierres/dia", method="POST", json={"fecha": "2026-08-31"}
    ):
        respuesta, status = vista.cerrar_dia_manual()

    data = json.loads(respuesta.get_data(as_text=True))
    assert data["fecha_inicio"] == "2026-08-31"
    assert data["generado_en"] == "2026-08-31T20:00:00+00:00"


def test_obtener_estado_dia_abierto(app, monkeypatch):
    monkeypatch.setattr(cierres, "obtener_cierre_local", lambda fecha: None)

    with app.test_request_context("/api/cierres/dia"):
        respuesta = vista.obtener_estado_dia()

    data = json.loads(respuesta.get_data(as_text=True))
    assert data["cerrado"] is False
    assert data["cierre"] is None


def test_obtener_estado_dia_cerrado(app, monkeypatch):
    monkeypatch.setattr(
        cierres,
        "obtener_cierre_local",
        lambda fecha: {"id": "c1", "total": 100.0, "fecha_inicio": fecha},
    )

    with app.test_request_context("/api/cierres/dia?fecha=2026-08-31"):
        respuesta = vista.obtener_estado_dia()

    data = json.loads(respuesta.get_data(as_text=True))
    assert data["cerrado"] is True
    assert data["cierre"]["total"] == 100.0


def test_obtener_estado_dia_con_fecha_invalida_da_400(app):
    with app.test_request_context("/api/cierres/dia?fecha=no-es-fecha"):
        body, status = vista.obtener_estado_dia()
    assert status == 400


def test_obtener_estado_dia_hoy_incluye_gate_de_hora(app, monkeypatch):
    monkeypatch.setattr(cierres, "obtener_cierre_local", lambda fecha: None)
    monkeypatch.setattr(cierres, "es_antes_de_hora_cierre", lambda: True)

    with app.test_request_context("/api/cierres/dia"):
        respuesta = vista.obtener_estado_dia()

    data = json.loads(respuesta.get_data(as_text=True))
    assert data["antes_de_hora_cierre"] is True
    assert data["hora_cierre"] == "21:00"


def test_obtener_estado_dia_pasado_no_incluye_gate_de_hora(app, monkeypatch):
    monkeypatch.setattr(cierres, "obtener_cierre_local", lambda fecha: None)

    with app.test_request_context("/api/cierres/dia?fecha=2026-08-31"):
        respuesta = vista.obtener_estado_dia()

    data = json.loads(respuesta.get_data(as_text=True))
    assert "antes_de_hora_cierre" not in data


def test_regenerar_acta_de_ayer_da_409(app):
    ayer = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    with app.test_request_context("/api/cierres/dia/regenerar", method="POST", json={"fecha": ayer}):
        body, status = vista.regenerar_cierre_dia()
    assert status == 409


def test_regenerar_acta_de_hoy_sin_acta_previa_genera_la_primera(app, monkeypatch):
    llamadas = {}
    monkeypatch.setattr(cierres, "obtener_cierre_local", lambda fecha: None)

    def falso_generar(fecha, generado_por):
        llamadas["generar"] = generado_por
        return {"id": "c1", "fecha_inicio": fecha, "fecha_fin": fecha, "total": 0, "sincronizado": False}

    monkeypatch.setattr(cierres, "generar_cierre_dia", falso_generar)

    with app.test_request_context("/api/cierres/dia/regenerar", method="POST", json={}):
        respuesta, status = vista.regenerar_cierre_dia()

    assert status == 201
    assert llamadas["generar"] == "manual"


def test_regenerar_acta_de_hoy_con_acta_previa_regenera(app, monkeypatch):
    llamadas = {}
    monkeypatch.setattr(cierres, "obtener_cierre_local", lambda fecha: {"id": "viejo"})

    def falso_regenerar(fecha, generado_por):
        llamadas["regenerar"] = generado_por
        return {"id": "c2", "fecha_inicio": fecha, "fecha_fin": fecha, "total": 150.0, "sincronizado": False}

    monkeypatch.setattr(cierres, "regenerar_cierre_dia", falso_regenerar)

    with app.test_request_context("/api/cierres/dia/regenerar", method="POST", json={}):
        respuesta, status = vista.regenerar_cierre_dia()

    data = json.loads(respuesta.get_data(as_text=True))
    assert status == 201
    assert llamadas["regenerar"] == "regeneracion"
    assert data["total"] == 150.0
