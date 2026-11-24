"""
Envuelve el backend como un Servicio de Windows real (#servicio),
usando `pywin32` -- arranca con el sistema operativo, sin necesidad de
que nadie inicie sesion, y Windows lo reinicia solo si el proceso
truena (configurado por scripts/instalar_servicio.ps1, ver ese script).

No es un mecanismo alternativo al acceso directo de Inicio existente
(scripts/iniciar_app.ps1) -- es un mecanismo ADICIONAL. Ese acceso
directo ya revisa si el puerto 5000 esta en uso antes de intentar
levantar el backend, asi que con el servicio corriendo simplemente
detecta que ya esta arriba y solo abre el navegador (sin tocar ese
script). Instalar el servicio es opcional; ver INSTALAR.md.

Uso (siempre como Administrador):

    venv\\Scripts\\python.exe servicio_windows.py install
    venv\\Scripts\\python.exe servicio_windows.py start
    venv\\Scripts\\python.exe servicio_windows.py stop
    venv\\Scripts\\python.exe servicio_windows.py remove

(scripts/instalar_servicio.ps1 automatiza install + start + el
reinicio-ante-fallo, que pywin32 no configura por si solo.)
"""

import logging
import os
import sys
import threading

# Fija el directorio de trabajo a backend/ ANTES de importar `main` --
# el codigo del backend ya no depende del CWD para nada critico (ver
# el fix de autentificacion/serviciosCloud.py, #servicio), pero se deja
# aqui como defensa adicional: mas codigo del que pudiera depender del
# CWD en el futuro (scripts externos, herramientas de terceros) sigue
# funcionando igual que si se hubiera lanzado `python main.py` a mano
# desde `backend/`.
_RAIZ_BACKEND = os.path.dirname(os.path.abspath(__file__))
os.chdir(_RAIZ_BACKEND)
if _RAIZ_BACKEND not in sys.path:
    sys.path.insert(0, _RAIZ_BACKEND)

import servicemanager  # noqa: E402 -- import tras el os.chdir/sys.path, a proposito
import win32event  # noqa: E402
import win32service  # noqa: E402
import win32serviceutil  # noqa: E402

import main as modulo_main  # noqa: E402

logger = logging.getLogger(__name__)


class ServicioLaPapeleria(win32serviceutil.ServiceFramework):
    _svc_name_ = "LaPapeleria"
    _svc_display_name_ = "La Papeleria - Backend"
    _svc_description_ = (
        "Sirve la API y el catalogo de La Papeleria (Flask + Waitress). "
        "Ver INSTALAR.md en la carpeta del proyecto."
    )

    def __init__(self, args):
        super().__init__(args)
        self._evento_detener = win32event.CreateEvent(None, 0, 0, None)
        self._hilo_servidor = None

    def SvcDoRun(self):
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, ""),
        )

        # Misma logica exacta que `python main.py` en consola -- ningun
        # camino de arranque duplicado entre los dos (ver main.py).
        modulo_main.iniciar_hilos_de_fondo(modulo_main.app)

        puerto = int(os.environ.get("PORT", 5000))
        self._hilo_servidor = threading.Thread(
            target=modulo_main.iniciar_servidor,
            args=(modulo_main.app, puerto),
            daemon=True,
            name="servidor-http",
        )
        self._hilo_servidor.start()

        # SvcDoRun() debe bloquear hasta que se pida detener el servicio
        # -- el servidor HTTP corre en su propio hilo (arriba); este
        # espera al evento que dispara SvcStop().
        win32event.WaitForSingleObject(self._evento_detener, win32event.INFINITE)

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)

        # Los tres hilos de fondo son cooperativos (threading.Event) y
        # se detienen limpio. El hilo del servidor HTTP (Waitress) NO
        # tiene una forma sencilla de pedirle que pare desde aqui -- se
        # deja que el SCM termine el proceso tras esto (ver design.md,
        # Risk aceptado: el journal local ya tolera un corte abrupto).
        try:
            modulo_main.app.sincronizador.detener()
            modulo_main.app.programador_cierre.detener()
            modulo_main.app.espejo_catalogo.detener()
        except Exception:  # noqa: BLE001 -- nunca dejar SvcStop a medias por esto
            logger.exception("Error deteniendo los hilos de fondo al parar el servicio")

        win32event.SetEvent(self._evento_detener)


if __name__ == "__main__":
    win32serviceutil.HandleCommandLine(ServicioLaPapeleria)
