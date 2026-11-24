"""
Tests de utilidades/reparar_journal_zona.py -- el script que reacomoda
los journals escritos antes del arreglo de zona horaria.
"""

import datetime
import json

from utilidades import reparar_journal_zona


def _linea(archivo, evento):
    with open(archivo, "a", encoding="utf-8") as f:
        f.write(json.dumps(evento, ensure_ascii=False) + "\n")


def _venta(id_, fecha_hora_iso, total=40):
    return {
        "evento": "venta",
        "id": id_,
        "fecha_hora": fecha_hora_iso,
        "total": total,
        "metodo_pago": "efectivo",
        "usuario_id": "u1",
        "lineas": [],
    }


def _journal_con_el_bug(tmp_path):
    """Dos ventas de la noche del 7, guardadas (mal) en el archivo del 8."""
    archivo = tmp_path / "ventas-2026-09-08.jsonl"
    _linea(archivo, _venta("a", "2026-09-08T01:23:00+00:00"))
    _linea(archivo, _venta("b", "2026-09-08T02:24:00+00:00", total=35))
    _linea(archivo, {"evento": "confirmacion", "id": "a", "confirmado_en": "2026-09-08T01:24:00+00:00"})
    return archivo


def test_planear_detecta_las_ventas_en_el_dia_equivocado(tmp_path):
    _journal_con_el_bug(tmp_path)

    _, movidas = reparar_journal_zona.planear(tmp_path)

    assert movidas == {(datetime.date(2026, 9, 8), datetime.date(2026, 9, 7)): 2}


def test_aplicar_reacomoda_las_ventas_y_sus_confirmaciones(tmp_path):
    _journal_con_el_bug(tmp_path)

    por_dia, _ = reparar_journal_zona.planear(tmp_path)
    reparar_journal_zona.aplicar(tmp_path, por_dia)

    archivos = sorted(p.name for p in tmp_path.glob("ventas-*.jsonl"))
    assert archivos == ["ventas-2026-09-07.jsonl"]

    from almacen_local import journal

    ventas = journal.leer_dia(datetime.date(2026, 9, 7), carpeta=tmp_path)
    assert [v["id"] for v in ventas] == ["a", "b"]
    # La confirmacion viajo junto a su venta: el estado se conserva.
    assert [v["estado_local"] for v in ventas] == ["enviada", "pendiente"]
    assert journal.leer_dia(datetime.date(2026, 9, 8), carpeta=tmp_path) == []


def test_es_idempotente(tmp_path):
    _journal_con_el_bug(tmp_path)
    por_dia, _ = reparar_journal_zona.planear(tmp_path)
    reparar_journal_zona.aplicar(tmp_path, por_dia)

    _, movidas = reparar_journal_zona.planear(tmp_path)

    assert movidas == {}


def test_aplicar_deja_un_respaldo_de_la_carpeta(tmp_path):
    carpeta = tmp_path / "journal"
    carpeta.mkdir()
    _journal_con_el_bug(carpeta)

    por_dia, _ = reparar_journal_zona.planear(carpeta)
    reparar_journal_zona.aplicar(carpeta, por_dia)

    respaldos = list(tmp_path.glob("journal_respaldo-*"))
    assert len(respaldos) == 1
    assert (respaldos[0] / "ventas-2026-09-08.jsonl").exists()


def test_un_journal_ya_correcto_no_reporta_nada(tmp_path):
    archivo = tmp_path / "ventas-2026-09-07.jsonl"
    _linea(archivo, _venta("a", "2026-09-07T18:00:00+00:00"))  # mediodia local

    _, movidas = reparar_journal_zona.planear(tmp_path)

    assert movidas == {}
