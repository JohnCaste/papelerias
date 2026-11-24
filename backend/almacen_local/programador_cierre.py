"""
Hilo daemon que dispara el cierre de dia automatico y perezoso (#50).
Mismo patron que el sincronizador (#15): corre dentro del proceso de
Flask/Waitress, se arranca solo desde __main__ en main.py.

Al iniciar: cierra perezosamente lo que haya quedado pendiente de dias
anteriores (una vez). Despues, revisa cada `intervalo_revision_segundos`
si ya se cruzo la hora de cierre configurada y el dia de hoy sigue
abierto -- si es asi, lo cierra con `generado_por='automatico'`.

Ningun cierre generado aqui depende de que la PC este encendida a una
hora exacta: si esta apagada a la hora de cierre, el disparador perezoso
lo cubre al prender de nuevo (ver cierres.cerrar_dias_pendientes).

Todo se evalua con el reloj del NEGOCIO (utilidades/zona_negocio.py), no
con el reloj naive de la PC.
"""

import datetime
import logging
import threading

from almacen_local import cierres
from almacen_local.cierres import HORA_CIERRE_POR_DEFECTO
from utilidades import zona_negocio

INTERVALO_REVISION_SEGUNDOS = 300  # 5 minutos: no hace falta mas fino

logger = logging.getLogger(__name__)


class ProgramadorCierre:
    def __init__(
        self,
        hora_cierre: datetime.time = HORA_CIERRE_POR_DEFECTO,
        intervalo_revision_segundos: int = INTERVALO_REVISION_SEGUNDOS,
        carpeta_journal=None,
        carpeta_cierre=None,
    ):
        self._hora_cierre = hora_cierre
        self._intervalo = intervalo_revision_segundos
        self._carpeta_journal = carpeta_journal
        self._carpeta_cierre = carpeta_cierre
        self._detener = threading.Event()
        self._hilo = None

    def iniciar(self):
        if self._hilo and self._hilo.is_alive():
            return
        self._detener.clear()
        self._hilo = threading.Thread(target=self._bucle, daemon=True, name="programador-cierre")
        self._hilo.start()

    def detener(self, timeout=5):
        self._detener.set()
        if self._hilo:
            self._hilo.join(timeout=timeout)

    def ejecutar_catchup_perezoso(self):
        """Cierra lo pendiente de dias anteriores. Seguro de llamar varias veces."""
        try:
            return cierres.cerrar_dias_pendientes(
                generado_por="perezoso",
                carpeta_journal=self._carpeta_journal,
                carpeta_cierre=self._carpeta_cierre,
            )
        except Exception:  # noqa: BLE001 -- el hilo nunca debe morir por esto
            logger.exception("Error en el cierre perezoso")
            return []

    def revisar_cierre_automatico(self, ahora: datetime.datetime | None = None) -> dict | None:
        """
        Al cruzarse la hora de cierre:
        - si hoy no tiene acta, la genera (`automatico`);
        - si hoy tiene un acta PROVISIONAL (forzada antes de la hora),
          la regenera una vez para consolidar las ventas posteriores y
          dejarla definitiva;
        - si hoy ya tiene un acta definitiva, no hace nada.

        Recibe `ahora` para poder probarse sin depender del reloj real:
        se lee como reloj de pared del negocio (un naive ya viene en esa
        hora; un aware se convierte).
        """
        ahora = zona_negocio.reloj(ahora)
        hoy = ahora.date()

        if ahora.time() < self._hora_cierre:
            return None

        acta = cierres.obtener_cierre_local(hoy, self._carpeta_cierre)
        try:
            if acta is None:
                return cierres.generar_cierre_dia(
                    hoy,
                    "automatico",
                    carpeta_journal=self._carpeta_journal,
                    carpeta_cierre=self._carpeta_cierre,
                )
            if acta.get("provisional"):
                return cierres.regenerar_cierre_dia(
                    hoy,
                    "automatico",
                    carpeta_journal=self._carpeta_journal,
                    carpeta_cierre=self._carpeta_cierre,
                )
            return None
        except Exception:  # noqa: BLE001
            logger.exception("Error generando el cierre automatico del dia")
            return None

    def _bucle(self):
        self.ejecutar_catchup_perezoso()
        while not self._detener.is_set():
            self.revisar_cierre_automatico()
            self._detener.wait(self._intervalo)
