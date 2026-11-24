"""
Tests de esquema/migrar_cuentas.py (migracion #10) -- sin BigQuery real.

Se parchean las funciones de I/O del modulo (`_leer_legado`,
`_contar_migradas`, `_cuadre_legado_por_anio`, `insertar_filas`); la
logica de transformacion se prueba directa.
"""

import datetime

import pytest

import esquema.migrar_cuentas as mig


def _fila(**overrides):
    """Fila legada de `nuevas_tablas.cuentas` con valores por defecto."""
    fila = {
        "id": "leg-1",
        "papeleria": None,
        "telefono": None,
        "copias": 0.0,
        "dulces": 0.0,
        "helados": 0.0,
        "recargas": 0.0,
        "productos": 0.0,
        "fecha": datetime.date(2024, 1, 1),
    }
    fila.update(overrides)
    return fila


@pytest.fixture
def stub_io(monkeypatch):
    """Aisla el modulo de BigQuery. Devuelve un dict con lo capturado."""
    capturado = {"insertadas": None}

    monkeypatch.setattr(mig, "_contar_migradas", lambda: 0)
    # El cuadre anual tiene sus propios tests; aqui solo interesa la insercion.
    monkeypatch.setattr(mig, "_verificar_cuadre_anual", lambda ventas: None)

    def falso_insertar(tabla, filas, cliente=None):
        capturado["insertadas"] = filas

    monkeypatch.setattr(mig, "insertar_filas", falso_insertar)
    return capturado


# --------------------------------------------------------------- _lineas_de / _venta_de

def test_fila_con_varias_categorias_produce_una_venta():
    fila = _fila(
        id="abc",
        fecha=datetime.date(2024, 1, 1),
        productos=259.0,
        copias=23.0,
        dulces=204.0,
        helados=57.0,
        recargas=150.0,
    )

    venta = mig._venta_de(fila)

    assert venta["id"] == "migracion-abc"
    assert venta["fecha_hora"] == datetime.datetime(
        2024, 1, 1, tzinfo=datetime.timezone.utc
    )
    assert venta["total"] == 693.0
    assert venta["detallada"] is False
    assert venta["origen"] == "migracion"
    assert venta["estado"] == "activa"
    assert venta["extemporanea"] is False
    assert len(venta["lineas"]) == 5
    assert sum(linea["subtotal"] for linea in venta["lineas"]) == venta["total"]


def test_solo_se_materializan_categorias_con_monto():
    fila = _fila(productos=456.0, copias=567.0, dulces=None, helados=None, recargas=None)

    venta = mig._venta_de(fila)

    categorias = {linea["categoria"] for linea in venta["lineas"]}
    assert categorias == {"productos", "copias"}
    for linea in venta["lineas"]:
        assert linea["tipo"] == "categoria"
        assert linea["cantidad"] == 1
        assert linea["precio_unitario"] == linea["subtotal"]
        assert linea["producto_id"] is None
        assert linea["servicio_id"] is None


def test_descripcion_es_el_nombre_legible():
    fila = _fila(copias=10.0)
    venta = mig._venta_de(fila)
    assert venta["lineas"][0]["descripcion"] == "Copias"


def test_fila_sin_montos_no_genera_venta():
    assert mig._venta_de(_fila()) is None


def test_fila_sin_fecha_no_genera_venta():
    assert mig._venta_de(_fila(fecha=None, productos=100.0)) is None


def test_valores_centinela():
    venta = mig._venta_de(_fila(productos=100.0))
    assert venta["metodo_pago"] == "desconocido"
    assert venta["usuario_id"] == "sistema"


def test_id_determinista_a_partir_del_id_legado():
    a = mig._venta_de(_fila(id="xyz", productos=1.0))
    b = mig._venta_de(_fila(id="xyz", productos=1.0))
    assert a["id"] == b["id"] == "migracion-xyz"


def test_montos_negativos_pasan_como_linea():
    venta = mig._venta_de(_fila(productos=100.0, copias=-30.0))
    montos = {linea["categoria"]: linea["subtotal"] for linea in venta["lineas"]}
    assert montos == {"productos": 100.0, "copias": -30.0}
    assert venta["total"] == 70.0


# --------------------------------------------------------------- migrar()

def test_migrar_inserta_solo_las_filas_con_venta(stub_io, monkeypatch, capsys):
    legado = [
        _fila(id="con-monto", productos=375.0),
        _fila(id="en-cero"),  # todas las categorias en 0
        _fila(id="sin-fecha", fecha=None, productos=10.0),
    ]
    monkeypatch.setattr(mig, "_leer_legado", lambda: legado)

    mig.migrar()

    ids = [v["id"] for v in stub_io["insertadas"]]
    assert ids == ["migracion-con-monto"]

    salida = capsys.readouterr().out
    assert "1 filas a insertar" in salida
    assert "descartadas sin fecha: 1" in salida
    assert "descartadas sin categorias con monto: 1" in salida


def test_migrar_aborta_si_ya_hay_migradas_sin_forzar(stub_io, monkeypatch):
    monkeypatch.setattr(mig, "_contar_migradas", lambda: 3)
    monkeypatch.setattr(mig, "_leer_legado", lambda: [])

    with pytest.raises(SystemExit) as exc:
        mig.migrar()

    assert "no deduplica" in str(exc.value)
    assert stub_io["insertadas"] is None


def test_migrar_forzar_ignora_las_migradas_existentes(stub_io, monkeypatch):
    monkeypatch.setattr(mig, "_contar_migradas", lambda: 3)
    monkeypatch.setattr(mig, "_leer_legado", lambda: [_fila(id="x", productos=5.0)])

    mig.migrar(forzar=True)

    assert [v["id"] for v in stub_io["insertadas"]] == ["migracion-x"]


def test_dry_run_no_escribe(stub_io, monkeypatch, capsys):
    monkeypatch.setattr(mig, "_leer_legado", lambda: [_fila(id="x", productos=5.0)])

    mig.migrar(dry_run=True)

    assert stub_io["insertadas"] is None
    assert "--dry-run: no se escribio nada." in capsys.readouterr().out


# --------------------------------------------------------------- cuadre anual

def test_cuadre_anual_ok_no_revienta(monkeypatch, capsys):
    ventas = [
        mig._venta_de(_fila(id="a", fecha=datetime.date(2024, 5, 1), productos=100.0)),
        mig._venta_de(_fila(id="b", fecha=datetime.date(2026, 5, 1), productos=50.0)),
    ]
    monkeypatch.setattr(mig, "_cuadre_legado_por_anio", lambda: {2024: 100.0, 2026: 50.0})

    mig._verificar_cuadre_anual(ventas)

    assert "Cuadre anual OK" in capsys.readouterr().out


def test_cuadre_anual_detecta_un_anio_que_no_cuadra(monkeypatch, capsys):
    ventas = [
        mig._venta_de(_fila(id="a", fecha=datetime.date(2024, 5, 1), productos=100.0)),
    ]
    monkeypatch.setattr(mig, "_cuadre_legado_por_anio", lambda: {2024: 123.0})

    with pytest.raises(SystemExit) as exc:
        mig._verificar_cuadre_anual(ventas)

    mensaje = str(exc.value)
    assert "2024" in mensaje
    assert "dif" in mensaje
    assert "DESCUADRE" in capsys.readouterr().out
