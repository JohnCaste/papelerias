"""
Tests del repositorio de cierre sobre BigQuery (acceso_datos/repositorios/cierres.py).
"""

import datetime

import acceso_datos.repositorios.cierres as cierres_repo


def test_existe_consulta_por_tipo_y_fecha_excluyendo_corregidos(monkeypatch):
    capturado = {}

    def falso_ejecutar_uno(sql, valores=None, tipos=None):
        capturado["sql"] = sql
        capturado["valores"] = valores
        return None

    monkeypatch.setattr(cierres_repo, "ejecutar_uno", falso_ejecutar_uno)
    resultado = cierres_repo.existe("dia", datetime.date(2026, 8, 31))

    assert resultado is False
    assert "estado != 'corregido'" in capturado["sql"]
    assert capturado["valores"]["tipo"] == "dia"


def test_existe_true_si_encuentra_fila(monkeypatch):
    monkeypatch.setattr(cierres_repo, "ejecutar_uno", lambda *a, **k: {"id": "c1"})
    assert cierres_repo.existe("dia", datetime.date(2026, 8, 31)) is True


def test_insertar_genera_id_nuevo(monkeypatch):
    capturado = {}
    monkeypatch.setattr(
        cierres_repo, "insertar_filas", lambda tabla, filas: capturado.update(filas=filas)
    )

    fila = cierres_repo.insertar(
        {
            "tipo": "dia",
            "fecha_inicio": datetime.date(2026, 8, 31),
            "fecha_fin": datetime.date(2026, 8, 31),
            "total": 100.0,
            "num_ventas": 5,
            "generado_por": "manual",
        }
    )

    assert fila["id"]
    assert fila["estado"] == "cerrado"
    assert capturado["filas"] == [fila]


def test_insertar_respeta_generado_en_si_se_provee(monkeypatch):
    """
    Un cierre generado localmente (#50) trae su propia marca de tiempo
    -- no debe pisarse con la hora en que se sincroniza a BigQuery.
    """
    monkeypatch.setattr(cierres_repo, "insertar_filas", lambda tabla, filas: None)

    original = datetime.datetime(2026, 8, 31, 20, 0, tzinfo=datetime.timezone.utc)
    fila = cierres_repo.insertar(
        {
            "tipo": "dia",
            "fecha_inicio": datetime.date(2026, 8, 31),
            "fecha_fin": datetime.date(2026, 8, 31),
            "total": 100.0,
            "num_ventas": 5,
            "generado_por": "automatico",
            "generado_en": original,
        }
    )

    assert fila["generado_en"] == original


def test_insertar_usa_ahora_si_no_se_provee_generado_en(monkeypatch):
    monkeypatch.setattr(cierres_repo, "insertar_filas", lambda tabla, filas: None)

    antes = datetime.datetime.now(datetime.timezone.utc)
    fila = cierres_repo.insertar(
        {
            "tipo": "dia",
            "fecha_inicio": datetime.date(2026, 8, 31),
            "fecha_fin": datetime.date(2026, 8, 31),
            "total": 0.0,
            "num_ventas": 0,
            "generado_por": "manual",
        }
    )
    despues = datetime.datetime.now(datetime.timezone.utc)

    assert antes <= fila["generado_en"] <= despues


def test_obtener_vigente_ordena_por_generado_en_descendente(monkeypatch):
    capturado = {}

    def falso_ejecutar_uno(sql, valores=None, tipos=None):
        capturado["sql"] = sql
        return {"id": "c1"}

    monkeypatch.setattr(cierres_repo, "ejecutar_uno", falso_ejecutar_uno)
    resultado = cierres_repo.obtener_vigente("dia", datetime.date(2026, 8, 31))

    assert "ORDER BY generado_en DESC" in capturado["sql"]
    assert resultado == {"id": "c1"}
