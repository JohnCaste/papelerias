"""
Tests de almacen_local/cierres.py -- el cierre de dia (#50). Todo se
prueba contra carpetas temporales, nunca la carpeta real.
"""

import datetime

from almacen_local import cierres, journal
from utilidades import categorias


def _con_monto(desglose):
    """
    {clave: monto} dejando fuera las categorias en cero: el desglose
    devuelve SIEMPRE la lista canonica completa (utilidades/categorias.py),
    y estos tests solo comprueban las que tuvieron venta.
    """
    return {d["clave"]: d["monto"] for d in desglose if d["monto"]}


def _venta(fecha_hora, **overrides):
    total = overrides.get("total", 20)
    datos = {
        "fecha_hora": fecha_hora,
        "total": total,
        "metodo_pago": "efectivo",
        "usuario_id": "u1",
        # Por defecto, una sola linea de categoria cuyo subtotal iguala el
        # total -- el desglose por categoria suma `lineas.subtotal`.
        "lineas": [
            {
                "tipo": "categoria",
                "categoria": "dulces",
                "cantidad": 1,
                "precio_unitario": total,
                "subtotal": total,
            }
        ],
    }
    datos.update(overrides)
    return datos


def test_dia_sin_cierre_no_esta_cerrado(tmp_path):
    assert cierres.ya_cerrado(datetime.date(2026, 1, 1), tmp_path) is False
    assert cierres.obtener_cierre_local(datetime.date(2026, 1, 1), tmp_path) is None


def test_generar_cierre_sin_ventas_da_totales_en_cero(tmp_path):
    fecha = datetime.date(2026, 1, 5)
    cierre = cierres.generar_cierre_dia(
        fecha, "manual", carpeta_journal=tmp_path, carpeta_cierre=tmp_path
    )

    assert cierre["total"] == 0
    assert cierre["num_ventas"] == 0
    # El desglose trae SIEMPRE la lista canonica completa, en cero.
    assert {d["monto"] for d in cierre["desglose_categoria"]} == {0.0}
    assert [d["clave"] for d in cierre["desglose_categoria"]] == list(categorias.CLAVES)
    assert cierre["estado"] == "cerrado"
    assert cierre["sincronizado"] is False


def test_generar_cierre_suma_las_ventas_del_dia(tmp_path):
    fecha = datetime.date(2026, 8, 31)
    hora = datetime.datetime.combine(fecha, datetime.time(10, 0), tzinfo=datetime.timezone.utc)

    journal.escribir_venta(_venta(hora, total=20, metodo_pago="efectivo"), carpeta=tmp_path)
    journal.escribir_venta(
        _venta(hora, total=15, metodo_pago="tarjeta", lineas=[
            {"tipo": "categoria", "categoria": "helados", "cantidad": 1, "precio_unitario": 15, "subtotal": 15}
        ]),
        carpeta=tmp_path,
    )

    cierre = cierres.generar_cierre_dia(
        fecha, "manual", carpeta_journal=tmp_path, carpeta_cierre=tmp_path
    )

    assert cierre["total"] == 35.0
    assert cierre["num_ventas"] == 2
    assert cierre["generado_por"] == "manual"


def test_desglose_por_categoria_agrupa_correctamente(tmp_path):
    fecha = datetime.date(2026, 8, 31)
    hora = datetime.datetime.combine(fecha, datetime.time(10, 0), tzinfo=datetime.timezone.utc)

    journal.escribir_venta(_venta(hora, total=10), carpeta=tmp_path)  # dulces
    journal.escribir_venta(_venta(hora, total=15), carpeta=tmp_path)  # dulces
    journal.escribir_venta(
        _venta(hora, total=8, lineas=[
            {"tipo": "categoria", "categoria": "helados", "cantidad": 1, "precio_unitario": 8, "subtotal": 8}
        ]),
        carpeta=tmp_path,
    )

    cierre = cierres.generar_cierre_dia(
        fecha, "manual", carpeta_journal=tmp_path, carpeta_cierre=tmp_path
    )

    desglose = _con_monto(cierre["desglose_categoria"])
    assert desglose == {"dulces": 25.0, "helados": 8.0}


def test_desglose_reparte_una_venta_con_varias_lineas_de_categoria(tmp_path):
    """El desglose suma por linea, no atribuye todo a la primera categoria."""
    fecha = datetime.date(2026, 8, 31)
    hora = datetime.datetime.combine(fecha, datetime.time(10, 0), tzinfo=datetime.timezone.utc)

    journal.escribir_venta(
        _venta(
            hora,
            total=50,
            lineas=[
                {"tipo": "categoria", "categoria": "copias", "cantidad": 1, "precio_unitario": 30, "subtotal": 30},
                {"tipo": "categoria", "categoria": "dulces", "cantidad": 1, "precio_unitario": 20, "subtotal": 20},
            ],
        ),
        carpeta=tmp_path,
    )

    cierre = cierres.generar_cierre_dia(
        fecha, "manual", carpeta_journal=tmp_path, carpeta_cierre=tmp_path
    )

    desglose = _con_monto(cierre["desglose_categoria"])
    assert desglose == {"copias": 30.0, "dulces": 20.0}


def test_desglose_por_metodo_pago_agrupa_correctamente(tmp_path):
    fecha = datetime.date(2026, 8, 31)
    hora = datetime.datetime.combine(fecha, datetime.time(10, 0), tzinfo=datetime.timezone.utc)

    journal.escribir_venta(_venta(hora, total=10, metodo_pago="efectivo"), carpeta=tmp_path)
    journal.escribir_venta(_venta(hora, total=15, metodo_pago="transferencia"), carpeta=tmp_path)

    cierre = cierres.generar_cierre_dia(
        fecha, "manual", carpeta_journal=tmp_path, carpeta_cierre=tmp_path
    )

    desglose = {d["clave"]: d["monto"] for d in cierre["desglose_metodo_pago"]}
    assert desglose == {"efectivo": 10.0, "transferencia": 15.0}


def test_generar_cierre_es_idempotente(tmp_path):
    fecha = datetime.date(2026, 8, 31)
    hora = datetime.datetime.combine(fecha, datetime.time(10, 0), tzinfo=datetime.timezone.utc)
    journal.escribir_venta(_venta(hora, total=20), carpeta=tmp_path)

    primero = cierres.generar_cierre_dia(fecha, "manual", carpeta_journal=tmp_path, carpeta_cierre=tmp_path)

    # Otra venta capturada DESPUES del cierre no debe alterar un cierre
    # que ya se genero -- eso seria #54, no este issue.
    journal.escribir_venta(_venta(hora, total=999), carpeta=tmp_path)
    segundo = cierres.generar_cierre_dia(fecha, "automatico", carpeta_journal=tmp_path, carpeta_cierre=tmp_path)

    assert primero["id"] == segundo["id"]
    assert segundo["total"] == 20.0  # no incluye la venta de 999
    assert segundo["generado_por"] == "manual"  # conserva el original


def test_marcar_sincronizado_actualiza_el_estado(tmp_path):
    fecha = datetime.date(2026, 8, 31)
    cierres.generar_cierre_dia(fecha, "manual", carpeta_journal=tmp_path, carpeta_cierre=tmp_path)
    assert cierres.obtener_cierre_local(fecha, tmp_path)["sincronizado"] is False

    cierres.marcar_sincronizado(fecha, tmp_path)
    assert cierres.obtener_cierre_local(fecha, tmp_path)["sincronizado"] is True


def test_cerrar_dias_pendientes_no_toca_hoy(tmp_path):
    hoy = datetime.date.today()
    hora_hoy = datetime.datetime.combine(hoy, datetime.time(10, 0), tzinfo=datetime.timezone.utc)
    journal.escribir_venta(_venta(hora_hoy, total=999), carpeta=tmp_path)

    cierres.cerrar_dias_pendientes(
        generado_por="perezoso", dias_hacia_atras=3, carpeta_journal=tmp_path, carpeta_cierre=tmp_path
    )

    assert cierres.ya_cerrado(hoy, tmp_path) is False


def test_cerrar_dias_pendientes_cierra_dias_sin_ventas_tambien(tmp_path):
    """
    Un domingo sin ventas tambien debe quedar cerrado en cero -- no
    solo los dias con actividad.
    """
    cierres.cerrar_dias_pendientes(
        generado_por="perezoso", dias_hacia_atras=3, carpeta_journal=tmp_path, carpeta_cierre=tmp_path
    )

    ayer = datetime.date.today() - datetime.timedelta(days=1)
    cierre = cierres.obtener_cierre_local(ayer, tmp_path)
    assert cierre is not None
    assert cierre["total"] == 0
    assert cierre["generado_por"] == "perezoso"


def test_cerrar_dias_pendientes_no_duplica_un_dia_ya_cerrado(tmp_path):
    ayer = datetime.date.today() - datetime.timedelta(days=1)
    cierres.generar_cierre_dia(ayer, "manual", carpeta_journal=tmp_path, carpeta_cierre=tmp_path)

    cierres.cerrar_dias_pendientes(
        generado_por="perezoso", dias_hacia_atras=3, carpeta_journal=tmp_path, carpeta_cierre=tmp_path
    )

    cierre = cierres.obtener_cierre_local(ayer, tmp_path)
    assert cierre["generado_por"] == "manual"  # no lo piso el perezoso


# --------------------------------------------------- acta regenerable (#54)


def test_obtener_cierre_local_devuelve_el_ultimo_evento_cierre(tmp_path):
    fecha = datetime.date.today()
    hora = datetime.datetime.combine(fecha, datetime.time(10, 0), tzinfo=datetime.timezone.utc)
    journal.escribir_venta(_venta(hora, total=20), carpeta=tmp_path)

    cierres.generar_cierre_dia(fecha, "automatico", carpeta_journal=tmp_path, carpeta_cierre=tmp_path)
    journal.escribir_venta(_venta(hora, total=30), carpeta=tmp_path)
    regenerado = cierres.regenerar_cierre_dia(
        fecha, "regeneracion", carpeta_journal=tmp_path, carpeta_cierre=tmp_path
    )

    leido = cierres.obtener_cierre_local(fecha, tmp_path)
    assert leido["id"] == regenerado["id"]
    assert leido["total"] == 50.0
    assert leido["generado_por"] == "regeneracion"


def test_regenerar_invalida_el_estado_de_sincronizacion(tmp_path):
    fecha = datetime.date.today()
    cierres.generar_cierre_dia(fecha, "automatico", carpeta_journal=tmp_path, carpeta_cierre=tmp_path)
    cierres.marcar_sincronizado(fecha, tmp_path)
    assert cierres.obtener_cierre_local(fecha, tmp_path)["sincronizado"] is True

    cierres.regenerar_cierre_dia(
        fecha, "regeneracion", carpeta_journal=tmp_path, carpeta_cierre=tmp_path
    )
    assert cierres.obtener_cierre_local(fecha, tmp_path)["sincronizado"] is False


def test_cierre_manual_de_hoy_antes_de_la_hora_es_provisional(tmp_path, monkeypatch):
    monkeypatch.setattr(cierres, "es_antes_de_hora_cierre", lambda *a, **k: True)
    cierre = cierres.generar_cierre_dia(
        datetime.date.today(), "manual", carpeta_journal=tmp_path, carpeta_cierre=tmp_path
    )
    assert cierre["provisional"] is True


def test_cierre_automatico_nunca_es_provisional(tmp_path, monkeypatch):
    monkeypatch.setattr(cierres, "es_antes_de_hora_cierre", lambda *a, **k: True)
    cierre = cierres.generar_cierre_dia(
        datetime.date.today(), "automatico", carpeta_journal=tmp_path, carpeta_cierre=tmp_path
    )
    assert cierre["provisional"] is False


def test_cierre_manual_de_un_dia_pasado_no_es_provisional(tmp_path, monkeypatch):
    monkeypatch.setattr(cierres, "es_antes_de_hora_cierre", lambda *a, **k: True)
    ayer = datetime.date.today() - datetime.timedelta(days=1)
    cierre = cierres.generar_cierre_dia(
        ayer, "manual", carpeta_journal=tmp_path, carpeta_cierre=tmp_path
    )
    assert cierre["provisional"] is False


def test_cerrar_dias_pendientes_finaliza_un_acta_provisional_pasada(tmp_path, monkeypatch):
    ayer = datetime.date.today() - datetime.timedelta(days=1)
    hora = datetime.datetime.combine(ayer, datetime.time(18, 0), tzinfo=datetime.timezone.utc)
    journal.escribir_venta(_venta(hora, total=20), carpeta=tmp_path)

    # Un acta que quedo provisional (se forzo el cierre y se apago la PC).
    acta_provisional = cierres._construir_acta(ayer, "manual", True, carpeta_journal=tmp_path)
    cierres._escribir_linea(
        cierres._archivo_dia(ayer, tmp_path), {"evento": "cierre", **acta_provisional}
    )
    journal.escribir_venta(_venta(hora, total=80), carpeta=tmp_path)

    cierres.cerrar_dias_pendientes(
        generado_por="perezoso", dias_hacia_atras=3, carpeta_journal=tmp_path, carpeta_cierre=tmp_path
    )

    acta = cierres.obtener_cierre_local(ayer, tmp_path)
    assert acta["provisional"] is False
    assert acta["total"] == 100.0
    assert acta["generado_por"] == "perezoso"
