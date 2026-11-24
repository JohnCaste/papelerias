"""
EspejoCatalogo: hilo daemon que mantiene al dia el espejo local de solo
lectura del catalogo (#13 -- paso previo a evaluar una migracion a
MySQL). Ver openspec/changes/espejo-local-catalogo-sqlite/design.md.

    BigQuery (producto, categoria, movimiento_inventario)
            |
            v  cada `intervalo_segundos` (por defecto 30s)
    productos_local.reemplazar_todo(...)  -- reemplazo completo, una transaccion
            |
            v
    catalogo_espejo.sqlite3

Mismo patron que Sincronizador (almacen_local/sincronizador.py) y
ProgramadorCierre (almacen_local/programador_cierre.py): un hilo daemon
que nunca debe poder tumbar el proceso -- cualquier excepcion durante un
ciclo se atrapa, se registra y se reintenta en el siguiente ciclo. A
diferencia de esos dos (que SUBEN datos locales a BigQuery), este BAJA
catalogo de BigQuery hacia el disco local -- direccion inversa, por eso
es un componente separado y no una extension del Sincronizador.

No es una fuente de verdad: si el proceso se cae o el archivo se borra,
se reconstruye solo en el siguiente ciclo. `disponible()` refleja si
hubo AL MENOS UN refresco exitoso alguna vez -- una vez que lo hubo, el
espejo se sigue considerando disponible aunque un ciclo posterior falle
(sin internet, por ejemplo): sirve el contenido del ultimo refresco
bueno, que es mejor que caer a BigQuery en cada peticion mientras tanto.
"""

import datetime
import logging
import threading

import acceso_datos.repositorios.categorias as categorias_repo
import acceso_datos.repositorios.movimientos_inventario as movimientos_repo
import acceso_datos.repositorios.productos as productos_repo
import acceso_datos.repositorios.productos_local as productos_local

INTERVALO_SEGUNDOS = 30

logger = logging.getLogger(__name__)


class EspejoCatalogo:
    def __init__(self, intervalo_segundos: int = INTERVALO_SEGUNDOS, archivo=None):
        self._intervalo = intervalo_segundos
        self._archivo = archivo
        self._detener = threading.Event()
        self._hilo = None

        self._disponible = False
        self.ultimo_refresco_exitoso = None
        self.ultimo_error = None

    def iniciar(self):
        if self._hilo and self._hilo.is_alive():
            return
        self._detener.clear()
        self._hilo = threading.Thread(target=self._bucle, daemon=True, name="espejo-catalogo")
        self._hilo.start()

    def detener(self, timeout=5):
        self._detener.set()
        if self._hilo:
            self._hilo.join(timeout=timeout)

    def disponible(self) -> bool:
        """True si hubo al menos un refresco exitoso -- ver docstring del
        modulo sobre por que no se vuelve False solo porque el ciclo MAS
        RECIENTE haya fallado."""
        return self._disponible

    def ejecutar_ciclo(self) -> dict:
        """
        Un solo ciclo, sincrono -- lo usa el bucle, y sirve para probar
        sin hilos. Lee todo el catalogo activo y el stock agregado de
        BigQuery, y reemplaza el contenido del espejo local completo
        dentro de una sola transaccion (ver
        productos_local.reemplazar_todo).
        """
        try:
            productos = productos_repo.listar_todos_activos()
            stock_por_id = movimientos_repo.stock_de_todos()
            categorias = categorias_repo.listar()

            for producto in productos:
                producto["cantidad"] = stock_por_id.get(producto["id"], 0)

            productos_local.reemplazar_todo(productos, categorias, archivo=self._archivo)
        except Exception as excepcion:  # noqa: BLE001 -- el hilo nunca debe morir por esto
            logger.warning("Espejo de catalogo: fallo el refresco: %s", excepcion)
            self.ultimo_error = str(excepcion)
            return {"exito": False, "error": str(excepcion)}

        self.ultimo_error = None
        self._disponible = True
        self.ultimo_refresco_exitoso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        return {"exito": True, "error": None}

    def _bucle(self):
        while not self._detener.is_set():
            self.ejecutar_ciclo()
            self._detener.wait(self._intervalo)
