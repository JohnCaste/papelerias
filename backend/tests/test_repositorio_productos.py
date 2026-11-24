"""
Tests del repositorio de producto -- se falsea ejecutar_query/ejecutar_uno
e insertar_filas, nunca se toca la red.
"""

import acceso_datos.repositorios.productos as productos


def test_listar_todos_activos_no_pagina(monkeypatch):
    capturado = {}

    def falso_ejecutar_query(sql, valores=None, tipos=None):
        capturado["sql"] = sql
        capturado["valores"] = valores
        return [{"id": "p1"}, {"id": "p2"}]

    monkeypatch.setattr(productos, "ejecutar_query", falso_ejecutar_query)
    filas = productos.listar_todos_activos()

    assert "activo = TRUE" in capturado["sql"]
    assert "LIMIT" not in capturado["sql"]
    assert capturado["valores"] is None
    assert filas == [{"id": "p1"}, {"id": "p2"}]


def test_buscar_sin_filtros_solo_exige_activo(monkeypatch):
    capturado = {}

    def falso_ejecutar_query(sql, valores=None, tipos=None):
        capturado["sql"] = sql
        capturado["valores"] = valores
        return []

    monkeypatch.setattr(productos, "ejecutar_query", falso_ejecutar_query)
    productos.buscar()

    assert "activo = TRUE" in capturado["sql"]
    assert "termino" not in capturado["valores"]
    assert capturado["valores"]["limite"] == 20
    assert capturado["valores"]["offset"] == 0


def test_buscar_por_termino_usa_like_parametrizado(monkeypatch):
    capturado = {}

    def falso_ejecutar_query(sql, valores=None, tipos=None):
        capturado["sql"] = sql
        capturado["valores"] = valores
        return []

    monkeypatch.setattr(productos, "ejecutar_query", falso_ejecutar_query)
    productos.buscar(termino="Bic")

    # el valor del usuario NUNCA debe aparecer literal dentro del sql
    assert "Bic" not in capturado["sql"]
    assert capturado["valores"]["termino"] == "%Bic%"


def test_buscar_por_termino_tambien_matchea_codigo_de_barras_exacto(monkeypatch):
    capturado = {}

    def falso_ejecutar_query(sql, valores=None, tipos=None):
        capturado["sql"] = sql
        capturado["valores"] = valores
        return []

    monkeypatch.setattr(productos, "ejecutar_query", falso_ejecutar_query)
    productos.buscar(termino="7501234567890")

    # el termino entra por nombre (LIKE) y por codigo_barras (igualdad exacta)
    assert "codigo_barras = @codigo_barras_exacto" in capturado["sql"]
    assert "LIKE" in capturado["sql"]
    # el LIKE lleva comodines; el match por codigo es exacto, sin '%'
    assert capturado["valores"]["termino"] == "%7501234567890%"
    assert capturado["valores"]["codigo_barras_exacto"] == "7501234567890"
    # el valor del usuario nunca va literal en el sql
    assert "7501234567890" not in capturado["sql"]


def test_buscar_por_termino_quita_marcas_diacriticas_ademas_de_normalizar(monkeypatch):
    """
    NORMALIZE(x, NFD) por si solo descompone (p.ej. 'a' con acento en 'a'
    + marca combinante) pero NO quita la marca -- buscar 'lapiz' nunca
    encontraba 'Lapiz' (con acento) sin esto, porque la marca combinante
    seguia rompiendo la coincidencia de subcadena. El SQL debe quitarla
    (categoria Unicode 'M', via REGEXP_REPLACE) en los dos lados de la
    comparacion, no solo normalizar.
    """
    capturado = {}

    def falso_ejecutar_query(sql, valores=None, tipos=None):
        capturado["sql"] = sql
        return []

    monkeypatch.setattr(productos, "ejecutar_query", falso_ejecutar_query)
    productos.buscar(termino="lapiz")

    assert r"REGEXP_REPLACE(LOWER(NORMALIZE(nombre, NFD)), r'\pM', '')" in capturado["sql"]
    assert (
        r"REGEXP_REPLACE(LOWER(NORMALIZE(@termino, NFD)), r'\pM', '')" in capturado["sql"]
    )


def test_contar_usa_las_mismas_condiciones_que_buscar(monkeypatch):
    capturado = {}

    def falso_ejecutar_uno(sql, valores=None, tipos=None):
        capturado["sql"] = sql
        capturado["valores"] = valores
        return {"total": 0}

    monkeypatch.setattr(productos, "ejecutar_uno", falso_ejecutar_uno)
    productos.contar(termino="7501234567890")

    # contar tambien resuelve la rama de codigo_barras -> el total queda coherente
    assert "codigo_barras = @codigo_barras_exacto" in capturado["sql"]
    assert capturado["valores"]["codigo_barras_exacto"] == "7501234567890"


def test_buscar_con_todos_los_filtros(monkeypatch):
    capturado = {}

    def falso_ejecutar_query(sql, valores=None, tipos=None):
        capturado["sql"] = sql
        capturado["valores"] = valores
        capturado["tipos"] = tipos
        return []

    monkeypatch.setattr(productos, "ejecutar_query", falso_ejecutar_query)
    productos.buscar(
        termino="pluma",
        categoria="papeleria",
        marca="Bic",
        precio_min=5,
        precio_max=50,
    )

    v = capturado["valores"]
    assert v["categoria"] == "papeleria"
    assert v["marca"] == "Bic"
    assert v["precio_min"] == 5.0
    assert v["precio_max"] == 50.0
    assert capturado["tipos"]["precio_min"] == "NUMERIC"


def test_limite_se_acota_al_maximo(monkeypatch):
    capturado = {}

    def falso_ejecutar_query(sql, valores=None, tipos=None):
        capturado["valores"] = valores
        return []

    monkeypatch.setattr(productos, "ejecutar_query", falso_ejecutar_query)
    productos.buscar(limite=99999)

    assert capturado["valores"]["limite"] == productos._LIMITE_MAXIMO


def test_buscar_con_total_usa_una_sola_consulta(monkeypatch):
    llamadas = []

    def falso_ejecutar_query(sql, valores=None, tipos=None):
        llamadas.append(sql)
        return [
            {"id": "p1", "nombre": "Pluma", "total_coincidencias": 3},
            {"id": "p2", "nombre": "Cuaderno", "total_coincidencias": 3},
        ]

    monkeypatch.setattr(productos, "ejecutar_query", falso_ejecutar_query)
    filas, total = productos.buscar_con_total(termino="pluma")

    assert len(llamadas) == 1
    assert "COUNT(*) OVER()" in llamadas[0]
    assert total == 3
    # la columna auxiliar no se filtra hacia quien llama
    assert "total_coincidencias" not in filas[0]
    assert "total_coincidencias" not in filas[1]
    assert filas[0]["id"] == "p1"


def test_buscar_con_total_sin_coincidencias_no_revienta(monkeypatch):
    monkeypatch.setattr(productos, "ejecutar_query", lambda sql, valores=None, tipos=None: [])
    filas, total = productos.buscar_con_total(termino="inexistente")

    assert filas == []
    assert total == 0


def test_crear_inserta_una_fila_con_uuid_y_activo_true(monkeypatch):
    capturado = {}

    def falsa_insertar_filas(tabla, filas):
        capturado["tabla"] = tabla
        capturado["filas"] = filas

    monkeypatch.setattr(productos, "insertar_filas", falsa_insertar_filas)
    fila = productos.crear({"nombre": "Pluma Bic", "categoria": "papeleria", "precio": 8.5})

    assert fila["id"]
    assert fila["activo"] is True
    assert fila["nombre"] == "Pluma Bic"
    assert capturado["filas"] == [fila]


def test_actualizar_solo_incluye_campos_provistos(monkeypatch):
    capturado = {}

    def falso_ejecutar_query(sql, valores=None, tipos=None):
        capturado["sql"] = sql
        capturado["valores"] = valores
        return []

    monkeypatch.setattr(productos, "ejecutar_query", falso_ejecutar_query)
    productos.actualizar("id-1", {"precio": 10})

    assert "precio = @precio" in capturado["sql"]
    assert "nombre = @nombre" not in capturado["sql"]
    assert capturado["valores"]["id"] == "id-1"


def test_actualizar_sin_cambios_no_ejecuta_nada(monkeypatch):
    llamado = []
    monkeypatch.setattr(
        productos, "ejecutar_query", lambda *a, **k: llamado.append(1)
    )
    productos.actualizar("id-1", {})
    assert llamado == []


def test_eliminar_es_borrado_logico_no_fisico(monkeypatch):
    capturado = {}

    def falso_ejecutar_query(sql, valores=None, tipos=None):
        capturado["sql"] = sql
        return []

    monkeypatch.setattr(productos, "ejecutar_query", falso_ejecutar_query)
    productos.eliminar("id-1")

    assert "UPDATE" in capturado["sql"]
    assert "DELETE" not in capturado["sql"]
    assert "activo = FALSE" in capturado["sql"]
