"""
Tests de almacen_local/programador_cierre.py -- disparadores automatico
y perezoso del cierre de dia (#50).
"""

import datetime
import time

from almacen_local import cierres, journal, programador_cierre


def test_catchup_perezoso_cierra_dias_pendientes(tmp_path):
    prog = programador_cierre.ProgramadorCierre(carpeta_journal=tmp_path, carpeta_cierre=tmp_path)
    resultado = prog.ejecutar_catchup_perezoso()

    ayer = datetime.date.today() - datetime.timedelta(days=1)
    assert any(c["fecha_inicio"] == ayer for c in resultado)
    assert cierres.ya_cerrado(ayer, tmp_path)


def test_catchup_perezoso_nunca_lanza(tmp_path, monkeypatch):
    def truena(*a, **k):
        raise RuntimeError("algo no previsto")

    monkeypatch.setattr(cierres, "cerrar_dias_pendientes", truena)

    prog = programador_cierre.ProgramadorCierre(carpeta_journal=tmp_path, carpeta_cierre=tmp_path)
    resultado = prog.ejecutar_catchup_perezoso()  # no debe lanzar

    assert resultado == []


def test_revisar_cierre_automatico_antes_de_la_hora_no_hace_nada(tmp_path):
    prog = programador_cierre.ProgramadorCierre(
        hora_cierre=datetime.time(20, 0), carpeta_journal=tmp_path, carpeta_cierre=tmp_path
    )
    antes_de_hora = datetime.datetime.combine(datetime.date.today(), datetime.time(19, 59))

    resultado = prog.revisar_cierre_automatico(ahora=antes_de_hora)

    assert resultado is None
    assert not cierres.ya_cerrado(datetime.date.today(), tmp_path)


def test_revisar_cierre_automatico_despues_de_la_hora_cierra_hoy(tmp_path):
    prog = programador_cierre.ProgramadorCierre(
        hora_cierre=datetime.time(20, 0), carpeta_journal=tmp_path, carpeta_cierre=tmp_path
    )
    despues_de_hora = datetime.datetime.combine(datetime.date.today(), datetime.time(20, 1))

    resultado = prog.revisar_cierre_automatico(ahora=despues_de_hora)

    assert resultado is not None
    assert resultado["generado_por"] == "automatico"
    assert cierres.ya_cerrado(datetime.date.today(), tmp_path)


def test_revisar_cierre_automatico_no_repite_si_ya_esta_cerrado(tmp_path):
    prog = programador_cierre.ProgramadorCierre(
        hora_cierre=datetime.time(20, 0), carpeta_journal=tmp_path, carpeta_cierre=tmp_path
    )
    hoy = datetime.date.today()
    # Acta definitiva (no provisional): el automatico no debe tocarla.
    cierres.generar_cierre_dia(hoy, "automatico", carpeta_journal=tmp_path, carpeta_cierre=tmp_path)

    despues_de_hora = datetime.datetime.combine(hoy, datetime.time(20, 1))
    resultado = prog.revisar_cierre_automatico(ahora=despues_de_hora)

    assert resultado is None  # ya estaba cerrada y definitiva -- no la vuelve a tocar


def test_revisar_cierre_automatico_finaliza_un_acta_provisional(tmp_path, monkeypatch):
    monkeypatch.setattr(cierres, "es_antes_de_hora_cierre", lambda *a, **k: True)
    prog = programador_cierre.ProgramadorCierre(
        hora_cierre=datetime.time(20, 0), carpeta_journal=tmp_path, carpeta_cierre=tmp_path
    )
    hoy = datetime.date.today()
    hora = datetime.datetime.combine(hoy, datetime.time(18, 0), tzinfo=datetime.timezone.utc)
    journal.escribir_venta(
        {"fecha_hora": hora, "total": 20, "metodo_pago": "efectivo", "usuario_id": "u1", "lineas": []},
        carpeta=tmp_path,
    )
    cierres.generar_cierre_dia(hoy, "manual", carpeta_journal=tmp_path, carpeta_cierre=tmp_path)
    assert cierres.obtener_cierre_local(hoy, tmp_path)["provisional"] is True

    journal.escribir_venta(
        {"fecha_hora": hora, "total": 80, "metodo_pago": "efectivo", "usuario_id": "u1", "lineas": []},
        carpeta=tmp_path,
    )
    despues_de_hora = datetime.datetime.combine(hoy, datetime.time(20, 1))
    resultado = prog.revisar_cierre_automatico(ahora=despues_de_hora)

    assert resultado is not None
    assert resultado["generado_por"] == "automatico"
    assert resultado["total"] == 100.0

    acta = cierres.obtener_cierre_local(hoy, tmp_path)
    assert acta["provisional"] is False
    # Segundo tick: ya esta finalizada, no hace nada.
    assert prog.revisar_cierre_automatico(ahora=despues_de_hora) is None


def test_revisar_cierre_automatico_nunca_lanza(tmp_path, monkeypatch):
    monkeypatch.setattr(cierres, "ya_cerrado", lambda *a, **k: False)

    def truena(*a, **k):
        raise RuntimeError("algo no previsto")

    monkeypatch.setattr(cierres, "generar_cierre_dia", truena)

    prog = programador_cierre.ProgramadorCierre(
        hora_cierre=datetime.time(0, 0), carpeta_journal=tmp_path, carpeta_cierre=tmp_path
    )
    resultado = prog.revisar_cierre_automatico()  # no debe lanzar

    assert resultado is None


def test_iniciar_y_detener_el_hilo_hace_el_catchup_perezoso(tmp_path):
    """Unico test con hilo real: confirma que iniciar() de verdad corre el catchup."""
    prog = programador_cierre.ProgramadorCierre(
        intervalo_revision_segundos=60, carpeta_journal=tmp_path, carpeta_cierre=tmp_path
    )
    prog.iniciar()
    try:
        ayer = datetime.date.today() - datetime.timedelta(days=1)
        for _ in range(50):
            if cierres.ya_cerrado(ayer, tmp_path):
                break
            time.sleep(0.02)
    finally:
        prog.detener(timeout=2)

    assert cierres.ya_cerrado(ayer, tmp_path)
