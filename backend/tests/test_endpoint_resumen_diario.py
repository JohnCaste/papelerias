"""
Tests de la captura manual del resumen diario (pantalla de Ventas):

  - ventas/resumen_diario.py       -- vista Flask, validacion del cuerpo
  - acceso_datos/repositorios/resumen_diario.py -- reconciliacion, con
    `ejecutar_query` e `insertar_filas` falseados (no toca BigQuery).
"""

import datetime
import json

import pytest
from flask import Flask

import ventas.resumen_diario as vista
import acceso_datos.repositorios.resumen_diario as repo
import acceso_datos.repositorios.gasto_dia as gasto_repo
from utilidades import categorias

HOY = vista._hoy_negocio()
AYER = HOY - datetime.timedelta(days=1)

# Referencia a la implementacion real, capturada antes de que el
# autouse `_sin_gasto_real` la reemplace -- la usa el test que prueba
# gasto_dia.guardar() de verdad (con BigQuery falseado a su propio
# nivel, no con el espia generico).
_GASTO_REPO_GUARDAR_REAL = gasto_repo.guardar


# ============================================================ vista Flask

@pytest.fixture
def app():
    app = Flask(__name__)
    app.testing = True
    return app


@pytest.fixture(autouse=True)
def _identidad(monkeypatch):
    monkeypatch.setattr(vista, "get_jwt_identity", lambda: "u1")


@pytest.fixture(autouse=True)
def _sin_gasto_real(monkeypatch):
    """
    Red de seguridad para TODO este archivo: `guardar_resumen_dia` llama
    a `gasto_repo.guardar` ademas de `repo.guardar` -- sin esto, los
    tests que no les interesa el gasto intentarian una llamada real a
    BigQuery. Los tests dedicados a gasto pisan esto con su propio espia.
    """
    monkeypatch.setattr(
        gasto_repo, "guardar", lambda fecha, monto, usuario_id: {"fecha": fecha.isoformat(), "monto": monto}
    )


def _post(app, body):
    with app.test_request_context("/api/ventas/resumen-dia", method="POST", json=body):
        resp = vista.guardar_resumen_dia()
    if isinstance(resp, tuple):
        return json.loads(resp[0].get_data(as_text=True)), resp[1]
    return json.loads(resp.get_data(as_text=True)), 200


def _get_gasto(app, fecha_texto):
    with app.test_request_context(f"/api/ventas/gasto-dia?fecha={fecha_texto}", method="GET"):
        resp = vista.obtener_gasto_dia()
    if isinstance(resp, tuple):
        return json.loads(resp[0].get_data(as_text=True)), resp[1]
    return json.loads(resp.get_data(as_text=True)), 200


@pytest.fixture
def espia_guardar(monkeypatch):
    llamadas = []

    def falso(fecha, objetivo, usuario_id=None):
        llamadas.append({"fecha": fecha, "objetivo": objetivo, "usuario_id": usuario_id})
        return {"fecha": fecha.isoformat(), "total": sum(objetivo.values()), "categorias": []}

    monkeypatch.setattr(repo, "guardar", falso)
    return llamadas


def test_guardado_valido_llama_al_repo_con_todas_las_claves(app, espia_guardar):
    data, status = _post(
        app,
        {
            "fecha": AYER.isoformat(),
            "categorias": [{"clave": "copias", "monto": 120}, {"clave": "dulces", "monto": 80}],
        },
    )
    assert status == 200
    assert len(espia_guardar) == 1
    objetivo = espia_guardar[0]["objetivo"]
    # El objetivo viaja SIEMPRE con la lista canonica completa: lo que el
    # modal no mande cuenta como cero, que es lo que hace que el resumen
    # sea la autoridad del dia y no un ajuste.
    assert set(objetivo) == set(categorias.CLAVES)
    assert objetivo["copias"] == 120.0
    assert objetivo["dulces"] == 80.0
    assert all(objetivo[c] == 0.0 for c in categorias.CLAVES if c not in ("copias", "dulces"))
    assert espia_guardar[0]["usuario_id"] == "u1"


def test_clave_legada_productos_se_pliega_a_papeleria(app, espia_guardar):
    _post(app, {"fecha": AYER.isoformat(), "categorias": [{"clave": "productos", "monto": 50}]})
    assert espia_guardar[0]["objetivo"]["papeleria"] == 50.0


def test_fecha_invalida_da_400(app, espia_guardar):
    _, status = _post(app, {"fecha": "ayer", "categorias": []})
    assert status == 400
    assert espia_guardar == []


def test_fecha_de_hace_dos_anios_da_400(app, espia_guardar):
    vieja = HOY.replace(year=HOY.year - 2)
    _, status = _post(app, {"fecha": vieja.isoformat(), "categorias": []})
    assert status == 400
    assert espia_guardar == []


def test_dia_en_curso_da_400(app, espia_guardar):
    _, status = _post(app, {"fecha": HOY.isoformat(), "categorias": [{"clave": "copias", "monto": 10}]})
    assert status == 400
    assert espia_guardar == []


def test_dia_futuro_da_400(app, espia_guardar):
    manana = HOY + datetime.timedelta(days=1)
    _, status = _post(app, {"fecha": manana.isoformat(), "categorias": [{"clave": "copias", "monto": 10}]})
    assert status == 400
    assert espia_guardar == []


def test_anio_anterior_se_acepta(app, espia_guardar):
    anterior = datetime.date(HOY.year - 1, 6, 15)
    _, status = _post(app, {"fecha": anterior.isoformat(), "categorias": [{"clave": "copias", "monto": 10}]})
    assert status == 200


def test_categoria_invalida_da_400(app, espia_guardar):
    _, status = _post(app, {"fecha": AYER.isoformat(), "categorias": [{"clave": "juguetes", "monto": 50}]})
    assert status == 400
    assert espia_guardar == []


def test_monto_negativo_da_400(app, espia_guardar):
    _, status = _post(app, {"fecha": AYER.isoformat(), "categorias": [{"clave": "copias", "monto": -10}]})
    assert status == 400
    assert espia_guardar == []


def test_monto_no_numerico_da_400(app, espia_guardar):
    _, status = _post(app, {"fecha": AYER.isoformat(), "categorias": [{"clave": "copias", "monto": "abc"}]})
    assert status == 400


def test_categorias_no_lista_da_400(app, espia_guardar):
    _, status = _post(app, {"fecha": AYER.isoformat(), "categorias": {"copias": 10}})
    assert status == 400


# ==================================================== repo.guardar()

@pytest.fixture
def bigquery_falso(monkeypatch):
    """
    Falsea las dos lecturas (`base_por_categoria`, `capturas_manuales`) y
    captura lo que se manda a `insertar_filas`.
    """
    estado = {"base_rows": [], "manual_rows": [], "insertado": []}

    def falso_ejecutar_query(sql, valores=None, tipos=None, **kw):
        if "UNNEST(v.lineas)" in sql:
            return list(estado["base_rows"])
        return list(estado["manual_rows"])

    monkeypatch.setattr(repo, "ejecutar_query", falso_ejecutar_query)
    monkeypatch.setattr(repo, "insertar_filas", lambda tabla, filas: estado["insertado"].extend(filas))
    return estado


def _objetivo(**kw):
    base = {cat: 0.0 for cat in repo.CATEGORIAS}
    base.update(kw)
    return base


def test_dia_sin_registro_inserta_una_venta_con_el_total(bigquery_falso):
    resumen = repo.guardar(HOY, _objetivo(copias=120, dulces=80), "u1")

    assert resumen["total"] == 200
    assert len(bigquery_falso["insertado"]) == 1
    venta = bigquery_falso["insertado"][0]
    assert venta["origen"] == "resumen_manual"
    assert venta["metodo_pago"] == "resumen_manual"
    assert venta["total"] == 200
    montos = {l["categoria"]: l["subtotal"] for l in venta["lineas"]}
    assert montos == {"copias": 120, "dulces": 80}


def test_dia_con_ventas_pos_solo_ajusta_la_diferencia(bigquery_falso):
    bigquery_falso["base_rows"] = [{"clave": "papeleria", "monto": 300}]

    resumen = repo.guardar(HOY, _objetivo(papeleria=500), "u1")

    assert resumen["total"] == 500
    venta = bigquery_falso["insertado"][0]
    assert [(l["categoria"], l["subtotal"]) for l in venta["lineas"]] == [("papeleria", 200)]


def test_reguardar_revierte_la_captura_previa_y_no_duplica(bigquery_falso):
    bigquery_falso["manual_rows"] = [
        {
            "id": "manual-1",
            "total": 200,
            "venta_original_id": None,
            "lineas": [
                {"tipo": "categoria", "categoria": "copias", "cantidad": 1,
                 "precio_unitario": 200, "subtotal": 200},
            ],
        }
    ]

    repo.guardar(AYER, _objetivo(copias=200), "u1")

    insertado = bigquery_falso["insertado"]
    assert len(insertado) == 2
    reversion = next(f for f in insertado if f["venta_original_id"] == "manual-1")
    nueva = next(f for f in insertado if f["venta_original_id"] is None)
    assert reversion["total"] == -200
    assert nueva["total"] == 200
    # neto del dia: 200 (previa) - 200 (reversion) + 200 (nueva) = 200
    assert 200 + reversion["total"] + nueva["total"] == 200
    # la reversion cae en el dia EDITADO, no en el dia en curso: si no,
    # el neto negativo descuenta de "hoy" en las agregaciones (que agrupan
    # por DATE(fecha_hora, zona)).
    assert reversion["fecha_hora"].date() == AYER
    assert nueva["fecha_hora"].date() == AYER


def test_guardar_todo_en_cero_revierte_y_no_inserta_captura(bigquery_falso):
    bigquery_falso["manual_rows"] = [
        {
            "id": "manual-1",
            "total": 200,
            "venta_original_id": None,
            "lineas": [
                {"tipo": "categoria", "categoria": "copias", "cantidad": 1,
                 "precio_unitario": 200, "subtotal": 200},
            ],
        }
    ]

    resumen = repo.guardar(HOY, _objetivo(), "u1")

    assert resumen["total"] == 0
    insertado = bigquery_falso["insertado"]
    assert len(insertado) == 1
    assert insertado[0]["venta_original_id"] == "manual-1"
    assert insertado[0]["total"] == -200


def test_sin_cambios_y_sin_captura_previa_no_escribe_nada(bigquery_falso):
    resumen = repo.guardar(HOY, _objetivo(), "u1")
    assert resumen["total"] == 0
    assert bigquery_falso["insertado"] == []


def test_no_revierte_una_captura_ya_revertida(bigquery_falso):
    bigquery_falso["manual_rows"] = [
        {"id": "manual-1", "total": 200, "venta_original_id": None,
         "lineas": [{"tipo": "categoria", "categoria": "copias", "cantidad": 1,
                     "precio_unitario": 200, "subtotal": 200}]},
        {"id": "rev-1", "total": -200, "venta_original_id": "manual-1", "lineas": []},
    ]

    repo.guardar(HOY, _objetivo(copias=200), "u1")

    # manual-1 ya estaba revertida: no se vuelve a revertir, solo se inserta la nueva
    insertado = bigquery_falso["insertado"]
    assert [f["venta_original_id"] for f in insertado] == [None]
    assert insertado[0]["total"] == 200


def test_pliega_claves_legadas_en_la_base(bigquery_falso):
    bigquery_falso["base_rows"] = [
        {"clave": "productos", "monto": 100},
        {"clave": "hojas", "monto": 50},
    ]

    base = repo.base_por_categoria(HOY)
    assert base["papeleria"] == 100
    assert base["copias"] == 50


def test_instante_es_mediodia_utc_del_dia_pedido(bigquery_falso):
    inst = repo._instante(datetime.date(2026, 3, 10))
    assert (inst.year, inst.month, inst.day, inst.hour) == (2026, 3, 10, 18)
    assert inst.tzinfo == datetime.timezone.utc


# ==================================================== columna "Gastos" (gasto_dia)

@pytest.fixture
def espia_guardar_gasto(monkeypatch, espia_guardar):
    llamadas = []

    def falso(fecha, monto, usuario_id):
        llamadas.append({"fecha": fecha, "monto": monto, "usuario_id": usuario_id})
        return {"fecha": fecha.isoformat(), "monto": monto}

    monkeypatch.setattr(gasto_repo, "guardar", falso)
    return llamadas


def test_guardar_resumen_dia_persiste_el_gasto(app, espia_guardar_gasto):
    data, status = _post(
        app,
        {"fecha": AYER.isoformat(), "categorias": [{"clave": "papeleria", "monto": 300}], "gasto": 45},
    )
    assert status == 200
    assert len(espia_guardar_gasto) == 1
    assert espia_guardar_gasto[0] == {"fecha": AYER, "monto": 45.0, "usuario_id": "u1"}
    assert data["gasto"] == 45.0


def test_gasto_es_opcional_y_por_defecto_es_cero(app, espia_guardar_gasto):
    data, status = _post(app, {"fecha": AYER.isoformat(), "categorias": []})
    assert status == 200
    assert espia_guardar_gasto[0]["monto"] == 0.0
    assert data["gasto"] == 0.0


def test_gasto_negativo_da_400_y_no_guarda_nada(app, espia_guardar, espia_guardar_gasto):
    _, status = _post(
        app, {"fecha": AYER.isoformat(), "categorias": [{"clave": "papeleria", "monto": 100}], "gasto": -5}
    )
    assert status == 400
    assert espia_guardar_gasto == []


def test_gasto_no_numerico_da_400(app, espia_guardar_gasto):
    _, status = _post(
        app, {"fecha": AYER.isoformat(), "categorias": [], "gasto": "mucho"}
    )
    assert status == 400


def test_obtener_gasto_dia_devuelve_lo_guardado(app, monkeypatch):
    monkeypatch.setattr(gasto_repo, "obtener", lambda fecha: 45.0)
    data, status = _get_gasto(app, AYER.isoformat())
    assert status == 200
    assert data == {"fecha": AYER.isoformat(), "gasto": 45.0}


def test_obtener_gasto_dia_sin_registro_devuelve_cero(app, monkeypatch):
    monkeypatch.setattr(gasto_repo, "obtener", lambda fecha: 0.0)
    data, status = _get_gasto(app, AYER.isoformat())
    assert data["gasto"] == 0.0


def test_obtener_gasto_dia_del_dia_en_curso_da_400(app, monkeypatch):
    monkeypatch.setattr(gasto_repo, "obtener", lambda fecha: 0.0)
    _, status = _get_gasto(app, HOY.isoformat())
    assert status == 400


def test_gasto_dia_repo_guarda_y_lee_lo_ultimo(monkeypatch):
    """
    acceso_datos/repositorios/gasto_dia.py, con BigQuery falseado: la
    ULTIMA fila por fecha es la que gana (append-only, sin UPDATE).
    """
    monkeypatch.setattr(gasto_repo, "guardar", _GASTO_REPO_GUARDAR_REAL)
    filas = []

    def falso_ejecutar_uno(sql, valores=None, tipos=None, **kw):
        de_la_fecha = [f for f in filas if f["fecha"] == valores["fecha"]]
        if not de_la_fecha:
            return None
        return max(de_la_fecha, key=lambda f: f["generado_en"])

    monkeypatch.setattr(gasto_repo, "ejecutar_uno", falso_ejecutar_uno)
    monkeypatch.setattr(gasto_repo, "insertar_filas", lambda tabla, nuevas: filas.extend(nuevas))

    assert gasto_repo.obtener(AYER) == 0.0

    gasto_repo.guardar(AYER, 30, "u1")
    assert gasto_repo.obtener(AYER) == 30.0

    gasto_repo.guardar(AYER, 50, "u1")
    assert gasto_repo.obtener(AYER) == 50.0
