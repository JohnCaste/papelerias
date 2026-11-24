"""
Tests de acceso_datos/consultas.py -- cliente falso, sin red.
"""

from acceso_datos.consultas import ejecutar_query, ejecutar_uno


class JobFalso:
    def __init__(self, filas):
        self._filas = filas

    def result(self, retry=None):
        return self._filas


class ClienteFalso:
    def __init__(self, filas):
        self._filas = filas
        self.llamadas = []

    def query(self, sql, job_config=None, retry=None):
        self.llamadas.append((sql, job_config))
        return JobFalso(self._filas)


def test_ejecutar_query_devuelve_lista_de_dicts():
    cliente = ClienteFalso([{"id": "1", "nombre": "Bic"}])
    resultado = ejecutar_query("SELECT * FROM x", cliente=cliente)
    assert resultado == [{"id": "1", "nombre": "Bic"}]


def test_ejecutar_query_pasa_los_parametros_al_job_config():
    cliente = ClienteFalso([])
    ejecutar_query("SELECT * FROM x WHERE nombre = @nombre", {"nombre": "Bic"}, cliente=cliente)
    _, config = cliente.llamadas[0]
    nombres = [p.name for p in config.query_parameters]
    assert nombres == ["nombre"]


def test_ejecutar_query_sin_valores_no_manda_parametros():
    cliente = ClienteFalso([])
    ejecutar_query("SELECT * FROM x", cliente=cliente)
    _, config = cliente.llamadas[0]
    assert config.query_parameters == []


def test_ejecutar_uno_devuelve_primera_fila():
    cliente = ClienteFalso([{"id": "1"}, {"id": "2"}])
    assert ejecutar_uno("SELECT * FROM x", cliente=cliente) == {"id": "1"}


def test_ejecutar_uno_devuelve_none_si_no_hay_filas():
    cliente = ClienteFalso([])
    assert ejecutar_uno("SELECT * FROM x", cliente=cliente) is None
