"""
Tests de ventas/ediciones.py (editar-ventas) -- vista de Flask con el
journal falseado. Editar el monto es DOS registros nuevos (reversion del
importe vigente + recaptura con el monto nuevo): nunca toca ni borra la
fila original.
"""

import datetime
import json

import pytest
from flask import Flask

import ventas.ediciones as vista
from almacen_local import journal


@pytest.fixture
def app():
    app = Flask(__name__)
    app.testing = True
    return app


def _venta(id_="v1", total=100.0, detallada=False, lineas=None, **extra):
    fila = {
        "id": id_,
        "fecha_hora": "2026-09-01T10:00:00+00:00",
        "total": total,
        "metodo_pago": "efectivo",
        "detallada": detallada,
        "estado": "activa",
        "estado_local": "pendiente",
        "venta_original_id": None,
        "lineas": lineas
        or [
            {
                "tipo": "categoria",
                "categoria": "dulces",
                "cantidad": 1.0,
                "precio_unitario": 100.0,
                "subtotal": 100.0,
                "monto_comision": None,
            }
        ],
    }
    fila.update(extra)
    return fila


def _dos_lineas(total=100.0):
    return _venta(
        total=total,
        lineas=[
            {
                "tipo": "categoria",
                "categoria": "dulces",
                "cantidad": 1.0,
                "precio_unitario": 60.0,
                "subtotal": 60.0,
                "monto_comision": None,
            },
            {
                "tipo": "categoria",
                "categoria": "copias",
                "cantidad": 1.0,
                "precio_unitario": 40.0,
                "subtotal": 40.0,
                "monto_comision": None,
            },
        ],
    )


@pytest.fixture
def editar(app, monkeypatch):
    """
    Devuelve `llamar(venta_id, body, dia=[...])` que ejecuta la vista y
    regresa `(status, body_json, escritos)` -- `escritos` es la lista de
    filas que la vista mando a `journal.escribir_venta`, en orden.
    """

    def hacer_llamada(venta_id, body, dia="__DEFAULT__"):
        journal_dia = [_venta(id_=venta_id)] if dia == "__DEFAULT__" else dia
        escritos = []

        def falso_leer_dia(fecha, carpeta=None):
            return journal_dia

        def falso_escribir(datos, carpeta=None):
            fila = dict(datos)
            escritos.append(fila)
            journal_dia.append({**fila, "estado_local": "pendiente"})
            return {**fila, "creado_en": datetime.datetime.now(datetime.timezone.utc)}

        monkeypatch.setattr(journal, "leer_dia", falso_leer_dia)
        monkeypatch.setattr(journal, "escribir_venta", falso_escribir)
        monkeypatch.setattr(vista, "get_jwt_identity", lambda: "ana")

        with app.test_request_context(
            f"/api/ventas/{venta_id}/editar", method="POST", json=body
        ):
            resp = vista.editar_venta(venta_id)

        cuerpo, status = resp
        return status, json.loads(cuerpo.get_data(as_text=True)), escritos

    return hacer_llamada


# --------------------------------------------------------------- validaciones

def test_sin_motivo_da_400(editar):
    status, _, escritos = editar("v1", {"fecha": "2026-09-01", "monto_nuevo": 150})
    assert status == 400
    assert escritos == []


def test_motivo_en_blanco_da_400(editar):
    status, _, escritos = editar(
        "v1", {"fecha": "2026-09-01", "motivo": "   ", "monto_nuevo": 150}
    )
    assert status == 400
    assert escritos == []


def test_fecha_invalida_da_400(editar):
    status, _, _ = editar("v1", {"fecha": "01-2026", "motivo": "x", "monto_nuevo": 150})
    assert status == 400


@pytest.mark.parametrize("monto", [0, -10, "abc", None])
def test_monto_nuevo_invalido_da_400(editar, monto):
    status, _, escritos = editar(
        "v1", {"fecha": "2026-09-01", "motivo": "x", "monto_nuevo": monto}
    )
    assert status == 400
    assert escritos == []


def test_monto_nuevo_igual_al_vigente_da_400(editar):
    status, _, escritos = editar(
        "v1", {"fecha": "2026-09-01", "motivo": "x", "monto_nuevo": 100}
    )
    assert status == 400
    assert escritos == []


def test_venta_inexistente_da_404(editar):
    status, _, _ = editar(
        "fantasma", {"fecha": "2026-09-01", "motivo": "x", "monto_nuevo": 50}, dia=[]
    )
    assert status == 404


def test_no_se_puede_editar_una_fila_de_ajuste(editar):
    ajuste = _venta(id_="r1", venta_original_id="v1", estado="editada_reversa")
    status, _, _ = editar(
        "r1", {"fecha": "2026-09-01", "motivo": "x", "monto_nuevo": 50}, dia=[ajuste]
    )
    assert status == 400


def test_no_se_puede_editar_una_venta_cancelada(editar):
    original = _venta(id_="v1")
    reversion = _venta(
        id_="rev", total=-100.0, venta_original_id="v1", estado="cancelada"
    )
    status, _, escritos = editar(
        "v1",
        {"fecha": "2026-09-01", "motivo": "x", "monto_nuevo": 50},
        dia=[original, reversion],
    )
    assert status == 400
    assert escritos == []


# --------------------------------------------------------------- edicion basica

def test_edicion_al_alza_escribe_reversion_y_recaptura(editar):
    status, cuerpo, escritos = editar(
        "v1", {"fecha": "2026-09-01", "motivo": "cobre de menos", "monto_nuevo": 150}
    )
    assert status == 201
    assert len(escritos) == 2

    reversion, recaptura = escritos
    assert reversion["estado"] == "editada_reversa"
    assert reversion["total"] == -100.0
    assert reversion["venta_original_id"] == "v1"
    assert reversion["lineas"][0]["subtotal"] == -100.0
    assert reversion["lineas"][0]["cantidad"] == -1.0

    assert recaptura["estado"] == "editada"
    assert recaptura["total"] == 150.0
    assert recaptura["venta_original_id"] == "v1"
    assert recaptura["lineas"][0]["subtotal"] == 150.0
    assert recaptura["lineas"][0]["cantidad"] == 1.0  # la cantidad no cambia


def test_edicion_a_la_baja(editar):
    status, _, escritos = editar(
        "v1", {"fecha": "2026-09-01", "motivo": "cobre de mas", "monto_nuevo": 70}
    )
    assert status == 201
    assert escritos[0]["total"] == -100.0
    assert escritos[1]["total"] == 70.0


def test_guarda_motivo_autor_y_momento_en_ambas_filas(editar):
    _, _, escritos = editar(
        "v1", {"fecha": "2026-09-01", "motivo": "cobro incompleto", "monto_nuevo": 120}
    )
    for fila in escritos:
        assert fila["motivo_cancelacion"] == "cobro incompleto"
        assert fila["cancelada_por"] == "ana"
        assert fila["cancelada_en"] is not None
        assert fila["origen"] == "pos"
        assert fila["venta_original_id"] == "v1"


def test_neto_del_dia_sigue_al_monto_nuevo(editar):
    _, _, escritos = editar(
        "v1", {"fecha": "2026-09-01", "motivo": "x", "monto_nuevo": 80}
    )
    # original + reversion + recaptura
    assert 100.0 + escritos[0]["total"] + escritos[1]["total"] == 80.0


# --------------------------------------------------------------- escalado de lineas

def test_escalado_reparte_en_proporcion(editar):
    status, _, escritos = editar(
        "v1",
        {"fecha": "2026-09-01", "motivo": "x", "monto_nuevo": 150},
        dia=[_dos_lineas()],
    )
    assert status == 201
    recaptura = escritos[1]
    subtotales = sorted(l["subtotal"] for l in recaptura["lineas"])
    assert subtotales == [60.0, 90.0]  # 40*1.5 y 60*1.5
    assert [l["categoria"] for l in recaptura["lineas"]] == ["dulces", "copias"]
    assert sum(l["subtotal"] for l in recaptura["lineas"]) == 150.0


def test_escalado_con_redondeo_suma_exacta(editar):
    tres = _venta(
        lineas=[
            {"tipo": "categoria", "categoria": "dulces", "cantidad": 1.0,
             "precio_unitario": 33.34, "subtotal": 33.34, "monto_comision": None},
            {"tipo": "categoria", "categoria": "copias", "cantidad": 1.0,
             "precio_unitario": 33.33, "subtotal": 33.33, "monto_comision": None},
            {"tipo": "categoria", "categoria": "helados", "cantidad": 1.0,
             "precio_unitario": 33.33, "subtotal": 33.33, "monto_comision": None},
        ]
    )
    _, _, escritos = editar(
        "v1", {"fecha": "2026-09-01", "motivo": "x", "monto_nuevo": 99.99}, dia=[tres]
    )
    recaptura = escritos[1]
    assert round(sum(l["subtotal"] for l in recaptura["lineas"]), 2) == 99.99


# --------------------------------------------------------------- re-edicion

def test_reedicion_encadena_sobre_la_recaptura_vigente(editar):
    original = _venta(id_="v1", total=100.0)
    dia = [original]

    s1, _, e1 = editar("v1", {"fecha": "2026-09-01", "motivo": "a", "monto_nuevo": 120}, dia=dia)
    assert s1 == 201
    # el fixture ya agrego reversion+recaptura a `dia`
    s2, _, e2 = editar("v1", {"fecha": "2026-09-01", "motivo": "b", "monto_nuevo": 90}, dia=dia)
    assert s2 == 201

    # la segunda reversion revierte el importe VIGENTE (120), no el original
    assert e2[0]["total"] == -120.0
    assert e2[1]["total"] == 90.0
    # ids distintos de la primera edicion (secuencia distinta)
    assert e1[1]["id"] != e2[1]["id"]

    total_dia = sum(v["total"] for v in dia)
    assert total_dia == 90.0


# --------------------------------------------------------------- fecha de las filas

def test_fecha_hora_cae_en_el_dia_de_la_venta_no_en_hoy(editar):
    # se edita HOY una venta de un dia anterior: las filas de ajuste deben
    # fecharse en ESE dia (el journal particiona por fecha_hora.date() y las
    # agregaciones agrupan por DATE(fecha_hora, zona)), no en el dia en curso.
    _, _, escritos = editar(
        "v1", {"fecha": "2026-08-15", "motivo": "x", "monto_nuevo": 130}
    )
    for fila in escritos:
        assert fila["fecha_hora"].date() == datetime.date(2026, 8, 15)
    # el "cuando" real de la edicion sigue siendo ahora, en cancelada_en
    hoy = datetime.datetime.now(datetime.timezone.utc).date()
    for fila in escritos:
        assert fila["cancelada_en"].date() == hoy


def test_reediciones_quedan_ordenadas_por_fecha_hora(editar):
    dia = [_venta(id_="v1", total=100.0)]
    _, _, _ = editar("v1", {"fecha": "2026-09-01", "motivo": "a", "monto_nuevo": 120}, dia=dia)
    _, _, _ = editar("v1", {"fecha": "2026-09-01", "motivo": "b", "monto_nuevo": 90}, dia=dia)
    _, _, e3 = editar("v1", {"fecha": "2026-09-01", "motivo": "c", "monto_nuevo": 150}, dia=dia)
    assert e3[0]["total"] == -90.0  # revierte la recaptura vigente (la 2a edicion)

    recapturas = sorted(
        (v for v in dia if v.get("estado") == "editada"),
        key=lambda v: v["fecha_hora"],
    )
    fechas = [v["fecha_hora"] for v in recapturas]
    assert fechas == sorted(fechas) and len(set(fechas)) == 3
    assert recapturas[-1]["total"] == 150.0


# --------------------------------------------------------------- idempotencia

def test_reintento_con_el_mismo_monto_usa_los_mismos_ids(editar):
    e_a = editar("v1", {"fecha": "2026-09-01", "motivo": "x", "monto_nuevo": 130})[2]
    e_b = editar("v1", {"fecha": "2026-09-01", "motivo": "x", "monto_nuevo": 130})[2]
    assert e_a[0]["id"] == e_b[0]["id"]
    assert e_a[1]["id"] == e_b[1]["id"]
