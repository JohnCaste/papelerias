"""
Tests del repositorio de usuario_rol. `guardar` hace upsert (INSERT la
primera vez, UPDATE despues) y las lecturas no revientan si la tabla
todavia no existe (se tratan todos como 'empleado').
"""

from google.api_core import exceptions as api_exceptions

import acceso_datos.repositorios.usuario_roles as roles


def test_listar_devuelve_mapa_id_a_rol(monkeypatch):
    monkeypatch.setattr(
        roles,
        "ejecutar_query",
        lambda sql, *a, **k: [
            {"usuario_id": "u1", "rol": "dueno"},
            {"usuario_id": "u2", "rol": "empleado"},
        ],
    )
    assert roles.listar() == {"u1": "dueno", "u2": "empleado"}


def test_listar_tolera_tabla_inexistente(monkeypatch):
    def truena(sql, *a, **k):
        raise api_exceptions.NotFound("Not found: Table lapape.usuario_rol")

    monkeypatch.setattr(roles, "ejecutar_query", truena)
    assert roles.listar() == {}


def test_obtener_tolera_tabla_inexistente(monkeypatch):
    def truena(sql, *a, **k):
        raise api_exceptions.NotFound("Not found: Table lapape.usuario_rol")

    monkeypatch.setattr(roles, "ejecutar_uno", truena)
    assert roles.obtener("u1") is None


def test_guardar_inserta_si_no_habia_rol(monkeypatch):
    consultas = []
    monkeypatch.setattr(roles, "ejecutar_uno", lambda sql, valores=None: None)
    monkeypatch.setattr(
        roles, "ejecutar_query", lambda sql, valores=None: consultas.append((sql, valores))
    )

    roles.guardar("u1", "dueno")

    assert len(consultas) == 1
    sql, valores = consultas[0]
    assert "INSERT INTO" in sql
    assert valores["id"] == "u1"
    assert valores["rol"] == "dueno"
    assert "ts" in valores


def test_guardar_actualiza_si_ya_habia_rol(monkeypatch):
    consultas = []
    monkeypatch.setattr(roles, "ejecutar_uno", lambda sql, valores=None: {"rol": "empleado"})
    monkeypatch.setattr(
        roles, "ejecutar_query", lambda sql, valores=None: consultas.append((sql, valores))
    )

    roles.guardar("u1", "dueno")

    assert len(consultas) == 1
    assert "UPDATE" in consultas[0][0]
    assert consultas[0][1]["rol"] == "dueno"
