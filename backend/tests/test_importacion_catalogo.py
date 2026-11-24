"""
Importacion de catalogo desde Excel/CSV (openspec/changes/importacion-catalogo-excel):
validacion compartida, repositorio en lote, lectura de archivos, validacion
de lote, confirmacion, plantilla y endpoints (rol dueno).

Nunca toca BigQuery: los repositorios se falsean y, donde importa, las
funciones de escritura revientan si alguien las llama.
"""

import io

import pytest
from flask_jwt_extended import create_access_token
from openpyxl import Workbook, load_workbook

import acceso_datos.repositorios.productos as productos_repo
import catalogos.importacion as importacion
import catalogos.validacion_producto as validacion
import main as modulo_main

CATEGORIAS = ["Lapiceros", "Lápices", "Cuadernos", "Escolar"]


def _xlsx(filas) -> bytes:
    libro = Workbook()
    hoja = libro.active
    for fila in filas:
        hoja.append(fila)
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


def _validar(filas, existentes=(), nombres=()):
    return importacion.validar_lote(
        filas,
        categorias=CATEGORIAS,
        codigos_existentes=set(existentes),
        nombres_existentes=list(nombres),
    )


def _f(fila, **datos):
    base = {"nombre": "Cuaderno", "categoria": "Cuadernos", "precio": 30}
    base.update(datos)
    return {"fila": fila, "datos": base}


# =========================================================== validacion


@pytest.mark.parametrize(
    "valor, esperado",
    [("$1,234.50", 1234.5), ("1,234", 1234.0), ("12,5", 12.5), (" 45 ", 45.0), (7, 7.0)],
)
def test_a_numero_tolerante(valor, esperado):
    assert validacion.a_numero(valor, tolerante=True) == esperado


@pytest.mark.parametrize("valor", ["abc", "1,2,3", "12,345.6.7", True])
def test_a_numero_rechaza_ambiguos(valor):
    with pytest.raises(ValueError):
        validacion.a_numero(valor, tolerante=True)


def test_precio_negativo_y_texto():
    assert validacion.error_precio(-10) == "El precio no puede ser negativo"
    assert validacion.error_precio("abc") == "El precio no es un numero valido"
    assert validacion.error_precio(0) is None
    assert validacion.error_precio("") is None


def test_categoria_tolerante_a_acentos_y_espacios():
    mapa = validacion.mapa_categorias(CATEGORIAS)
    assert validacion.resolver_categoria("escolar ", mapa) == ("Escolar", None)
    assert validacion.resolver_categoria("LAPICES", mapa) == ("Lápices", None)
    assert validacion.resolver_categoria("Juguetería", mapa)[1] == 'La categoria "Juguetería" no existe'


def test_codigos_numericos_y_vacios():
    assert validacion.normalizar_codigo(7501234567890.0) == "7501234567890"
    assert validacion.normalizar_codigo(7501234567890) == "7501234567890"
    assert validacion.normalizar_codigo("  ") is None
    assert validacion.normalizar_codigo(None) is None


def test_varios_errores_en_una_fila():
    _, errores = validacion.validar_fila({"categoria": "Escolar", "precio": "abc"}, validacion.mapa_categorias(CATEGORIAS))
    assert "Falta el nombre" in errores
    assert "El precio no es un numero valido" in errores


def test_cantidad_negativa_en_femenino():
    _, errores = validacion.validar_fila(
        {"nombre": "x", "categoria": "Escolar", "precio": 1, "cantidad": -1},
        validacion.mapa_categorias(CATEGORIAS),
    )
    assert errores == ["La cantidad no puede ser negativa"]


# =========================================================== repositorio


def test_crear_varios_inserta_en_bloques(monkeypatch):
    llamadas = []
    monkeypatch.setattr(productos_repo, "insertar_filas", lambda tabla, filas: llamadas.append((tabla, len(filas))))
    creados = productos_repo.crear_varios(
        [{"nombre": f"p{i}", "categoria": "Escolar", "precio": 1} for i in range(1100)]
    )
    assert [n for _, n in llamadas] == [500, 500, 100]
    assert all(tabla == productos_repo.TABLA for tabla, _ in llamadas)
    assert productos_repo.TABLA.endswith(".producto")
    assert len({p["id"] for p in creados}) == 1100
    assert all(p["activo"] is True for p in creados)


def test_crear_varios_reporta_hasta_donde_llego(monkeypatch):
    llamadas = {"n": 0}

    def falso(tabla, filas):
        llamadas["n"] += 1
        if llamadas["n"] == 2:
            raise RuntimeError("sin red")

    monkeypatch.setattr(productos_repo, "insertar_filas", falso)
    with pytest.raises(productos_repo.ErrorInsercionParcial) as error:
        productos_repo.crear_varios([{"nombre": "p", "categoria": "Escolar", "precio": 1}] * 700)
    assert len(error.value.creados) == 500


def test_codigos_barras_existentes_una_consulta(monkeypatch):
    capturado = {}

    def falso(sql, valores=None, tipos=None):
        capturado.update(sql=sql, valores=valores, tipos=tipos)
        return [{"codigo_barras": "111"}]

    monkeypatch.setattr(productos_repo, "ejecutar_query", falso)
    assert productos_repo.codigos_barras_existentes(["222", "111", None, "111"]) == {"111"}
    assert "IN UNNEST(@codigos)" in capturado["sql"]
    assert "activo = TRUE" in capturado["sql"]
    assert capturado["valores"] == {"codigos": ["111", "222"]}


def test_codigos_barras_existentes_sin_codigos_no_consulta(monkeypatch):
    monkeypatch.setattr(productos_repo, "ejecutar_query", lambda *a, **k: pytest.fail("no debe consultar"))
    assert productos_repo.codigos_barras_existentes([None, ""]) == set()


# ============================================================== lectura


def test_xlsx_encabezados_con_acentos_y_en_otro_orden():
    contenido = _xlsx(
        [["Precio", "Categoría", "Nombre", "Código de barras", "Color"], [12, "escolar", "Lápiz", 7501234567890]]
    )
    filas, advertencias = importacion.leer_archivo("lista.xlsx", contenido)
    assert filas == [
        {"fila": 2, "datos": {"precio": 12, "categoria": "escolar", "nombre": "Lápiz", "codigo_barras": "7501234567890"}}
    ]
    assert advertencias == ["Se ignoraron las columnas: Color"]


def test_xlsx_ignora_filas_vacias_y_conserva_numero_de_fila():
    contenido = _xlsx([["nombre", "categoria", "precio"], ["A", "Escolar", 1], [None, None, None], ["B", "Escolar", 2]])
    filas, _ = importacion.leer_archivo("x.xlsx", contenido)
    assert [f["fila"] for f in filas] == [2, 4]


def test_falta_columna_requerida():
    with pytest.raises(importacion.ErrorArchivo, match="precio"):
        importacion.leer_archivo("x.xlsx", _xlsx([["nombre", "categoria"], ["A", "Escolar"]]))


def test_tipo_no_soportado():
    with pytest.raises(importacion.ErrorArchivo, match=r"\.xlsx y \.csv"):
        importacion.leer_archivo("lista.pdf", b"%PDF")


def test_xlsx_corrupto():
    with pytest.raises(importacion.ErrorArchivo, match="No se pudo leer"):
        importacion.leer_archivo("x.xlsx", b"no soy un zip")


def test_limite_de_filas():
    filas = [["nombre", "categoria", "precio"]] + [["A", "Escolar", 1]] * (importacion.MAX_FILAS + 1)
    with pytest.raises(importacion.ErrorArchivo, match="2000"):
        importacion.leer_archivo("x.xlsx", _xlsx(filas))


def test_limite_de_tamano():
    with pytest.raises(importacion.ErrorArchivo, match="5 MB"):
        importacion.leer_archivo("x.csv", b"a" * (importacion.MAX_BYTES + 1))


def test_csv_utf8_con_bom():
    contenido = "Nombre,Categoría,Precio\nLápiz,Escolar,5\n".encode("utf-8-sig")
    filas, _ = importacion.leer_archivo("x.csv", contenido)
    assert filas[0]["datos"] == {"nombre": "Lápiz", "categoria": "Escolar", "precio": "5"}


def test_csv_punto_y_coma_en_cp1252():
    contenido = "nombre;categoria;precio;codigo\nLápiz;Escolar;12,5;0750\n".encode("cp1252")
    filas, _ = importacion.leer_archivo("x.csv", contenido)
    assert filas[0]["datos"]["nombre"] == "Lápiz"
    assert filas[0]["datos"]["precio"] == "12,5"
    assert filas[0]["datos"]["codigo_barras"] == "0750"


def test_csv_de_errores_resubido_no_avisa_columna_error():
    contenido = b"fila,nombre,categoria,precio,error\n3,A,Escolar,1,algo\n"
    _, advertencias = importacion.leer_archivo("errores.csv", contenido)
    assert advertencias == []


# ======================================================= validar lote


def test_todo_valido():
    r = _validar([_f(2), _f(3, nombre="Lapiz"), _f(4, nombre="Goma")])
    assert (r["total"], len(r["validas"]), len(r["errores"])) == (3, 3, 0)


def test_categoria_normalizada_al_canonico():
    r = _validar([_f(2, categoria="escolar ")])
    assert r["validas"][0]["producto"]["categoria"] == "Escolar"


def test_precio_negativo_fila_5():
    r = _validar([_f(5, precio=-10)])
    assert r["errores"] == [{"fila": 5, "datos": _f(5, precio=-10)["datos"], "motivos": ["El precio no puede ser negativo"]}]


def test_codigo_en_uso_es_error():
    r = _validar([_f(2, codigo_barras="111")], existentes={"111"})
    assert r["errores"][0]["motivos"] == ["El codigo de barras ya esta en uso"]


def test_codigo_repetido_en_archivo_marca_ambas_filas():
    r = _validar([_f(3, codigo_barras="9"), _f(5, nombre="otro"), _f(9, nombre="x", codigo_barras="9")])
    motivos = {e["fila"]: e["motivos"] for e in r["errores"]}
    assert motivos == {
        3: ["El codigo de barras se repite en el archivo (filas 3 y 9)"],
        9: ["El codigo de barras se repite en el archivo (filas 3 y 9)"],
    }
    assert [v["fila"] for v in r["validas"]] == [5]


def test_posible_duplicado_por_nombre_sin_codigo():
    r = _validar([_f(2, nombre="CUADERNO  profesional")], nombres=["Cuaderno profesional"])
    assert r["validas"][0]["advertencias"] == ["Posible duplicado por nombre"]
    r = _validar([_f(2, nombre="Cuaderno profesional", codigo_barras="1")], nombres=["Cuaderno profesional"])
    assert r["validas"][0]["advertencias"] == []


def test_sucursal_sin_categorias_avisa():
    r = importacion.validar_lote([_f(2)], categorias=[], codigos_existentes=set(), nombres_existentes=[])
    assert r["errores"] and "no tiene categorias" in r["advertencias"][0]


def test_validar_lote_hace_las_consultas_en_bloque(monkeypatch):
    llamadas = []
    monkeypatch.setattr(importacion, "_categorias_vigentes", lambda: llamadas.append("cat") or CATEGORIAS)
    monkeypatch.setattr(importacion.productos_repo, "codigos_barras_existentes", lambda c: llamadas.append("cod") or set())
    monkeypatch.setattr(importacion.productos_repo, "nombres_activos", lambda: llamadas.append("nom") or [])
    importacion.validar_lote([_f(i, nombre=f"p{i}", codigo_barras=str(i)) for i in range(2, 200)])
    assert llamadas == ["cat", "cod", "nom"]


# =========================================================== confirmar


@pytest.fixture
def escrituras(monkeypatch):
    registro = {"productos": [], "movimientos": [], "espejo": []}

    def crear_varios(lista):
        filas = [dict(p, id=f"id{i}", activo=True) for i, p in enumerate(lista)]
        registro["productos"].extend(filas)
        return filas

    monkeypatch.setattr(importacion.productos_repo, "crear_varios", crear_varios)
    monkeypatch.setattr(importacion.movimientos_repo, "insertar_varios", lambda m: registro["movimientos"].extend(m))
    monkeypatch.setattr(importacion.productos_local, "upsert_producto", lambda p: registro["espejo"].append(p))
    return registro


def test_confirmar_crea_y_registra_inventario_inicial(escrituras):
    filas = [_f(i, nombre=f"p{i}", cantidad=(5 if i % 2 else None)) for i in range(2, 12)]
    r = importacion.confirmar_lote(filas, "u1", categorias=CATEGORIAS, codigos_existentes=set(), nombres_existentes=[])
    assert r == {"creados": 10, "omitidos": []}
    assert len(escrituras["productos"]) == 10
    assert len(escrituras["movimientos"]) == 5
    assert {m["tipo"] for m in escrituras["movimientos"]} == {"inventario_inicial"}
    assert {m["usuario_id"] for m in escrituras["movimientos"]} == {"u1"}
    assert len(escrituras["espejo"]) == 10


def test_confirmar_omite_conflicto_aparecido_despues(escrituras):
    filas = [_f(2, codigo_barras="111"), _f(3, nombre="otro")]
    r = importacion.confirmar_lote(filas, "u1", categorias=CATEGORIAS, codigos_existentes={"111"}, nombres_existentes=[])
    assert r["creados"] == 1
    assert r["omitidos"] == [{"fila": 2, "motivos": ["El codigo de barras ya esta en uso"]}]


def test_fallo_del_espejo_no_cambia_la_respuesta(escrituras, monkeypatch):
    monkeypatch.setattr(importacion.productos_local, "upsert_producto", lambda p: 1 / 0)
    r = importacion.confirmar_lote([_f(2)], "u1", categorias=CATEGORIAS, codigos_existentes=set(), nombres_existentes=[])
    assert r == {"creados": 1, "omitidos": []}


def test_fallo_parcial_reporta_desde_que_fila(monkeypatch):
    def crear_varios(lista):
        raise productos_repo.ErrorInsercionParcial([dict(lista[0], id="a")], RuntimeError("red"))

    monkeypatch.setattr(importacion.productos_repo, "crear_varios", crear_varios)
    monkeypatch.setattr(importacion.movimientos_repo, "insertar_varios", lambda m: None)
    monkeypatch.setattr(importacion.productos_local, "upsert_producto", lambda p: None)
    r = importacion.confirmar_lote(
        [_f(2), _f(3, nombre="b")], "u1", categorias=CATEGORIAS, codigos_existentes=set(), nombres_existentes=[]
    )
    assert r["creados"] == 1
    assert r["omitidos"][0]["fila"] == 3
    assert "desde la fila 3" in r["error"]


# =========================================================== plantilla


def test_plantilla_hojas_encabezados_y_formato_texto():
    libro = load_workbook(io.BytesIO(importacion.generar_plantilla(CATEGORIAS)))
    assert libro.sheetnames == ["Productos", "Categorias"]
    hoja = libro["Productos"]
    assert [c.value for c in hoja[1]] == list(importacion.COLUMNAS)
    assert hoja["A1"].font.bold and not hoja["D1"].font.bold
    assert hoja["D2"].number_format == "@"
    assert [c.value for c in libro["Categorias"]["A"]][1:] == CATEGORIAS


def test_plantilla_vacia_se_puede_reimportar_como_error_claro():
    with pytest.raises(importacion.ErrorArchivo, match="no tiene filas"):
        importacion.leer_archivo("p.xlsx", importacion.generar_plantilla(CATEGORIAS))


# =========================================================== endpoints


@pytest.fixture
def app(tmp_path):
    app = modulo_main.crear_app(carpeta_frontend=str(tmp_path))
    app.testing = True
    return app


@pytest.fixture
def sin_bigquery(monkeypatch):
    """Lecturas falseadas; cualquier escritura real revienta el test."""
    monkeypatch.setattr(importacion, "_categorias_vigentes", lambda: CATEGORIAS)
    monkeypatch.setattr(importacion.productos_repo, "codigos_barras_existentes", lambda c: set())
    monkeypatch.setattr(importacion.productos_repo, "nombres_activos", lambda: [])
    prohibido = lambda *a, **k: pytest.fail("no debe escribir en BigQuery")  # noqa: E731
    monkeypatch.setattr(productos_repo, "insertar_filas", prohibido)
    monkeypatch.setattr(importacion.movimientos_repo, "insertar_filas", prohibido)


def _h(app, rol="dueno"):
    with app.app_context():
        token = create_access_token(identity="u1", additional_claims={"rol": rol, "nombre": "Nadya"})
    return {"Authorization": f"Bearer {token}"}


def _subir(cliente, headers, nombre, contenido):
    return cliente.post(
        "/api/catalogo/importar/previsualizar",
        data={"archivo": (io.BytesIO(contenido), nombre)},
        headers=headers,
        content_type="multipart/form-data",
    )


def test_sin_token_401(app):
    cliente = app.test_client()
    assert cliente.post("/api/catalogo/importar/previsualizar").status_code == 401
    assert cliente.get("/api/catalogo/importar/plantilla").status_code == 401
    assert cliente.post("/api/catalogo/importar/confirmar", json={}).status_code == 401


def test_empleado_403(app, sin_bigquery):
    cliente = app.test_client()
    h = _h(app, "empleado")
    assert _subir(cliente, h, "x.csv", b"nombre,categoria,precio\nA,Escolar,1\n").status_code == 403
    assert cliente.get("/api/catalogo/importar/plantilla", headers=h).status_code == 403
    assert cliente.post("/api/catalogo/importar/confirmar", json={"filas": [_f(2)]}, headers=h).status_code == 403


def test_previsualizar_no_escribe_y_reporta(app, sin_bigquery):
    contenido = _xlsx([["nombre", "categoria", "precio"], ["A", "Escolar", 1], ["B", "Juguetería", -1]])
    r = _subir(app.test_client(), _h(app), "x.xlsx", contenido)
    assert r.status_code == 200
    data = r.get_json()
    assert data["total"] == 2
    assert [v["fila"] for v in data["validas"]] == [2]
    assert data["errores"][0]["fila"] == 3
    assert len(data["errores"][0]["motivos"]) == 2


def test_previsualizar_400(app, sin_bigquery):
    cliente = app.test_client()
    assert _subir(cliente, _h(app), "x.pdf", b"x").status_code == 400
    r = _subir(cliente, _h(app), "x.csv", b"nombre,categoria\nA,Escolar\n")
    assert r.status_code == 400 and "precio" in r.get_json()["error"]
    assert cliente.post("/api/catalogo/importar/previsualizar", headers=_h(app)).status_code == 400


def test_plantilla_endpoint(app, sin_bigquery):
    r = app.test_client().get("/api/catalogo/importar/plantilla", headers=_h(app))
    assert r.status_code == 200
    assert "plantilla_productos.xlsx" in r.headers["Content-Disposition"]
    assert load_workbook(io.BytesIO(r.data)).sheetnames == ["Productos", "Categorias"]


def test_confirmar_endpoint_usa_usuario_del_jwt(app, sin_bigquery, escrituras):
    cuerpo = {"filas": [_f(2, cantidad=3, usuario_id="intruso")]}
    r = app.test_client().post("/api/catalogo/importar/confirmar", json=cuerpo, headers=_h(app))
    assert r.status_code == 200
    assert r.get_json() == {"creados": 1, "omitidos": []}
    assert escrituras["movimientos"][0]["usuario_id"] == "u1"


def test_confirmar_endpoint_400(app, sin_bigquery):
    cliente = app.test_client()
    assert cliente.post("/api/catalogo/importar/confirmar", json={}, headers=_h(app)).status_code == 400
    assert cliente.post("/api/catalogo/importar/confirmar", json={"filas": ["x"]}, headers=_h(app)).status_code == 400
