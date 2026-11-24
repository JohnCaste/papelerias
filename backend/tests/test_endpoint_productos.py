"""
Tests de catalogos/productos.py -- las vistas de Flask, con los
repositorios falseados. No pasan por JWT/CORS: eso es main.py, no la
logica reescrita en #11.
"""

import decimal
import io
import json

import pytest
from flask import Flask
from PIL import Image

import catalogos.productos as vista
import catalogos.imagenes as imagenes


@pytest.fixture
def app():
    app = Flask(__name__)
    app.testing = True
    return app


def test_limite_productos_usa_valores_seguros_si_query_params_son_basura(app, monkeypatch):
    capturado = {}

    def falso_listar(limite, offset):
        capturado["limite"] = limite
        capturado["offset"] = offset
        return []

    monkeypatch.setattr(vista.productos_repo, "listar", falso_listar)
    monkeypatch.setattr(vista.movimientos_repo, "stock_de_varios", lambda ids: {})

    with app.test_request_context("/api/catalogo/paginador?limit=nan&offset=-5"):
        vista.limite_productos()

    # texto invalido -> default; offset negativo -> 0, nunca revienta
    assert capturado["limite"] == 12
    assert capturado["offset"] == 0


def test_limite_productos_pasa_limit_y_offset_validos(app, monkeypatch):
    capturado = {}
    monkeypatch.setattr(
        vista.productos_repo,
        "listar",
        lambda limite, offset: capturado.update(limite=limite, offset=offset) or [],
    )
    monkeypatch.setattr(vista.movimientos_repo, "stock_de_varios", lambda ids: {})

    with app.test_request_context("/api/catalogo/paginador?limit=5&offset=10"):
        vista.limite_productos()

    assert capturado == {"limite": 5, "offset": 10}


def test_traer_productos_adjunta_stock_calculado(app, monkeypatch):
    monkeypatch.setattr(
        vista.productos_repo,
        "listar",
        lambda limite, offset: [{"id": "p1", "nombre": "Pluma"}],
    )
    monkeypatch.setattr(
        vista.movimientos_repo, "stock_de_varios", lambda ids: {"p1": 7}
    )

    with app.test_request_context("/api/catalogo"):
        respuesta = vista.traer_productos()
        data = json.loads(respuesta.get_data(as_text=True))

    assert data == [{"id": "p1", "nombre": "Pluma", "cantidad": 7}]


def test_traer_productos_convierte_numeric_de_decimal_a_number(app, monkeypatch):
    """BigQuery devuelve NUMERIC como Decimal y Flask lo serializaria como
    string -- el front espera number. Ver _con_stock / _CAMPOS_NUMERICOS."""
    monkeypatch.setattr(
        vista.productos_repo,
        "listar",
        lambda limite, offset: [
            {
                "id": "p1",
                "nombre": "Pluma",
                "precio": decimal.Decimal("294"),
                "costo": decimal.Decimal("12.50"),
                "stock_minimo": None,
            }
        ],
    )
    monkeypatch.setattr(
        vista.movimientos_repo, "stock_de_varios", lambda ids: {"p1": decimal.Decimal("7")}
    )

    with app.test_request_context("/api/catalogo"):
        respuesta = vista.traer_productos()
        data = json.loads(respuesta.get_data(as_text=True))

    assert data[0]["precio"] == 294 and isinstance(data[0]["precio"], int)
    assert data[0]["costo"] == 12.5
    assert data[0]["stock_minimo"] is None
    assert data[0]["cantidad"] == 7 and isinstance(data[0]["cantidad"], int)


# --------------------------------------------------------------------------
# Busqueda server-side (GET /api/catalogo/buscar) + total
# --------------------------------------------------------------------------


def test_buscar_productos_devuelve_items_y_total(app, monkeypatch):
    capturado = {}

    def falso_buscar_con_total(**kwargs):
        capturado["buscar"] = kwargs
        return [{"id": "p9", "nombre": "Cuaderno profesional"}], 37

    monkeypatch.setattr(vista.productos_repo, "buscar_con_total", falso_buscar_con_total)
    monkeypatch.setattr(vista.movimientos_repo, "stock_de_varios", lambda ids: {"p9": 4})

    with app.test_request_context(
        "/api/catalogo/buscar?q=cuaderno%20profesional&limit=12&offset=0"
    ):
        respuesta = vista.buscar_productos()
        data = json.loads(respuesta.get_data(as_text=True))

    assert data["total"] == 37
    assert data["items"] == [
        {"id": "p9", "nombre": "Cuaderno profesional", "cantidad": 4}
    ]
    assert capturado["buscar"]["termino"] == "cuaderno profesional"


def test_buscar_productos_devuelve_total_cero_sin_coincidencias(app, monkeypatch):
    """buscar_con_total no ejecuta una segunda consulta para el total: si no
    hay filas, el total es 0 directamente."""
    monkeypatch.setattr(
        vista.productos_repo, "buscar_con_total", lambda **kw: ([], 0)
    )
    monkeypatch.setattr(vista.movimientos_repo, "stock_de_varios", lambda ids: {})

    with app.test_request_context("/api/catalogo/buscar?q=inexistente"):
        respuesta = vista.buscar_productos()
        data = json.loads(respuesta.get_data(as_text=True))

    assert data == {"items": [], "total": 0}


def test_buscar_productos_pasa_filtros_combinados(app, monkeypatch):
    capturado = {}
    monkeypatch.setattr(
        vista.productos_repo,
        "buscar_con_total",
        lambda **kw: (capturado.update(kw) or [], 0),
    )
    monkeypatch.setattr(vista.movimientos_repo, "stock_de_varios", lambda ids: {})

    with app.test_request_context(
        "/api/catalogo/buscar?categoria=Escritura&marca=BIC&precio_max=50"
    ):
        vista.buscar_productos()

    assert capturado["categoria"] == "Escritura"
    assert capturado["marca"] == "BIC"
    assert capturado["precio_max"] == 50.0
    assert capturado["precio_min"] is None


def test_buscar_productos_ignora_params_invalidos(app, monkeypatch):
    capturado = {}
    monkeypatch.setattr(
        vista.productos_repo,
        "buscar_con_total",
        lambda **kw: (capturado.update(kw) or [], 0),
    )
    monkeypatch.setattr(vista.movimientos_repo, "stock_de_varios", lambda ids: {})

    with app.test_request_context(
        "/api/catalogo/buscar?precio_min=abc&limit=-5"
    ):
        respuesta = vista.buscar_productos()

    assert respuesta.status_code == 200
    assert capturado["precio_min"] is None
    assert capturado["limite"] == 12  # cae al default


def test_listar_categorias_devuelve_la_lista_canonica(app, monkeypatch):
    # ahora la lista viene de la tabla fija `categoria`, en su propio orden
    monkeypatch.setattr(
        vista.categorias_repo,
        "listar",
        lambda: ["Lapiceros", "Lápices", "Cuadernos"],
    )
    with app.test_request_context("/api/catalogo/categorias"):
        data = json.loads(vista.listar_categorias().get_data(as_text=True))
    assert data == ["Lapiceros", "Lápices", "Cuadernos"]


def test_listar_marcas_delega_al_repositorio(app, monkeypatch):
    monkeypatch.setattr(
        vista.productos_repo,
        "marcas_distintas",
        lambda: ["BIC", "Faber-Castell"],
    )
    with app.test_request_context("/api/catalogo/marcas"):
        data = json.loads(vista.listar_marcas().get_data(as_text=True))
    assert data == ["BIC", "Faber-Castell"]


# --------------------------------------------------------------------------
# Precio no negativo
# --------------------------------------------------------------------------


def test_agregar_productos_precio_negativo_da_400(app, monkeypatch):
    llamadas = []
    monkeypatch.setattr(
        vista.productos_repo, "crear", lambda datos: llamadas.append(datos)
    )

    with app.test_request_context(
        "/api/catalogo",
        method="POST",
        json={"nombre": "Pluma", "categoria": "papeleria", "precio": -10},
    ):
        body, status = vista.agregar_productos()

    assert status == 400
    assert "negativo" in json.loads(body.get_data(as_text=True))["error"]
    assert llamadas == []


def test_agregar_productos_precio_cero_es_valido(app, monkeypatch):
    monkeypatch.setattr(vista.productos_repo, "crear", lambda datos: {"id": "p1", **datos})
    monkeypatch.setattr(vista.movimientos_repo, "stock_de_varios", lambda ids: {})

    with app.test_request_context(
        "/api/catalogo",
        method="POST",
        json={"nombre": "Muestra", "categoria": "papeleria", "precio": 0},
    ):
        body, status = vista.agregar_productos()

    assert status == 201


def test_actualizar_productos_precio_negativo_da_400_y_no_toca_repo(app, monkeypatch):
    llamadas = []
    monkeypatch.setattr(
        vista.productos_repo, "actualizar", lambda id_, datos: llamadas.append(datos)
    )

    with app.test_request_context(
        "/api/catalogo", method="PATCH", json={"id": "p1", "precio": -1}
    ):
        body, status = vista.actualizar_productos()

    assert status == 400
    assert llamadas == []


# --------------------------------------------------------------------------
# Codigo de barras: opcional y unico entre productos activos
# --------------------------------------------------------------------------


def test_agregar_productos_con_codigo_de_barras_nuevo_ok(app, monkeypatch):
    capturado = {}
    monkeypatch.setattr(vista.productos_repo, "obtener_por_codigo_barras", lambda c: None)
    monkeypatch.setattr(
        vista.productos_repo,
        "crear",
        lambda datos: capturado.update(datos) or {"id": "p1", **datos},
    )
    monkeypatch.setattr(vista.movimientos_repo, "stock_de_varios", lambda ids: {})

    with app.test_request_context(
        "/api/catalogo",
        method="POST",
        json={
            "nombre": "Pluma",
            "categoria": "papeleria",
            "precio": 8,
            "codigo_barras": "7501234567890",
        },
    ):
        body, status = vista.agregar_productos()

    assert status == 201
    assert capturado["codigo_barras"] == "7501234567890"


def test_agregar_productos_sin_codigo_de_barras_guarda_none(app, monkeypatch):
    capturado = {}
    monkeypatch.setattr(
        vista.productos_repo,
        "crear",
        lambda datos: capturado.update(datos) or {"id": "p1", **datos},
    )
    monkeypatch.setattr(vista.movimientos_repo, "stock_de_varios", lambda ids: {})

    with app.test_request_context(
        "/api/catalogo",
        method="POST",
        json={"nombre": "Pluma", "categoria": "papeleria", "precio": 8,
              "codigo_barras": "   "},
    ):
        body, status = vista.agregar_productos()

    assert status == 201
    assert capturado["codigo_barras"] is None


def test_agregar_productos_codigo_de_barras_duplicado_da_400(app, monkeypatch):
    llamadas = []
    monkeypatch.setattr(
        vista.productos_repo,
        "obtener_por_codigo_barras",
        lambda c: {"id": "otro", "codigo_barras": c},
    )
    monkeypatch.setattr(
        vista.productos_repo, "crear", lambda datos: llamadas.append(datos)
    )

    with app.test_request_context(
        "/api/catalogo",
        method="POST",
        json={
            "nombre": "Pluma",
            "categoria": "papeleria",
            "precio": 8,
            "codigo_barras": "7501234567890",
        },
    ):
        body, status = vista.agregar_productos()

    assert status == 400
    assert "codigo de barras" in json.loads(body.get_data(as_text=True))["error"]
    assert llamadas == []


def test_actualizar_productos_conserva_su_propio_codigo_de_barras(app, monkeypatch):
    monkeypatch.setattr(
        vista.productos_repo,
        "obtener_por_codigo_barras",
        lambda c: {"id": "p1", "codigo_barras": c},  # el match es el propio producto
    )
    monkeypatch.setattr(vista.productos_repo, "actualizar", lambda id_, datos: None)
    monkeypatch.setattr(
        vista.productos_repo, "obtener_por_id", lambda id_: {"id": "p1", "nombre": "Pluma"}
    )
    monkeypatch.setattr(vista.movimientos_repo, "stock_de_varios", lambda ids: {"p1": 0})

    with app.test_request_context(
        "/api/catalogo",
        method="PATCH",
        json={"id": "p1", "codigo_barras": "7501234567890"},
    ):
        respuesta = vista.actualizar_productos()

    assert respuesta.status_code == 200


def test_actualizar_productos_codigo_de_barras_de_otro_da_400(app, monkeypatch):
    llamadas = []
    monkeypatch.setattr(
        vista.productos_repo,
        "obtener_por_codigo_barras",
        lambda c: {"id": "producto_A", "codigo_barras": c},
    )
    monkeypatch.setattr(
        vista.productos_repo, "actualizar", lambda id_, datos: llamadas.append(datos)
    )

    with app.test_request_context(
        "/api/catalogo",
        method="PATCH",
        json={"id": "producto_B", "codigo_barras": "111"},
    ):
        body, status = vista.actualizar_productos()

    assert status == 400
    assert llamadas == []


# --------------------------------------------------------------------------
# Subida de imagen: pipeline WebP + GCS (mockeado)
# --------------------------------------------------------------------------


def _png_en_memoria(tamano=(40, 40), color=(200, 10, 10)):
    buf = io.BytesIO()
    Image.new("RGB", tamano, color).save(buf, format="PNG")
    return buf.getvalue()


def test_procesar_a_webp_reduce_imagen_grande():
    grande = _png_en_memoria((4000, 3000))
    webp = imagenes.procesar_a_webp(grande)
    salida = Image.open(io.BytesIO(webp))
    assert salida.format == "WEBP"
    assert max(salida.size) == imagenes.MAX_LADO
    assert len(webp) < len(grande)


def test_procesar_a_webp_no_amplia_imagen_pequena():
    chica = _png_en_memoria((300, 300))
    salida = Image.open(io.BytesIO(imagenes.procesar_a_webp(chica)))
    assert salida.format == "WEBP"
    assert salida.size == (300, 300)


def test_procesar_a_webp_rechaza_no_imagen():
    with pytest.raises(ValueError):
        imagenes.procesar_a_webp(b"esto no es una imagen")


def test_subir_imagen_ok_devuelve_url(app, monkeypatch):
    monkeypatch.setattr(vista.imagenes, "subir_a_gcs", lambda datos: "https://cdn/x.webp")

    data = {"archivo": (io.BytesIO(_png_en_memoria()), "foto.png")}
    with app.test_request_context(
        "/api/catalogo/imagen", method="POST", data=data,
        content_type="multipart/form-data",
    ):
        respuesta = vista.subir_imagen()
        cuerpo = json.loads(respuesta.get_data(as_text=True))

    assert cuerpo == {"url": "https://cdn/x.webp"}


def test_subir_imagen_archivo_no_imagen_da_400(app):
    data = {"archivo": (io.BytesIO(b"%PDF-1.4 nope"), "doc.pdf")}
    with app.test_request_context(
        "/api/catalogo/imagen", method="POST", data=data,
        content_type="multipart/form-data",
    ):
        body, status = vista.subir_imagen()
    assert status == 400


def test_subir_imagen_demasiado_grande_da_400(app, monkeypatch):
    monkeypatch.setattr(imagenes, "MAX_SUBIDA_MB", 0)  # cualquier cosa excede
    data = {"archivo": (io.BytesIO(_png_en_memoria()), "foto.png")}
    with app.test_request_context(
        "/api/catalogo/imagen", method="POST", data=data,
        content_type="multipart/form-data",
    ):
        body, status = vista.subir_imagen()
    assert status == 400
    assert "MB" in json.loads(body.get_data(as_text=True))["error"]


def test_subir_imagen_sin_bucket_da_500(app, monkeypatch):
    def sin_bucket(datos):
        raise imagenes.BucketNoConfigurado("falta BUCKET_IMAGENES_PRODUCTO")

    monkeypatch.setattr(vista.imagenes, "subir_a_gcs", sin_bucket)
    data = {"archivo": (io.BytesIO(_png_en_memoria()), "foto.png")}
    with app.test_request_context(
        "/api/catalogo/imagen", method="POST", data=data,
        content_type="multipart/form-data",
    ):
        body, status = vista.subir_imagen()
    assert status == 500


def test_agregar_productos_sin_campos_requeridos_da_400(app, monkeypatch):
    with app.test_request_context(
        "/api/catalogo", method="POST", json={"nombre": "Pluma"}
    ):
        body, status = vista.agregar_productos()

    assert status == 400


def test_agregar_productos_crea_y_no_inserta_inventario_si_no_hay_cantidad(app, monkeypatch):
    monkeypatch.setattr(
        vista.productos_repo,
        "crear",
        lambda datos: {"id": "p1", **datos},
    )
    monkeypatch.setattr(vista.movimientos_repo, "stock_de_varios", lambda ids: {})

    llamadas_movimiento = []
    monkeypatch.setattr(
        vista.movimientos_repo, "insertar", lambda datos: llamadas_movimiento.append(datos)
    )

    with app.test_request_context(
        "/api/catalogo",
        method="POST",
        json={"nombre": "Pluma", "categoria": "papeleria", "precio": 8},
    ):
        body, status = vista.agregar_productos()

    assert status == 201
    assert llamadas_movimiento == []


def test_agregar_productos_con_cantidad_inicial_crea_movimiento(app, monkeypatch):
    monkeypatch.setattr(vista.productos_repo, "crear", lambda datos: {"id": "p1", **datos})
    monkeypatch.setattr(vista.movimientos_repo, "stock_de_varios", lambda ids: {"p1": 10})

    llamadas_movimiento = []
    monkeypatch.setattr(
        vista.movimientos_repo, "insertar", lambda datos: llamadas_movimiento.append(datos)
    )

    with app.test_request_context(
        "/api/catalogo",
        method="POST",
        json={"nombre": "Pluma", "categoria": "papeleria", "precio": 8, "cantidad": 10},
    ):
        vista.agregar_productos()

    assert len(llamadas_movimiento) == 1
    assert llamadas_movimiento[0]["tipo"] == "inventario_inicial"
    assert llamadas_movimiento[0]["cantidad"] == 10.0


def test_eliminar_productos_sin_id_da_400(app):
    with app.test_request_context("/api/catalogo"):
        body, status = vista.eliminar_productos()
    assert status == 400


def test_eliminar_productos_delega_al_repositorio(app, monkeypatch):
    llamados = []
    monkeypatch.setattr(vista.productos_repo, "eliminar", lambda id_: llamados.append(id_))

    with app.test_request_context("/api/catalogo?id=p1"):
        vista.eliminar_productos()

    assert llamados == ["p1"]


def test_actualizar_productos_sin_id_da_400(app):
    with app.test_request_context("/api/catalogo", method="PATCH", json={"nombre": "x"}):
        body, status = vista.actualizar_productos()
    assert status == 400


def test_actualizar_productos_producto_inexistente_da_404(app, monkeypatch):
    monkeypatch.setattr(vista.productos_repo, "actualizar", lambda id_, datos: None)
    monkeypatch.setattr(vista.productos_repo, "obtener_por_id", lambda id_: None)

    with app.test_request_context(
        "/api/catalogo", method="PATCH", json={"id": "p1", "nombre": "x"}
    ):
        body, status = vista.actualizar_productos()

    assert status == 404


def test_actualizar_productos_cambia_cantidad_inserta_ajuste_por_la_diferencia(
    app, monkeypatch
):
    monkeypatch.setattr(vista.productos_repo, "actualizar", lambda id_, datos: None)
    monkeypatch.setattr(
        vista.productos_repo, "obtener_por_id", lambda id_: {"id": "p1", "nombre": "Pluma"}
    )
    monkeypatch.setattr(vista.movimientos_repo, "stock_actual", lambda id_: 3)
    monkeypatch.setattr(vista.movimientos_repo, "stock_de_varios", lambda ids: {"p1": 8})

    capturado = {}
    monkeypatch.setattr(
        vista.movimientos_repo, "insertar", lambda datos: capturado.update(datos)
    )

    with app.test_request_context(
        "/api/catalogo", method="PATCH", json={"id": "p1", "cantidad": 8}
    ):
        vista.actualizar_productos()

    assert capturado["tipo"] == "ajuste"
    assert capturado["cantidad"] == 5.0  # 8 nuevo - 3 actual


def test_actualizar_productos_sin_cambiar_cantidad_no_inserta_ajuste(app, monkeypatch):
    monkeypatch.setattr(vista.productos_repo, "actualizar", lambda id_, datos: None)
    monkeypatch.setattr(
        vista.productos_repo, "obtener_por_id", lambda id_: {"id": "p1", "nombre": "Pluma"}
    )
    monkeypatch.setattr(vista.movimientos_repo, "stock_de_varios", lambda ids: {"p1": 8})

    llamados = []
    monkeypatch.setattr(vista.movimientos_repo, "insertar", lambda datos: llamados.append(datos))

    with app.test_request_context(
        "/api/catalogo", method="PATCH", json={"id": "p1", "nombre": "Pluma nueva"}
    ):
        vista.actualizar_productos()

    assert llamados == []


# --------------------------------------------------------------------------
# Espejo local del catalogo (#13): fallback a BigQuery cuando no esta
# disponible, uso del espejo cuando si -- ver _con_fallback en
# catalogos/productos.py.
# --------------------------------------------------------------------------


class _FalsoEspejo:
    def __init__(self, disponible=True):
        self._disponible = disponible

    def disponible(self):
        return self._disponible


def test_buscar_productos_usa_el_espejo_local_cuando_esta_disponible(app, monkeypatch):
    app.espejo_catalogo = _FalsoEspejo(disponible=True)

    llamado_bigquery = []
    monkeypatch.setattr(
        vista.productos_local,
        "buscar_con_total",
        lambda **kw: ([{"id": "p1", "nombre": "Local", "cantidad": 5}], 1),
    )
    monkeypatch.setattr(
        vista.productos_repo,
        "buscar_con_total",
        lambda **kw: llamado_bigquery.append(1) or ([], 0),
    )

    with app.test_request_context("/api/catalogo/buscar?q=algo"):
        respuesta = vista.buscar_productos()
        data = json.loads(respuesta.get_data(as_text=True))

    assert data == {"items": [{"id": "p1", "nombre": "Local", "cantidad": 5}], "total": 1}
    assert llamado_bigquery == []  # BigQuery NUNCA se llamo


def test_buscar_productos_cae_a_bigquery_si_el_espejo_no_esta_disponible(app, monkeypatch):
    app.espejo_catalogo = _FalsoEspejo(disponible=False)

    llamado_local = []
    monkeypatch.setattr(
        vista.productos_local,
        "buscar_con_total",
        lambda **kw: llamado_local.append(1) or ([], 0),
    )
    monkeypatch.setattr(
        vista.productos_repo,
        "buscar_con_total",
        lambda **kw: ([{"id": "p1", "nombre": "De BigQuery"}], 1),
    )
    monkeypatch.setattr(vista.movimientos_repo, "stock_de_varios", lambda ids: {"p1": 2})

    with app.test_request_context("/api/catalogo/buscar?q=algo"):
        respuesta = vista.buscar_productos()
        data = json.loads(respuesta.get_data(as_text=True))

    assert data == {
        "items": [{"id": "p1", "nombre": "De BigQuery", "cantidad": 2}],
        "total": 1,
    }
    assert llamado_local == []  # el espejo no disponible ni se intenta


def test_buscar_productos_cae_a_bigquery_si_el_espejo_lanza_excepcion(app, monkeypatch):
    app.espejo_catalogo = _FalsoEspejo(disponible=True)

    def _truena(**kw):
        raise RuntimeError("archivo corrupto")

    monkeypatch.setattr(vista.productos_local, "buscar_con_total", _truena)
    monkeypatch.setattr(
        vista.productos_repo,
        "buscar_con_total",
        lambda **kw: ([{"id": "p1", "nombre": "De BigQuery"}], 1),
    )
    monkeypatch.setattr(vista.movimientos_repo, "stock_de_varios", lambda ids: {"p1": 0})

    with app.test_request_context("/api/catalogo/buscar?q=algo"):
        respuesta = vista.buscar_productos()
        data = json.loads(respuesta.get_data(as_text=True))

    assert data["items"] == [{"id": "p1", "nombre": "De BigQuery", "cantidad": 0}]


def test_sin_espejo_asociado_a_la_app_cae_a_bigquery(app, monkeypatch):
    """Una app que nunca paso por crear_app() (como la de este archivo de
    test) no tiene 'espejo_catalogo' -- debe comportarse igual que si el
    espejo no estuviera disponible, sin reventar con AttributeError."""
    assert not hasattr(app, "espejo_catalogo")

    monkeypatch.setattr(
        vista.productos_repo,
        "buscar_con_total",
        lambda **kw: ([{"id": "p1", "nombre": "De BigQuery"}], 1),
    )
    monkeypatch.setattr(vista.movimientos_repo, "stock_de_varios", lambda ids: {"p1": 0})

    with app.test_request_context("/api/catalogo/buscar?q=algo"):
        respuesta = vista.buscar_productos()
        assert respuesta.status_code == 200


def test_limite_productos_usa_el_espejo_local_cuando_esta_disponible(app, monkeypatch):
    app.espejo_catalogo = _FalsoEspejo(disponible=True)

    llamado_bigquery = []
    monkeypatch.setattr(
        vista.productos_local,
        "listar",
        lambda limite, offset: [{"id": "p1", "nombre": "Local", "cantidad": 1}],
    )
    monkeypatch.setattr(
        vista.productos_repo,
        "listar",
        lambda limite, offset: llamado_bigquery.append(1) or [],
    )

    with app.test_request_context("/api/catalogo/paginador"):
        respuesta = vista.limite_productos()
        data = json.loads(respuesta.get_data(as_text=True))

    assert data == [{"id": "p1", "nombre": "Local", "cantidad": 1}]
    assert llamado_bigquery == []


def test_listar_categorias_usa_el_espejo_local_cuando_esta_disponible(app, monkeypatch):
    app.espejo_catalogo = _FalsoEspejo(disponible=True)

    llamado_bigquery = []
    monkeypatch.setattr(vista.productos_local, "listar_categorias", lambda: ["Local"])
    monkeypatch.setattr(
        vista.categorias_repo, "listar", lambda: llamado_bigquery.append(1) or []
    )

    with app.test_request_context("/api/catalogo/categorias"):
        data = json.loads(vista.listar_categorias().get_data(as_text=True))

    assert data == ["Local"]
    assert llamado_bigquery == []


def test_listar_marcas_usa_el_espejo_local_cuando_esta_disponible(app, monkeypatch):
    app.espejo_catalogo = _FalsoEspejo(disponible=True)

    llamado_bigquery = []
    monkeypatch.setattr(vista.productos_local, "marcas_distintas", lambda: ["Local"])
    monkeypatch.setattr(
        vista.productos_repo, "marcas_distintas", lambda: llamado_bigquery.append(1) or []
    )

    with app.test_request_context("/api/catalogo/marcas"):
        data = json.loads(vista.listar_marcas().get_data(as_text=True))

    assert data == ["Local"]
    assert llamado_bigquery == []
