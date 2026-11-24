"""
Tests de acceso_datos/parametros.py -- sin red, sin credenciales.
"""

import datetime
import decimal

import pytest
from google.cloud import bigquery

from acceso_datos.parametros import construir_parametros


def test_infiere_string():
    (p,) = construir_parametros({"nombre": "Bic"})
    assert p.name == "nombre"
    assert p.type_ == "STRING"
    assert p.value == "Bic"


def test_infiere_bool_antes_que_int():
    # bool es subclase de int en Python: True no debe mapear a INT64.
    (p,) = construir_parametros({"activo": True})
    assert p.type_ == "BOOL"


def test_infiere_int():
    (p,) = construir_parametros({"limite": 20})
    assert p.type_ == "INT64"


def test_infiere_float_como_numeric():
    (p,) = construir_parametros({"precio": 12.5})
    assert p.type_ == "NUMERIC"


def test_infiere_decimal_como_numeric():
    (p,) = construir_parametros({"precio": decimal.Decimal("12.50")})
    assert p.type_ == "NUMERIC"


def test_infiere_datetime_como_timestamp():
    (p,) = construir_parametros({"fecha_hora": datetime.datetime(2026, 8, 31)})
    assert p.type_ == "TIMESTAMP"


def test_infiere_date_como_date():
    (p,) = construir_parametros({"fecha": datetime.date(2026, 8, 31)})
    assert p.type_ == "DATE"


def test_tipo_explicito_tiene_prioridad():
    (p,) = construir_parametros({"x": 5}, tipos={"x": "NUMERIC"})
    assert p.type_ == "NUMERIC"


def test_valor_none_requiere_tipo_explicito():
    with pytest.raises(TypeError):
        construir_parametros({"marca": None})


def test_valor_none_con_tipo_explicito_funciona():
    (p,) = construir_parametros({"marca": None}, tipos={"marca": "STRING"})
    assert p.value is None


def test_tipo_no_soportado_lanza_error_claro():
    class Cosa:
        pass

    with pytest.raises(TypeError):
        construir_parametros({"x": Cosa()})


def test_varios_parametros_en_orden():
    parametros = construir_parametros({"a": "x", "b": 1, "c": True})
    nombres = [p.name for p in parametros]
    assert nombres == ["a", "b", "c"]


def test_lista_se_convierte_en_array_query_parameter():
    (p,) = construir_parametros({"ids": ["a", "b", "c"]})
    assert isinstance(p, bigquery.ArrayQueryParameter)
    assert p.array_type == "STRING"
    assert p.values == ["a", "b", "c"]


def test_lista_vacia_requiere_tipo_explicito():
    with pytest.raises(TypeError):
        construir_parametros({"ids": []})


def test_lista_vacia_con_tipo_explicito_funciona():
    (p,) = construir_parametros({"ids": []}, tipos={"ids": "STRING"})
    assert p.values == []
    assert p.array_type == "STRING"
