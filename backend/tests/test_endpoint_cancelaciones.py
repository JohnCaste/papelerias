"""
Tests de ventas/cancelaciones.py (#26) -- vista de Flask con el journal
falseado. Cancelar es un registro NUEVO de signo contrario: nunca toca
ni borra la fila original.
"""

import datetime
import json

import pytest
from flask import Flask

import ventas.cancelaciones as vista
from almacen_local import journal


@pytest.fixture
def app():
    app = Flask(__name__)
    app.testing = True
    return app


def _venta(id_="v1", total=100.0, detallada=False, lineas=None):
    return {
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


@pytest.fixture
def cancelar(app, monkeypatch):
    """
    Devuelve `llamar(venta_id, body, original=<venta o None>)` que ejecuta
    la vista y regresa `(status, body_json, fila_escrita)`.
    """
    estado = {"escrito": {}}

    def hacer_llamada(venta_id, body, original="__DEFAULT__"):
        original_venta = _venta(id_=venta_id) if original == "__DEFAULT__" else original

        def falso_buscar(id_, fecha, carpeta=None):
            if original_venta is not None and id_ == original_venta["id"]:
                return original_venta
            return None

        def falso_escribir(datos, carpeta=None):
            estado["escrito"] = dict(datos)
            return {**datos, "creado_en": datetime.datetime.now(datetime.timezone.utc)}

        monkeypatch.setattr(journal, "buscar_venta", falso_buscar)
        monkeypatch.setattr(journal, "escribir_venta", falso_escribir)
        monkeypatch.setattr(vista, "get_jwt_identity", lambda: "ana")

        with app.test_request_context(
            f"/api/ventas/{venta_id}/cancelar", method="POST", json=body
        ):
            resp = vista.cancelar_venta(venta_id)

        cuerpo, status = resp
        return status, json.loads(cuerpo.get_data(as_text=True)), estado["escrito"]

    return hacer_llamada


# --------------------------------------------------------------- validaciones

def test_sin_motivo_da_400(cancelar):
    status, cuerpo, escrito = cancelar("v1", {"fecha": "2026-09-01"})
    assert status == 400
    assert escrito == {}  # no se escribio nada


def test_motivo_en_blanco_da_400(cancelar):
    status, _, escrito = cancelar("v1", {"fecha": "2026-09-01", "motivo": "   "})
    assert status == 400
    assert escrito == {}


def test_fecha_invalida_da_400(cancelar):
    status, _, _ = cancelar("v1", {"fecha": "01-2026", "motivo": "error"})
    assert status == 400


def test_venta_inexistente_da_404(cancelar):
    status, _, _ = cancelar("fantasma", {"fecha": "2026-09-01", "motivo": "x"}, original=None)
    assert status == 404


def test_no_se_puede_cancelar_una_reversion(cancelar):
    reversion = _venta(id_="r1")
    reversion["venta_original_id"] = "v1"
    status, _, _ = cancelar("r1", {"fecha": "2026-09-01", "motivo": "x"}, original=reversion)
    assert status == 400


def test_indice_de_linea_inexistente_da_400(cancelar):
    status, _, escrito = cancelar(
        "v1", {"fecha": "2026-09-01", "motivo": "x", "lineas": [5]}
    )
    assert status == 400
    assert escrito == {}


# --------------------------------------------------------------- cancelacion total

def test_cancelacion_total_escribe_reversion_de_signo_contrario(cancelar):
    status, cuerpo, escrito = cancelar("v1", {"fecha": "2026-09-01", "motivo": "cobro doble"})

    assert status == 201
    assert escrito["venta_original_id"] == "v1"
    assert escrito["total"] == -100.0
    assert escrito["estado"] == "cancelada"
    assert escrito["lineas"][0]["subtotal"] == -100.0
    assert escrito["lineas"][0]["cantidad"] == -1.0


def test_cancelacion_total_guarda_motivo_autor_y_momento(cancelar):
    _, _, escrito = cancelar("v1", {"fecha": "2026-09-01", "motivo": "error de tecleo"})

    assert escrito["motivo_cancelacion"] == "error de tecleo"
    assert escrito["cancelada_por"] == "ana"
    assert escrito["cancelada_en"] is not None
    assert escrito["origen"] == "pos"
    assert escrito["extemporanea"] is False


def test_neto_original_mas_reversion_es_cero(cancelar):
    _, _, escrito = cancelar("v1", {"fecha": "2026-09-01", "motivo": "x"})
    assert _venta()["total"] + escrito["total"] == 0


def test_reintento_con_el_mismo_cuerpo_usa_el_mismo_id(cancelar):
    _, _, escrito1 = cancelar("v1", {"fecha": "2026-09-01", "motivo": "x"})
    _, _, escrito2 = cancelar("v1", {"fecha": "2026-09-01", "motivo": "x"})
    assert escrito1["id"] == escrito2["id"]


# ----------------------------------------------------------- devolucion parcial

def _venta_dos_lineas():
    return _venta(
        total=100.0,
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


def test_devolucion_parcial_solo_revierte_las_lineas_pedidas(cancelar):
    status, _, escrito = cancelar(
        "v1",
        {"fecha": "2026-09-01", "motivo": "solo devuelve las copias", "lineas": [1]},
        original=_venta_dos_lineas(),
    )

    assert status == 201
    assert escrito["estado"] == "devolucion_parcial"
    assert len(escrito["lineas"]) == 1
    assert escrito["lineas"][0]["subtotal"] == -40.0
    assert escrito["total"] == -40.0


def test_pasar_todos_los_indices_es_cancelacion_total(cancelar):
    _, _, escrito = cancelar(
        "v1",
        {"fecha": "2026-09-01", "motivo": "todo", "lineas": [0, 1]},
        original=_venta_dos_lineas(),
    )
    assert escrito["estado"] == "cancelada"
    assert escrito["total"] == -100.0
