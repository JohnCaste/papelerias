"""
Sincronizador: toma lo pendiente del journal local (#14) y lo sube a
BigQuery en segundo plano, sin bloquear nunca la captura de una venta.

    journal.leer_pendientes() -> BigQuery (streaming) -> journal.marcar_confirmada()

Corre como un hilo daemon dentro del mismo proceso de Flask/Waitress
(#12) -- no hace falta un servicio aparte que instalar o mantener en la
PC del negocio.

Sobre el destino: el issue original proponia "Drive, S3, GCS o
Backblaze B2" como destino del respaldo. Eso era de cuando la base
local (SQLite) era la fuente de verdad y el journal era una copia de
seguridad aparte. Con el giro a BigQuery (ver #7/#8), BigQuery YA es el
destino -- no hace falta elegir un almacen de archivos adicional.
"""

import datetime
import json
import logging
import threading
import uuid
from pathlib import Path

import acceso_datos.repositorios.cierres as cierres_repo
from acceso_datos.escrituras import insertar_filas
from almacen_local import cierres as cierres_locales
from almacen_local import compras as compras_locales
from almacen_local import faltantes as faltantes_locales
from almacen_local import journal
from esquema.tablas import DATASET
from utilidades import zona_negocio

TABLA_VENTA = f"{DATASET}.venta"
TABLA_MOVIMIENTO_INVENTARIO = f"{DATASET}.movimiento_inventario"
TABLA_COMPRA_TRABAJADOR = f"{DATASET}.compra_trabajador"
TABLA_ABONO_COMPRA = f"{DATASET}.abono_compra"
TABLA_FALTANTE = f"{DATASET}.faltante"

# Namespace fijo (arbitrario, pero estable entre corridas) para derivar
# ids deterministas de movimiento_inventario -- ver _generar_movimientos_de_venta.
_NAMESPACE_MOVIMIENTO = uuid.uuid5(uuid.NAMESPACE_DNS, "lapape.movimiento_inventario")

INTERVALO_BASE_SEGUNDOS = 5
INTERVALO_MAXIMO_SEGUNDOS = 60
DIAS_HACIA_ATRAS = 30  # cuanto backlog revisar por ciclo -- cubre #55

logger = logging.getLogger(__name__)


def _quitar_campos_locales(venta: dict) -> dict:
    """
    La fila que se manda a BigQuery no lleva 'estado_local' -- es un
    campo que el journal calcula al leer (#14), no existe en el
    esquema de `venta` (#8).
    """
    fila = dict(venta)
    fila.pop("estado_local", None)
    return fila


def _rango_dias_a_revisar(dias_hacia_atras=DIAS_HACIA_ATRAS):
    hoy = zona_negocio.hoy()
    for delta in range(dias_hacia_atras + 1):
        yield hoy - datetime.timedelta(days=delta)


def _generar_movimientos_de_venta(venta: dict) -> list:
    """
    movimiento_inventario (#21) por cada linea tipo 'producto' de una
    venta que ya se subio a BigQuery. Se generan aqui -- no en la captura
    (#20) -- porque la captura solo escribe el journal local y NUNCA
    debe esperar a BigQuery (ver docstring de ventas/capturas.py); el
    descuento de stock puede esperar los segundos que tarda este ciclo.

    El id de cada movimiento es un uuid5 derivado de (venta_id, indice de
    linea): determinista, no aleatorio. Si subir los movimientos falla
    despues de que la venta ya se subio, el siguiente ciclo reintenta
    todo el dia (ver sincronizar_una_vez) y genera EXACTAMENTE los
    mismos ids -- BigQuery los deduplica por row_id (acceso_datos/escrituras.py),
    en vez de descontar el stock dos veces.

    Cantidad: 'cantidad' de la linea es positiva en una venta normal y
    negativa en la fila de reversion de una cancelacion (#26, ver
    acceso_datos/repositorios/ventas.py::cancelar). Negar esa cantidad da
    el signo correcto en ambos casos: sale stock al vender, regresa al
    cancelar -- sin necesitar un caso especial para la reversion.
    """
    tipo_movimiento = "cancelacion" if venta.get("venta_original_id") else "venta"
    movimientos = []
    for indice, linea in enumerate(venta.get("lineas") or []):
        if linea.get("tipo") != "producto":
            continue
        movimientos.append(
            {
                "id": str(uuid.uuid5(_NAMESPACE_MOVIMIENTO, f"{venta['id']}:{indice}")),
                "producto_id": linea["producto_id"],
                "tipo": tipo_movimiento,
                "cantidad": -float(linea["cantidad"]),
                "costo_unitario": linea.get("costo_unitario"),
                "referencia_id": venta["id"],
                "fecha": venta["fecha_hora"],
                "usuario_id": venta["usuario_id"],
            }
        )
    return movimientos


def sincronizar_una_vez(carpeta=None, dias_hacia_atras=DIAS_HACIA_ATRAS) -> dict:
    """
    Un solo ciclo: sube todo lo pendiente que encuentre, del dia mas
    reciente al mas antiguo. Devuelve un resumen -- lo usa tanto el
    hilo en segundo plano como los tests.

    Si un dia falla al subir, se corta ahi (no se siguen intentando los
    demas en este ciclo): lo mas probable es que todos fallen por la
    misma razon (sin internet), y no vale la pena esperar 30 timeouts
    seguidos. El siguiente ciclo reintenta todo -- es seguro, porque
    insertar_filas es idempotente por row_id (#7).
    """
    enviadas = 0
    error = None

    for dia in _rango_dias_a_revisar(dias_hacia_atras):
        pendientes = journal.leer_pendientes(dia, carpeta=carpeta)
        if not pendientes:
            continue

        filas = [_quitar_campos_locales(v) for v in pendientes]
        movimientos = [
            movimiento
            for venta in pendientes
            for movimiento in _generar_movimientos_de_venta(venta)
        ]
        try:
            insertar_filas(TABLA_VENTA, filas)
            # Solo si la venta ya quedo en BigQuery: los movimientos
            # referencian venta_id como referencia_id, no tiene sentido
            # que existan sin la venta que los origino.
            if movimientos:
                insertar_filas(TABLA_MOVIMIENTO_INVENTARIO, movimientos)
        except Exception as excepcion:  # noqa: BLE001 -- cualquier falla de red/API cuenta
            logger.warning("Sincronizacion: fallo subiendo %s ventas del %s: %s", len(filas), dia, excepcion)
            error = excepcion
            break

        for venta in pendientes:
            journal.marcar_confirmada(venta["id"], fecha=dia, carpeta=carpeta)
        enviadas += len(pendientes)

    return {"enviadas": enviadas, "exito": error is None, "error": str(error) if error else None}


def sincronizar_cierres_una_vez(
    carpeta_cierre=None, dias_hacia_atras=DIAS_HACIA_ATRAS
) -> dict:
    """
    Sube a BigQuery los cierres locales (#50/#54) que todavia no se han
    sincronizado. Mismo patron que sincronizar_una_vez para ventas: se
    corta al primer fallo.

    Idempotencia y regeneracion: se compara el `id` del acta local con
    el del acta vigente en BigQuery (`obtener_vigente`). Si no hay
    vigente, se inserta. Si el `id` cambio (hubo una regeneracion local,
    #54), se marca la vigente como `corregido` y se inserta la nueva --
    los lectores toman siempre la ultima por `generado_en`. Si el `id`
    coincide, ya estaba subida y solo se re-marca el journal local.

    Las agregaciones de ventas (semana/mes) suman la tabla `venta`, no
    `cierre`, asi que marcar un acta `corregido` no las altera.
    """
    enviados = 0
    error = None

    for dia in _rango_dias_a_revisar(dias_hacia_atras):
        cierre_local = cierres_locales.obtener_cierre_local(dia, carpeta_cierre)
        if cierre_local is None or cierre_local.get("sincronizado"):
            continue

        try:
            vigente = cierres_repo.obtener_vigente("dia", cierre_local["fecha_inicio"])
            if vigente is None:
                cierres_repo.insertar(cierre_local)
            elif vigente.get("id") != cierre_local["id"]:
                cierres_repo.marcar_corregido(vigente["id"])
                cierres_repo.insertar(cierre_local)
        except Exception as excepcion:  # noqa: BLE001
            logger.warning("Sincronizacion: fallo subiendo el cierre del %s: %s", dia, excepcion)
            error = excepcion
            break

        cierres_locales.marcar_sincronizado(dia, carpeta_cierre)
        enviados += 1

    return {"enviados": enviados, "exito": error is None, "error": str(error) if error else None}


def sincronizar_compras_una_vez(carpeta_compras=None) -> dict:
    """
    Sube a BigQuery los eventos del journal de compras de trabajadores
    (almacen_local/compras.py) que no tienen confirmacion. Las dos tablas
    se insertan antes de confirmar nada: si una falla, el siguiente ciclo
    reintenta todo, y el `id` del evento como row_id evita duplicados.
    """
    pendientes = compras_locales.leer_pendientes(carpeta_compras)
    if not pendientes:
        return {"enviados": 0, "exito": True, "error": None}

    def _fila(evento):
        fila = dict(evento)
        fila.pop("evento", None)
        return fila

    compras = [_fila(e) for e in pendientes if e["evento"] == "compra"]
    abonos = [_fila(e) for e in pendientes if e["evento"] == "abono"]
    try:
        insertar_filas(TABLA_COMPRA_TRABAJADOR, compras)
        insertar_filas(TABLA_ABONO_COMPRA, abonos)
    except Exception as excepcion:  # noqa: BLE001 -- cualquier falla de red/API cuenta
        logger.warning("Sincronizacion: fallo subiendo %s eventos de compras: %s", len(pendientes), excepcion)
        return {"enviados": 0, "exito": False, "error": str(excepcion)}

    compras_locales.marcar_confirmados([e["id"] for e in pendientes], carpeta_compras)
    return {"enviados": len(pendientes), "exito": True, "error": None}


def sincronizar_faltantes_una_vez(carpeta_faltantes=None) -> dict:
    """
    Sube a BigQuery los eventos del journal de faltantes
    (almacen_local/faltantes.py) que no tienen confirmacion. El `id` del
    evento viaja como row_id: un reintento no duplica filas.
    """
    pendientes = faltantes_locales.leer_pendientes(carpeta_faltantes)
    if not pendientes:
        return {"enviados": 0, "exito": True, "error": None}

    filas = [{k: v for k, v in e.items() if k != "evento"} for e in pendientes]
    try:
        insertar_filas(TABLA_FALTANTE, filas)
    except Exception as excepcion:  # noqa: BLE001 -- cualquier falla de red/API cuenta
        logger.warning("Sincronizacion: fallo subiendo %s eventos de faltantes: %s", len(pendientes), excepcion)
        return {"enviados": 0, "exito": False, "error": str(excepcion)}

    faltantes_locales.marcar_confirmados([e["id"] for e in pendientes], carpeta_faltantes)
    return {"enviados": len(pendientes), "exito": True, "error": None}


def _archivo_estado(carpeta=None) -> Path:
    return journal.resolver_carpeta(carpeta) / "estado_sincronizacion.json"


def _leer_estado_persistido(carpeta=None) -> dict:
    archivo = _archivo_estado(carpeta)
    if not archivo.exists():
        return {}
    try:
        return json.loads(archivo.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _guardar_estado_persistido(carpeta, estado: dict):
    archivo = _archivo_estado(carpeta)
    archivo.write_text(json.dumps(estado, ensure_ascii=False), encoding="utf-8")


def calcular_siguiente_espera(fallos_consecutivos: int, base=INTERVALO_BASE_SEGUNDOS, maximo=INTERVALO_MAXIMO_SEGUNDOS) -> float:
    """
    Backoff exponencial: 0 fallos -> espera base; cada fallo consecutivo
    la duplica, hasta el tope. Funcion pura -- separada del hilo para
    poder probarla sin esperar tiempo real en los tests.
    """
    if fallos_consecutivos <= 0:
        return base
    return min(base * (2 ** fallos_consecutivos), maximo)


class Sincronizador:
    """
    Hilo daemon que llama a sincronizar_una_vez() en bucle. Nunca debe
    poder tumbar el proceso: cualquier excepcion inesperada se atrapa,
    se registra y se reintenta en el siguiente ciclo.
    """

    def __init__(
        self,
        carpeta=None,
        carpeta_cierre=None,
        carpeta_compras=None,
        carpeta_faltantes=None,
        intervalo_base=INTERVALO_BASE_SEGUNDOS,
        intervalo_maximo=INTERVALO_MAXIMO_SEGUNDOS,
    ):
        self._carpeta = carpeta
        self._carpeta_cierre = carpeta_cierre
        self._carpeta_compras = carpeta_compras
        self._carpeta_faltantes = carpeta_faltantes
        self._intervalo_base = intervalo_base
        self._intervalo_maximo = intervalo_maximo
        self._detener = threading.Event()
        self._hilo = None
        self._fallos_consecutivos = 0
        self.ultimo_error = None

        # OJO: el estado persistido NO se lee aqui. Construir un
        # Sincronizador no debe tocar disco -- crear_app() (main.py)
        # construye uno en cada import del modulo, incluida la
        # importacion que hace pytest al recolectar tests, antes de que
        # cualquier fixture (incluido el que aisla la carpeta de
        # pruebas) haya corrido. Se carga perezoso, la primera vez que
        # se pide el estado -- ver `estado()`.
        self.ultima_sincronizacion_exitosa = None
        self._estado_persistido_cargado = False

    def iniciar(self):
        if self._hilo and self._hilo.is_alive():
            return
        self._detener.clear()
        self._hilo = threading.Thread(target=self._bucle, daemon=True, name="sincronizador-bigquery")
        self._hilo.start()

    def detener(self, timeout=5):
        self._detener.set()
        if self._hilo:
            self._hilo.join(timeout=timeout)

    def ejecutar_ciclo(self):
        """
        Un solo ciclo, sincrono -- lo usa el bucle, y sirve para probar
        sin hilos. Sube ventas primero; solo intenta cierres si las
        ventas salieron bien (si no hay internet, ambas fallarian igual
        -- no vale la pena el segundo intento en el mismo ciclo).
        """
        try:
            resultado_ventas = sincronizar_una_vez(carpeta=self._carpeta)
        except Exception as excepcion:  # noqa: BLE001 -- el hilo nunca debe morir por esto
            logger.exception("Error inesperado sincronizando ventas")
            resultado_ventas = {"enviadas": 0, "exito": False, "error": str(excepcion)}

        resultado_cierres = {"enviados": 0, "exito": True, "error": None}
        if resultado_ventas["exito"]:
            try:
                resultado_cierres = sincronizar_cierres_una_vez(carpeta_cierre=self._carpeta_cierre)
            except Exception as excepcion:  # noqa: BLE001
                logger.exception("Error inesperado sincronizando cierres")
                resultado_cierres = {"enviados": 0, "exito": False, "error": str(excepcion)}

        # Compras de trabajadores al final y en su propio try: un error aqui
        # nunca debe frenar ventas ni cierres (ya se subieron arriba).
        resultado_compras = {"enviados": 0, "exito": True, "error": None}
        if resultado_ventas["exito"]:
            try:
                resultado_compras = sincronizar_compras_una_vez(carpeta_compras=self._carpeta_compras)
            except Exception as excepcion:  # noqa: BLE001
                logger.exception("Error inesperado sincronizando compras")
                resultado_compras = {"enviados": 0, "exito": False, "error": str(excepcion)}

        # Faltantes igual: al final y en su propio try.
        resultado_faltantes = {"enviados": 0, "exito": True, "error": None}
        if resultado_ventas["exito"]:
            try:
                resultado_faltantes = sincronizar_faltantes_una_vez(carpeta_faltantes=self._carpeta_faltantes)
            except Exception as excepcion:  # noqa: BLE001
                logger.exception("Error inesperado sincronizando faltantes")
                resultado_faltantes = {"enviados": 0, "exito": False, "error": str(excepcion)}

        resultados = (resultado_ventas, resultado_cierres, resultado_compras, resultado_faltantes)
        exito = all(r["exito"] for r in resultados)
        error = next((r["error"] for r in resultados if r["error"]), None)

        if exito:
            self._fallos_consecutivos = 0
            self.ultimo_error = None
            ahora = datetime.datetime.now(datetime.timezone.utc).isoformat()
            self.ultima_sincronizacion_exitosa = ahora
            self._estado_persistido_cargado = True
            _guardar_estado_persistido(self._carpeta, {"ultima_sincronizacion_exitosa": ahora})
        else:
            self._fallos_consecutivos += 1
            self.ultimo_error = error

        return {
            "ventas_enviadas": resultado_ventas["enviadas"],
            "cierres_enviados": resultado_cierres["enviados"],
            "compras_enviadas": resultado_compras["enviados"],
            "faltantes_enviados": resultado_faltantes["enviados"],
            "exito": exito,
            "error": error,
        }

    def _bucle(self):
        while not self._detener.is_set():
            self.ejecutar_ciclo()
            espera = calcular_siguiente_espera(
                self._fallos_consecutivos, self._intervalo_base, self._intervalo_maximo
            )
            self._detener.wait(espera)

    def estado(self) -> dict:
        if not self._estado_persistido_cargado:
            estado_previo = _leer_estado_persistido(self._carpeta)
            self.ultima_sincronizacion_exitosa = estado_previo.get("ultima_sincronizacion_exitosa")
            self._estado_persistido_cargado = True

        return {
            "ultima_sincronizacion_exitosa": self.ultima_sincronizacion_exitosa,
            "fallos_consecutivos": self._fallos_consecutivos,
            "ultimo_error": self.ultimo_error,
        }
