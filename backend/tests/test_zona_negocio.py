"""
Tests de utilidades/zona_negocio.py -- la unica autoridad sobre "que dia
es hoy" y "a que dia pertenece este instante" (ver el docstring del
modulo para el bug que lo origino).
"""

import datetime

from utilidades import zona_negocio


def test_la_hora_de_cierre_es_las_nueve_de_la_noche():
    assert zona_negocio.HORA_CIERRE == datetime.time(21, 0)


def test_fecha_de_usa_el_dia_local_no_el_utc():
    # 01:23 UTC del 8 == 19:23 del 7 en hora del negocio.
    momento = datetime.datetime(2026, 9, 8, 1, 23, tzinfo=datetime.timezone.utc)
    assert zona_negocio.fecha_de(momento) == datetime.date(2026, 9, 7)


def test_fecha_de_acepta_texto_iso_como_lo_entrega_el_journal():
    assert zona_negocio.fecha_de("2026-09-08T01:23:00+00:00") == datetime.date(2026, 9, 7)


def test_fecha_de_lee_un_naive_como_utc():
    """Asi los escriben los modelos: datetime.now(timezone.utc)."""
    assert zona_negocio.fecha_de(datetime.datetime(2026, 9, 8, 1, 23)) == datetime.date(2026, 9, 7)


def test_reloj_lee_un_naive_como_hora_del_negocio():
    """A diferencia de fecha_de: aqui un naive es reloj de pared local."""
    assert zona_negocio.reloj(datetime.datetime(2026, 9, 7, 21, 1)).hour == 21


def test_antes_de_hora_cierre_con_reloj_de_pared():
    hoy = datetime.date(2026, 9, 7)
    assert zona_negocio.antes_de_hora_cierre(datetime.datetime.combine(hoy, datetime.time(20, 59)))
    assert not zona_negocio.antes_de_hora_cierre(
        datetime.datetime.combine(hoy, datetime.time(21, 0))
    )


def test_antes_de_hora_cierre_convierte_un_instante_utc():
    # 02:00 UTC del 8 == 20:00 del 7 local: todavia antes de la hora.
    assert zona_negocio.antes_de_hora_cierre(
        datetime.datetime(2026, 9, 8, 2, 0, tzinfo=datetime.timezone.utc)
    )
    # 03:30 UTC del 8 == 21:30 del 7 local: ya paso.
    assert not zona_negocio.antes_de_hora_cierre(
        datetime.datetime(2026, 9, 8, 3, 30, tzinfo=datetime.timezone.utc)
    )
