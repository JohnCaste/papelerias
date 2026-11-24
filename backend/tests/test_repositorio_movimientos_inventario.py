"""
Tests del repositorio de movimiento_inventario. La parte que importa
verificar: el stock nunca se lee de una columna, siempre se agrega.
"""

import acceso_datos.repositorios.movimientos_inventario as movimientos


def test_insertar_normaliza_y_genera_id(monkeypatch):
    capturado = {}
    monkeypatch.setattr(
        movimientos, "insertar_filas", lambda tabla, filas: capturado.update(filas=filas)
    )

    fila = movimientos.insertar(
        {"producto_id": "p1", "tipo": "venta", "cantidad": -2, "usuario_id": "u1"}
    )

    assert fila["id"]
    assert fila["cantidad"] == -2.0
    assert capturado["filas"] == [fila]


def test_insertar_varios_para_una_venta_con_varias_lineas(monkeypatch):
    capturado = {}
    monkeypatch.setattr(
        movimientos, "insertar_filas", lambda tabla, filas: capturado.update(filas=filas)
    )

    filas = movimientos.insertar_varios(
        [
            {"producto_id": "p1", "tipo": "venta", "cantidad": -1, "usuario_id": "u1"},
            {"producto_id": "p2", "tipo": "venta", "cantidad": -3, "usuario_id": "u1"},
        ]
    )

    assert len(filas) == 2
    assert {f["id"] for f in filas} == {f["id"] for f in capturado["filas"]}


def test_stock_actual_usa_sum_no_una_columna(monkeypatch):
    capturado = {}

    def falso_ejecutar_uno(sql, valores=None):
        capturado["sql"] = sql
        return {"stock": 7}

    monkeypatch.setattr(movimientos, "ejecutar_uno", falso_ejecutar_uno)
    resultado = movimientos.stock_actual("p1")

    assert "SUM(cantidad)" in capturado["sql"]
    assert resultado == 7


def test_stock_de_varios_sin_ids_no_consulta(monkeypatch):
    llamado = []
    monkeypatch.setattr(movimientos, "ejecutar_query", lambda *a, **k: llamado.append(1))
    assert movimientos.stock_de_varios([]) == {}
    assert llamado == []


def test_stock_de_varios_usa_unnest_y_arma_dict(monkeypatch):
    capturado = {}

    def falso_ejecutar_query(sql, valores=None, tipos=None):
        capturado["sql"] = sql
        capturado["valores"] = valores
        capturado["tipos"] = tipos
        return [{"producto_id": "p1", "stock": 5}, {"producto_id": "p2", "stock": 0}]

    monkeypatch.setattr(movimientos, "ejecutar_query", falso_ejecutar_query)
    resultado = movimientos.stock_de_varios(["p1", "p2"])

    assert "UNNEST(@producto_ids)" in capturado["sql"]
    assert capturado["valores"]["producto_ids"] == ["p1", "p2"]
    assert capturado["tipos"]["producto_ids"] == "STRING"
    assert resultado == {"p1": 5, "p2": 0}


def test_stock_de_todos_agrupa_sin_filtrar(monkeypatch):
    capturado = {}

    def falso_ejecutar_query(sql, valores=None, tipos=None):
        capturado["sql"] = sql
        capturado["valores"] = valores
        return [{"producto_id": "p1", "stock": 5}, {"producto_id": "p2", "stock": 12}]

    monkeypatch.setattr(movimientos, "ejecutar_query", falso_ejecutar_query)
    resultado = movimientos.stock_de_todos()

    assert "GROUP BY producto_id" in capturado["sql"]
    assert "WHERE" not in capturado["sql"]
    assert capturado["valores"] is None
    assert resultado == {"p1": 5, "p2": 12}


def test_stock_bajo_compara_contra_stock_minimo(monkeypatch):
    capturado = {}

    def falso_ejecutar_query(sql, valores=None, tipos=None):
        capturado["sql"] = sql
        return []

    monkeypatch.setattr(movimientos, "ejecutar_query", falso_ejecutar_query)
    movimientos.stock_bajo()

    assert "HAVING stock <=" in capturado["sql"]
    assert "stock_minimo" in capturado["sql"]


def test_kardex_filtra_por_producto_y_rango_opcional(monkeypatch):
    capturado = {}

    def falso_ejecutar_query(sql, valores=None, tipos=None):
        capturado["sql"] = sql
        capturado["valores"] = valores
        return []

    monkeypatch.setattr(movimientos, "ejecutar_query", falso_ejecutar_query)
    movimientos.kardex("p1", fecha_inicio="2026-08-01")

    assert "producto_id = @producto_id" in capturado["sql"]
    assert "fecha_inicio" in capturado["valores"]
    assert "fecha_fin" not in capturado["valores"]
