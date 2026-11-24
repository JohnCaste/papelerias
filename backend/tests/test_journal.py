"""
Tests de almacen_local/journal.py -- el criterio de aceptacion de #14
es literal: escribir una venta y poder recuperarla como si el proceso
hubiera muerto justo despues. Cada test usa una carpeta temporal
distinta, nunca la carpeta real por defecto.
"""

import datetime
import os
import threading

import pytest

from almacen_local import journal


def _venta(**overrides):
    datos = {
        "total": 20,
        "metodo_pago": "efectivo",
        "usuario_id": "u1",
        "lineas": [
            {
                "tipo": "categoria",
                "categoria": "pilas",
                "cantidad": 1,
                "precio_unitario": 20,
                "subtotal": 20,
            }
        ],
    }
    datos.update(overrides)
    return datos


def test_escribir_venta_devuelve_la_fila_con_id(tmp_path):
    fila = journal.escribir_venta(_venta(), carpeta=tmp_path)
    assert fila["id"]
    assert fila["total"] == 20.0


def test_venta_recien_escrita_se_puede_leer_de_inmediato(tmp_path):
    """
    Esto simula literalmente el criterio de aceptacion: escribir y
    releer desde cero (sin cache en memoria, sin estado compartido)
    como si fuera un proceso nuevo levantandose tras un crash.
    """
    fila = journal.escribir_venta(_venta(), carpeta=tmp_path)
    hoy = fila["fecha_hora"].date()

    leidas = journal.leer_dia(hoy, carpeta=tmp_path)

    assert len(leidas) == 1
    assert leidas[0]["id"] == fila["id"]
    assert leidas[0]["estado_local"] == "pendiente"


def test_dia_sin_ventas_no_revienta(tmp_path):
    assert journal.leer_dia(datetime.date(2026, 1, 1), carpeta=tmp_path) == []


def test_marcar_confirmada_cambia_el_estado_calculado(tmp_path):
    fila = journal.escribir_venta(_venta(), carpeta=tmp_path)
    hoy = fila["fecha_hora"].date()

    journal.marcar_confirmada(fila["id"], fecha=hoy, carpeta=tmp_path)

    leidas = journal.leer_dia(hoy, carpeta=tmp_path)
    assert leidas[0]["estado_local"] == "enviada"


def test_leer_pendientes_excluye_las_confirmadas(tmp_path):
    hoy = datetime.date.today()
    v1 = journal.escribir_venta(_venta(total=10), carpeta=tmp_path)
    v2 = journal.escribir_venta(_venta(total=20), carpeta=tmp_path)

    journal.marcar_confirmada(v1["id"], fecha=hoy, carpeta=tmp_path)

    pendientes = journal.leer_pendientes(hoy, carpeta=tmp_path)
    ids_pendientes = {v["id"] for v in pendientes}

    assert v1["id"] not in ids_pendientes
    assert v2["id"] in ids_pendientes


def test_buscar_venta_encuentra_por_id_y_fecha(tmp_path):
    hoy = datetime.date.today()
    v1 = journal.escribir_venta(_venta(total=10), carpeta=tmp_path)
    journal.escribir_venta(_venta(total=20), carpeta=tmp_path)

    encontrada = journal.buscar_venta(v1["id"], hoy, carpeta=tmp_path)

    assert encontrada is not None
    assert encontrada["id"] == v1["id"]
    assert encontrada["total"] == 10.0


def test_buscar_venta_devuelve_none_si_no_existe(tmp_path):
    hoy = datetime.date.today()
    journal.escribir_venta(_venta(), carpeta=tmp_path)

    assert journal.buscar_venta("no-existe", hoy, carpeta=tmp_path) is None


def test_buscar_venta_devuelve_none_si_el_dia_no_tiene_journal(tmp_path):
    assert journal.buscar_venta("x", datetime.date(2026, 1, 1), carpeta=tmp_path) is None


def test_rotacion_por_dia_usa_archivos_separados(tmp_path):
    ayer = datetime.datetime(2026, 8, 30, 12, 0, tzinfo=datetime.timezone.utc)
    hoy = datetime.datetime(2026, 8, 31, 12, 0, tzinfo=datetime.timezone.utc)

    journal.escribir_venta(_venta(fecha_hora=ayer), carpeta=tmp_path)
    journal.escribir_venta(_venta(fecha_hora=hoy), carpeta=tmp_path)

    archivos = sorted(p.name for p in tmp_path.glob("*.jsonl"))
    assert archivos == ["ventas-2026-08-30.jsonl", "ventas-2026-08-31.jsonl"]

    assert len(journal.leer_dia(ayer.date(), carpeta=tmp_path)) == 1
    assert len(journal.leer_dia(hoy.date(), carpeta=tmp_path)) == 1


def test_reconstruir_desde_junta_varios_dias(tmp_path):
    for dia in range(1, 4):
        fecha = datetime.datetime(2026, 8, dia, 10, 0, tzinfo=datetime.timezone.utc)
        journal.escribir_venta(_venta(fecha_hora=fecha), carpeta=tmp_path)

    ventas = journal.reconstruir_desde(
        datetime.date(2026, 8, 1), datetime.date(2026, 8, 3), carpeta=tmp_path
    )
    assert len(ventas) == 3


def test_reconstruir_desde_ignora_dias_fuera_de_rango(tmp_path):
    dentro = datetime.datetime(2026, 8, 15, 10, 0, tzinfo=datetime.timezone.utc)
    fuera = datetime.datetime(2026, 9, 1, 10, 0, tzinfo=datetime.timezone.utc)
    journal.escribir_venta(_venta(fecha_hora=dentro), carpeta=tmp_path)
    journal.escribir_venta(_venta(fecha_hora=fuera), carpeta=tmp_path)

    ventas = journal.reconstruir_desde(
        datetime.date(2026, 8, 1), datetime.date(2026, 8, 31), carpeta=tmp_path
    )
    assert len(ventas) == 1


def test_fsync_se_llama_tras_cada_escritura(tmp_path, monkeypatch):
    llamadas = []
    fsync_real = os.fsync

    def fsync_espia(fd):
        llamadas.append(fd)
        return fsync_real(fd)

    monkeypatch.setattr(journal.os, "fsync", fsync_espia)
    journal.escribir_venta(_venta(), carpeta=tmp_path)

    assert len(llamadas) == 1


def test_lineas_se_normalizan_igual_que_en_bigquery(tmp_path):
    """
    El journal usa el mismo modelos_venta.construir_venta que el
    repositorio de BigQuery -- las dos rutas de escritura no deben
    poder divergir en como arman una venta.
    """
    fila = journal.escribir_venta(_venta(), carpeta=tmp_path)
    linea = fila["lineas"][0]
    assert linea["cantidad"] == 1.0
    assert linea["subtotal"] == 20.0
    assert linea["producto_id"] is None


def test_escrituras_concurrentes_no_pierden_ni_corrompen_lineas(tmp_path):
    hoy = datetime.datetime.now(datetime.timezone.utc)
    errores = []

    def escribir(n):
        try:
            journal.escribir_venta(_venta(total=n, fecha_hora=hoy), carpeta=tmp_path)
        except Exception as error:  # noqa: BLE001
            errores.append(error)

    hilos = [threading.Thread(target=escribir, args=(i,)) for i in range(20)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    assert errores == []
    ventas = journal.leer_dia(hoy.date(), carpeta=tmp_path)
    assert len(ventas) == 20
    assert len({v["id"] for v in ventas}) == 20


def test_evento_desconocido_en_el_archivo_no_rompe_la_lectura(tmp_path):
    """
    Robustez ante un archivo tocado a mano o por una version futura del
    codigo que agregue un tipo de evento nuevo: se ignora, no revienta.
    """
    hoy = datetime.date(2026, 8, 31)
    archivo = journal._archivo_dia(hoy, carpeta=tmp_path)
    archivo.parent.mkdir(parents=True, exist_ok=True)
    with open(archivo, "w", encoding="utf-8") as f:
        f.write('{"evento": "algo_nuevo", "id": "x"}\n')

    assert journal.leer_dia(hoy, carpeta=tmp_path) == []


def test_una_venta_de_la_noche_cae_en_su_dia_local_no_en_el_dia_utc(tmp_path):
    """
    Regresion: 19:23 hora del negocio (UTC-6) del 7 de septiembre es
    01:23 UTC del 8. Antes se guardaba en `ventas-2026-09-08.jsonl` y
    aparecia al dia siguiente como "venta de hoy".
    """
    noche = datetime.datetime(2026, 9, 8, 1, 23, tzinfo=datetime.timezone.utc)

    journal.escribir_venta(_venta(fecha_hora=noche), carpeta=tmp_path)

    archivos = [p.name for p in tmp_path.glob("*.jsonl")]
    assert archivos == ["ventas-2026-09-07.jsonl"]
    assert len(journal.leer_dia(datetime.date(2026, 9, 7), carpeta=tmp_path)) == 1
    assert journal.leer_dia(datetime.date(2026, 9, 8), carpeta=tmp_path) == []


def test_la_frontera_del_dia_es_la_medianoche_local(tmp_path):
    """23:59 local del 7 y 00:01 local del 8 caen en dias distintos."""
    ultimo_del_7 = datetime.datetime(2026, 9, 8, 5, 59, tzinfo=datetime.timezone.utc)
    primero_del_8 = datetime.datetime(2026, 9, 8, 6, 1, tzinfo=datetime.timezone.utc)

    journal.escribir_venta(_venta(fecha_hora=ultimo_del_7), carpeta=tmp_path)
    journal.escribir_venta(_venta(fecha_hora=primero_del_8), carpeta=tmp_path)

    archivos = sorted(p.name for p in tmp_path.glob("*.jsonl"))
    assert archivos == ["ventas-2026-09-07.jsonl", "ventas-2026-09-08.jsonl"]
