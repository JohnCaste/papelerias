"""
Tests de almacen_local/espejo_catalogo.py -- se falsean los repositorios
de BigQuery (productos_repo, movimientos_repo, categorias_repo), nunca se
toca la red. El espejo local en si usa una base SQLite temporal
(`tmp_path`), nunca el archivo real del negocio.
"""

import almacen_local.espejo_catalogo as espejo_catalogo
import acceso_datos.repositorios.productos_local as productos_local


def _espejo(tmp_path, **kwargs):
    return espejo_catalogo.EspejoCatalogo(archivo=tmp_path / "espejo_test.sqlite3", **kwargs)


def test_disponible_es_false_antes_del_primer_ciclo(tmp_path):
    espejo = _espejo(tmp_path)
    assert espejo.disponible() is False


def test_un_ciclo_exitoso_puebla_el_espejo_y_marca_disponible(tmp_path, monkeypatch):
    monkeypatch.setattr(
        espejo_catalogo.productos_repo,
        "listar_todos_activos",
        lambda: [{"id": "p1", "nombre": "Pluma", "categoria": "Escritura", "precio": 10}],
    )
    monkeypatch.setattr(
        espejo_catalogo.movimientos_repo, "stock_de_todos", lambda: {"p1": 7}
    )
    monkeypatch.setattr(
        espejo_catalogo.categorias_repo, "listar", lambda: ["Escritura"]
    )

    espejo = _espejo(tmp_path)
    resultado = espejo.ejecutar_ciclo()

    assert resultado["exito"] is True
    assert espejo.disponible() is True
    assert espejo.ultimo_refresco_exitoso is not None

    filas = productos_local.listar(archivo=espejo._archivo)
    assert len(filas) == 1
    assert filas[0]["cantidad"] == 7


def test_un_ciclo_que_falla_no_lanza_y_registra_el_error(tmp_path, monkeypatch):
    def truena():
        raise RuntimeError("sin internet")

    monkeypatch.setattr(espejo_catalogo.productos_repo, "listar_todos_activos", truena)

    espejo = _espejo(tmp_path)
    resultado = espejo.ejecutar_ciclo()  # no debe lanzar

    assert resultado["exito"] is False
    assert "sin internet" in resultado["error"]
    assert espejo.ultimo_error is not None


def test_disponible_sigue_true_tras_un_fallo_posterior_a_un_exito(tmp_path, monkeypatch):
    """Una vez que hubo un refresco exitoso, un ciclo que falla despues NO
    debe volver el espejo 'no disponible' -- sigue sirviendo el contenido
    del ultimo refresco bueno (ver design.md, Decision 4)."""
    monkeypatch.setattr(espejo_catalogo.productos_repo, "listar_todos_activos", lambda: [])
    monkeypatch.setattr(espejo_catalogo.movimientos_repo, "stock_de_todos", lambda: {})
    monkeypatch.setattr(espejo_catalogo.categorias_repo, "listar", lambda: [])

    espejo = _espejo(tmp_path)
    assert espejo.ejecutar_ciclo()["exito"] is True
    assert espejo.disponible() is True

    def truena():
        raise RuntimeError("sin internet")

    monkeypatch.setattr(espejo_catalogo.productos_repo, "listar_todos_activos", truena)
    assert espejo.ejecutar_ciclo()["exito"] is False
    assert espejo.disponible() is True  # sigue disponible


def test_iniciar_y_detener_el_hilo(tmp_path, monkeypatch):
    monkeypatch.setattr(espejo_catalogo.productos_repo, "listar_todos_activos", lambda: [])
    monkeypatch.setattr(espejo_catalogo.movimientos_repo, "stock_de_todos", lambda: {})
    monkeypatch.setattr(espejo_catalogo.categorias_repo, "listar", lambda: [])

    espejo = _espejo(tmp_path, intervalo_segundos=60)
    espejo.iniciar()
    try:
        espejo._hilo.join(timeout=2)  # el primer ciclo corre de inmediato
        assert espejo.disponible() is True
    finally:
        espejo.detener()

    assert not espejo._hilo.is_alive()


def test_iniciar_dos_veces_no_duplica_el_hilo(tmp_path, monkeypatch):
    monkeypatch.setattr(espejo_catalogo.productos_repo, "listar_todos_activos", lambda: [])
    monkeypatch.setattr(espejo_catalogo.movimientos_repo, "stock_de_todos", lambda: {})
    monkeypatch.setattr(espejo_catalogo.categorias_repo, "listar", lambda: [])

    espejo = _espejo(tmp_path, intervalo_segundos=60)
    espejo.iniciar()
    hilo_original = espejo._hilo
    espejo.iniciar()
    try:
        assert espejo._hilo is hilo_original
    finally:
        espejo.detener()
