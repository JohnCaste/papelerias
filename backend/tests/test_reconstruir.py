"""
Tests del comando de linea almacen_local/reconstruir.py.
"""

import datetime

import pytest

import almacen_local.reconstruir as cli


def _venta_leida(total, estado):
    return {
        "id": "abcdefgh-1234",
        "fecha_hora": "2026-08-31T10:00:00+00:00",
        "total": total,
        "metodo_pago": "efectivo",
        "estado_local": estado,
    }


def test_dia_llama_a_leer_dia(monkeypatch, capsys):
    llamado = {}

    def falso_leer_dia(fecha, **k):
        llamado["fecha"] = fecha
        return [_venta_leida(20, "pendiente")]

    monkeypatch.setattr(cli, "leer_dia", falso_leer_dia)

    cli.main(["--dia", "2026-08-31"])

    assert llamado["fecha"] == datetime.date(2026, 8, 31)
    salida = capsys.readouterr().out
    assert "1 ventas, total 20.00" in salida
    assert "1 pendientes" in salida


def test_rango_llama_a_reconstruir_desde(monkeypatch, capsys):
    llamado = {}

    def falso_reconstruir(desde, hasta, **k):
        llamado["rango"] = (desde, hasta)
        return [_venta_leida(10, "enviada"), _venta_leida(15, "pendiente")]

    monkeypatch.setattr(cli, "reconstruir_desde", falso_reconstruir)

    cli.main(["--desde", "2026-08-01", "--hasta", "2026-08-31"])

    assert llamado["rango"] == (datetime.date(2026, 8, 1), datetime.date(2026, 8, 31))
    salida = capsys.readouterr().out
    assert "2 ventas, total 25.00" in salida
    assert "1 pendientes" in salida


def test_sin_argumentos_da_error_de_uso():
    with pytest.raises(SystemExit):
        cli.main([])
