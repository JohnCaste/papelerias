"""
Tests del repositorio de catalogo contra el espejo local en SQLite
(#13). Mismos casos que test_repositorio_productos.py (BigQuery),
para confirmar paridad de comportamiento entre ambos caminos --
especialmente la busqueda insensible a acentos/mayusculas, que en
BigQuery usa NORMALIZE() y aqui se resuelve a mano (ver
almacen_local/espejo_catalogo_sqlite.py::normalizar_texto).

Cada test usa un archivo SQLite temporal (`tmp_path`), nunca el archivo
real del negocio.
"""

import datetime

import acceso_datos.repositorios.productos_local as productos_local


def _archivo(tmp_path):
    return tmp_path / "catalogo_espejo_test.sqlite3"


def _producto(**overrides):
    base = {
        "id": "p1",
        "codigo_barras": None,
        "codigo_interno": None,
        "nombre": "Producto de prueba",
        "categoria": "Escolar",
        "marca": None,
        "descripcion": None,
        "imagen": None,
        "precio": 10.0,
        "costo": None,
        "stock_minimo": None,
        "cantidad": 0,
        "actualizado_en": datetime.datetime(2026, 1, 1),
    }
    base.update(overrides)
    return base


def test_reemplazar_todo_puebla_productos_y_categorias(tmp_path):
    archivo = _archivo(tmp_path)
    productos_local.reemplazar_todo(
        [_producto(id="p1", nombre="Pluma")],
        ["Escolar", "Escritura"],
        archivo=archivo,
    )

    assert productos_local.listar_categorias(archivo=archivo) == ["Escolar", "Escritura"]
    filas = productos_local.listar(archivo=archivo)
    assert len(filas) == 1
    assert filas[0]["nombre"] == "Pluma"


def test_reemplazar_todo_reemplaza_el_contenido_previo(tmp_path):
    archivo = _archivo(tmp_path)
    productos_local.reemplazar_todo([_producto(id="p1")], ["Escolar"], archivo=archivo)
    productos_local.reemplazar_todo([_producto(id="p2")], ["Nueva"], archivo=archivo)

    filas = productos_local.listar(archivo=archivo)
    assert [f["id"] for f in filas] == ["p2"]
    assert productos_local.listar_categorias(archivo=archivo) == ["Nueva"]


def test_buscar_por_termino_insensible_a_mayusculas_y_acentos(tmp_path):
    archivo = _archivo(tmp_path)
    productos_local.reemplazar_todo(
        [_producto(id="p1", nombre="Cámara fotográfica")],
        [],
        archivo=archivo,
    )

    filas, total = productos_local.buscar_con_total(termino="camara fotografica", archivo=archivo)
    assert total == 1
    assert filas[0]["id"] == "p1"

    filas, total = productos_local.buscar_con_total(termino="CÁMARA", archivo=archivo)
    assert total == 1


def test_buscar_por_codigo_de_barras_exacto(tmp_path):
    archivo = _archivo(tmp_path)
    productos_local.reemplazar_todo(
        [_producto(id="p1", nombre="Cuaderno profesional", codigo_barras="7501234567890")],
        [],
        archivo=archivo,
    )

    filas, total = productos_local.buscar_con_total(termino="7501234567890", archivo=archivo)
    assert total == 1
    assert filas[0]["id"] == "p1"


def test_codigo_de_barras_parcial_no_coincide(tmp_path):
    archivo = _archivo(tmp_path)
    productos_local.reemplazar_todo(
        [_producto(id="p1", nombre="Cuaderno", codigo_barras="7501234567890")],
        [],
        archivo=archivo,
    )

    _, total = productos_local.buscar_con_total(termino="750123", archivo=archivo)
    assert total == 0


def test_filtro_combinado_categoria_marca_precio(tmp_path):
    archivo = _archivo(tmp_path)
    productos_local.reemplazar_todo(
        [
            _producto(id="p1", categoria="Escritura", marca="BIC", precio=30),
            _producto(id="p2", categoria="Escritura", marca="BIC", precio=80),
            _producto(id="p3", categoria="Escolar", marca="BIC", precio=30),
            _producto(id="p4", categoria="Escritura", marca="Pilot", precio=30),
        ],
        [],
        archivo=archivo,
    )

    filas, total = productos_local.buscar_con_total(
        categoria="Escritura", marca="bic", precio_max=50, archivo=archivo
    )
    assert total == 1
    assert filas[0]["id"] == "p1"


def test_paginacion_devuelve_total_estable(tmp_path):
    archivo = _archivo(tmp_path)
    productos_local.reemplazar_todo(
        [_producto(id=f"p{i}", nombre=f"Producto {i:02d}") for i in range(25)],
        [],
        archivo=archivo,
    )

    filas, total = productos_local.buscar_con_total(limite=12, offset=12, archivo=archivo)
    assert total == 25
    assert len(filas) == 12


def test_sin_coincidencias_total_es_cero(tmp_path):
    archivo = _archivo(tmp_path)
    productos_local.reemplazar_todo([_producto(id="p1")], [], archivo=archivo)

    filas, total = productos_local.buscar_con_total(termino="no existe esto", archivo=archivo)
    assert filas == []
    assert total == 0


def test_marcas_distintas_unicas_y_ordenadas(tmp_path):
    archivo = _archivo(tmp_path)
    productos_local.reemplazar_todo(
        [
            _producto(id="p1", marca="BIC"),
            _producto(id="p2", marca="Faber-Castell"),
            _producto(id="p3", marca="BIC"),
            _producto(id="p4", marca=None),
        ],
        [],
        archivo=archivo,
    )

    assert productos_local.marcas_distintas(archivo=archivo) == ["BIC", "Faber-Castell"]


def test_limite_se_acota_al_maximo(tmp_path):
    archivo = _archivo(tmp_path)
    productos_local.reemplazar_todo([_producto(id="p1")], [], archivo=archivo)

    filas, total = productos_local.buscar_con_total(
        limite=99999, archivo=archivo
    )
    # no debe reventar ni devolver un limite absurdo -- se acota igual
    # que acceso_datos/repositorios/productos.py::_LIMITE_MAXIMO
    assert productos_local._LIMITE_MAXIMO == 200


def test_upsert_producto_agrega_uno_nuevo(tmp_path):
    archivo = _archivo(tmp_path)
    productos_local.reemplazar_todo([], [], archivo=archivo)

    productos_local.upsert_producto(_producto(id="p1", nombre="Nuevo"), archivo=archivo)

    filas = productos_local.listar(archivo=archivo)
    assert len(filas) == 1
    assert filas[0]["nombre"] == "Nuevo"


def test_upsert_producto_actualiza_uno_existente(tmp_path):
    archivo = _archivo(tmp_path)
    productos_local.reemplazar_todo([_producto(id="p1", precio=10)], [], archivo=archivo)

    productos_local.upsert_producto(_producto(id="p1", precio=99), archivo=archivo)

    filas = productos_local.listar(archivo=archivo)
    assert len(filas) == 1
    assert filas[0]["precio"] == 99.0


def test_upsert_producto_se_ve_de_inmediato_en_una_busqueda(tmp_path):
    archivo = _archivo(tmp_path)
    productos_local.reemplazar_todo([], [], archivo=archivo)

    productos_local.upsert_producto(_producto(id="p1", nombre="Recien editado"), archivo=archivo)

    filas, total = productos_local.buscar_con_total(termino="recien editado", archivo=archivo)
    assert total == 1


def test_marcar_inactivo_quita_el_producto(tmp_path):
    archivo = _archivo(tmp_path)
    productos_local.reemplazar_todo([_producto(id="p1")], [], archivo=archivo)

    productos_local.marcar_inactivo("p1", archivo=archivo)

    assert productos_local.listar(archivo=archivo) == []
