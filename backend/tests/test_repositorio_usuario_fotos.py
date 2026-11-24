"""
Tests del repositorio de usuario_foto. Lo que importa verificar: `guardar`
hace upsert (INSERT la primera vez, UPDATE despues) y `listar` no revienta
si la tabla todavia no existe.
"""

from google.api_core import exceptions as api_exceptions

import acceso_datos.repositorios.usuario_fotos as fotos


def test_listar_devuelve_mapa_id_a_url(monkeypatch):
    monkeypatch.setattr(
        fotos,
        "ejecutar_query",
        lambda sql, *a, **k: [
            {"usuario_id": "u1", "foto_url": "https://cdn/a.webp"},
            {"usuario_id": "u2", "foto_url": "https://cdn/b.webp"},
        ],
    )
    assert fotos.listar() == {
        "u1": "https://cdn/a.webp",
        "u2": "https://cdn/b.webp",
    }


def test_listar_tolera_tabla_inexistente(monkeypatch):
    def truena(sql, *a, **k):
        raise api_exceptions.NotFound("Not found: Table lapape.usuario_foto")

    monkeypatch.setattr(fotos, "ejecutar_query", truena)
    assert fotos.listar() == {}


def test_guardar_inserta_si_no_habia_foto(monkeypatch):
    consultas = []
    monkeypatch.setattr(fotos, "ejecutar_uno", lambda sql, valores=None: None)
    monkeypatch.setattr(
        fotos,
        "ejecutar_query",
        lambda sql, valores=None: consultas.append((sql, valores)),
    )

    fotos.guardar("u1", "https://cdn/nueva.webp")

    assert len(consultas) == 1
    assert "INSERT INTO" in consultas[0][0]
    assert consultas[0][1]["id"] == "u1"
    assert consultas[0][1]["url"] == "https://cdn/nueva.webp"


def test_guardar_actualiza_si_ya_habia_foto(monkeypatch):
    consultas = []
    monkeypatch.setattr(
        fotos, "ejecutar_uno", lambda sql, valores=None: {"foto_url": "https://cdn/vieja.webp"}
    )
    monkeypatch.setattr(
        fotos,
        "ejecutar_query",
        lambda sql, valores=None: consultas.append((sql, valores)),
    )

    fotos.guardar("u1", "https://cdn/nueva.webp")

    assert len(consultas) == 1
    assert "UPDATE" in consultas[0][0]
    assert consultas[0][1]["url"] == "https://cdn/nueva.webp"
