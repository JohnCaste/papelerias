"""
Tests del repositorio de categoria -- se falsea ejecutar_query e
insertar_filas, nunca se toca la red.
"""

import acceso_datos.repositorios.categorias as categorias


def test_listar_devuelve_nombres_activos_ordenados_por_orden(monkeypatch):
    capturado = {}

    def falso_ejecutar_query(sql, valores=None, tipos=None):
        capturado["sql"] = sql
        return [{"nombre": "Lapiceros"}, {"nombre": "Lápices"}]

    monkeypatch.setattr(categorias, "ejecutar_query", falso_ejecutar_query)

    assert categorias.listar() == ["Lapiceros", "Lápices"]
    assert "activo = TRUE" in capturado["sql"]
    assert "ORDER BY orden" in capturado["sql"]


def test_sembrar_asigna_orden_por_posicion(monkeypatch):
    capturado = {}

    monkeypatch.setattr(
        categorias,
        "insertar_filas",
        lambda tabla, filas: capturado.update(tabla=tabla, filas=filas),
    )

    filas = categorias.sembrar(["Lapiceros", "Lápices", "Cuadernos"])

    assert [f["orden"] for f in filas] == [0, 1, 2]
    assert [f["id"] for f in filas] == ["Lapiceros", "Lápices", "Cuadernos"]
    assert all(f["activo"] is True for f in filas)
    assert capturado["filas"] == filas


def test_borrar_todas_hace_delete_where_true(monkeypatch):
    capturado = {}
    monkeypatch.setattr(
        categorias,
        "ejecutar_query",
        lambda sql, valores=None, tipos=None: capturado.update(sql=sql) or [],
    )

    categorias.borrar_todas()

    assert "DELETE FROM" in capturado["sql"]
    assert "WHERE TRUE" in capturado["sql"]
