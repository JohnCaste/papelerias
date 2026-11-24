"""
Tests de acceso_datos/escrituras.py -- cliente falso, sin red.
"""

import datetime
import decimal

import pytest

from acceso_datos.escrituras import ErrorInsercion, insertar_filas


class ClienteFalso:
    def __init__(self, errores=None):
        self.project = "proyecto-de-prueba"
        self.errores = errores or []
        self.llamadas = []

    def insert_rows_json(self, tabla_id, filas_json, row_ids=None):
        self.llamadas.append((tabla_id, filas_json, row_ids))
        return self.errores


def test_no_llama_al_cliente_si_no_hay_filas():
    cliente = ClienteFalso()
    insertar_filas("lapape.producto", [], cliente=cliente)
    assert cliente.llamadas == []


def test_arma_tabla_id_con_el_project_del_cliente():
    cliente = ClienteFalso()
    insertar_filas("lapape.producto", [{"id": "1"}], cliente=cliente)
    tabla_id, _, _ = cliente.llamadas[0]
    assert tabla_id == "proyecto-de-prueba.lapape.producto"


def test_manda_row_ids_para_deduplicacion():
    cliente = ClienteFalso()
    insertar_filas(
        "lapape.venta", [{"id": "aaa"}, {"id": "bbb"}], cliente=cliente
    )
    _, _, row_ids = cliente.llamadas[0]
    assert row_ids == ["aaa", "bbb"]


def test_serializa_fechas_y_decimales_a_texto():
    cliente = ClienteFalso()
    fila = {
        "id": "1",
        "creado_en": datetime.datetime(2026, 8, 31, 12, 0, 0),
        "fecha": datetime.date(2026, 8, 31),
        "precio": decimal.Decimal("12.50"),
    }
    insertar_filas("lapape.producto", [fila], cliente=cliente)
    _, filas_json, _ = cliente.llamadas[0]
    enviado = filas_json[0]
    assert enviado["creado_en"] == "2026-08-31T12:00:00"
    assert enviado["fecha"] == "2026-08-31"
    assert enviado["precio"] == "12.50"


def test_serializa_lineas_anidadas_de_una_venta():
    cliente = ClienteFalso()
    fila = {
        "id": "1",
        "lineas": [
            {"cantidad": decimal.Decimal("2"), "subtotal": decimal.Decimal("40.00")}
        ],
    }
    insertar_filas("lapape.venta", [fila], cliente=cliente)
    _, filas_json, _ = cliente.llamadas[0]
    linea = filas_json[0]["lineas"][0]
    assert linea["cantidad"] == "2"
    assert linea["subtotal"] == "40.00"


def test_lanza_error_insercion_si_bigquery_rechaza_filas():
    cliente = ClienteFalso(errores=[{"index": 0, "errors": [{"reason": "invalid"}]}])
    with pytest.raises(ErrorInsercion):
        insertar_filas("lapape.producto", [{"id": "1"}], cliente=cliente)
