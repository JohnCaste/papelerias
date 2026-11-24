"""
Punto de entrada del backend. Reescrito por #12.

Cambio de comportamiento importante: por defecto ahora corre en modo
PRODUCCION (Waitress, sin depurador, sin CORS). Antes `python main.py`
siempre levantaba con `debug=True` -- el servidor de desarrollo de
Flask, que no aguanta uso real y expone un depurador con ejecucion de
codigo si algo truena.

Para desarrollo local (Vite en :5173 hablando con Flask en :5000, dos
origenes distintos, con recarga automatica) hay que pedirlo explicito:

    $env:ENTORNO = "desarrollo"
    python main.py

Sin esa variable, `python main.py` sirve TODO desde un solo proceso: la
API y el frontend compilado (`frontend/dist`), en el mismo origen -- por
eso ya no hace falta CORS en produccion (ver `crear_app`).
"""

import logging
import os
from datetime import timedelta

from flask import Flask, abort, jsonify, request, send_from_directory
from flask_cors import CORS
from flask_jwt_extended import JWTManager, jwt_required
from werkzeug.exceptions import HTTPException

import autentificacion.credenciales as credenciales
import catalogos.productos as productos
import ventas.cancelaciones as cancelaciones
import ventas.capturas as capturas
import ventas.ediciones as ediciones
import ventas.cierres as cierres
import ventas.resumen_diario as resumen_diario
import usuarios.vistas as usuarios_vistas
import compras.vistas as compras_vistas
from compras.acceso import requiere_duena_lapape
import faltantes.vistas as faltantes_vistas
from almacen_local._seguridad_pruebas import bajo_pruebas
from esquema.tablas import DATASET
from reportes import agregaciones, dashboard
from utilidades import sucursal
from utilidades.registro import configurar_logging

# 'desarrollo' | 'produccion'. Por defecto PRODUCCION -- falla hacia el
# lado seguro si alguien corre esto sin pensar en la variable.
ENTORNO = os.environ.get("ENTORNO", "produccion")

# Logging a archivo (#13): se configura una sola vez, aqui, ANTES de
# construir crear_app() (que arma Sincronizador/ProgramadorCierre) -- asi
# esos hilos en segundo plano ya escriben a archivo desde su primer
# mensaje, sin que ese codigo cambie (ver utilidades/registro.py). Se
# salta bajo pytest: los tests no deben tocar backend/datos_locales/logs/
# real (mismo criterio que journal.py/cierres.py, ver
# almacen_local/_seguridad_pruebas.py).
if not bajo_pruebas():
    configurar_logging(entorno=ENTORNO)

logger = logging.getLogger(__name__)

# Valor de solo desarrollo/tests para JWT_SECRET_KEY (ver
# _resolver_jwt_secret_key) -- nunca usar en produccion. Es publico a
# proposito (queda en el codigo): si esta cadena firma un token real, algo
# esta mal configurado.
_JWT_SECRET_KEY_DESARROLLO = "clave-de-desarrollo-nunca-usar-en-produccion"


def _resolver_jwt_secret_key() -> str:
    """
    La llave con la que se firman los tokens de sesion SHALL venir de la
    variable de entorno JWT_SECRET_KEY (en backend/.env), nunca de un
    valor fijo en el codigo -- antes vivia hardcodeada aqui mismo
    ("<secreto-viejo-ya-rotado>", visible en el historial de git). Con el
    backend corriendo siempre (arranque automatico / servicio de
    Windows) y expuesto en la red local via Waitress, ese secreto
    expuesto deja de ser un detalle pendiente y pasa a ser una forma de
    forjar sesiones validas.

    En desarrollo/tests, si la variable no esta definida, se usa un
    valor fijo documentado como tal -- para no exigir un .env a cada
    entorno de pruebas ni rendir el flujo de `ENTORNO=desarrollo`.
    En produccion (el modo por defecto), si falta la variable el proceso
    SHALL rehusarse a arrancar: es preferible que truene aqui, con un
    mensaje claro, a que sirva sesiones firmadas con un secreto debil o
    vacio.
    """
    secreto = os.environ.get("JWT_SECRET_KEY")
    if secreto:
        return secreto

    if ENTORNO == "desarrollo" or bajo_pruebas():
        return _JWT_SECRET_KEY_DESARROLLO

    raise RuntimeError(
        "Falta la variable de entorno JWT_SECRET_KEY. Configurala en "
        "backend\\.env antes de arrancar en produccion -- ver INSTALAR.md "
        "para como generar un valor nuevo. El proceso no arranca sin "
        "ella a proposito: es preferible que falle aqui a que sirva "
        "sesiones firmadas con un secreto debil."
    )

# frontend/package.json ya compila aqui (`vite build` -> outDir por
# defecto 'dist'), asi que no hace falta copiar nada: este backend sirve
# esa carpeta directamente.
CARPETA_FRONTEND = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "frontend", "dist"
)


def crear_app(carpeta_frontend: str = CARPETA_FRONTEND) -> Flask:
    # static_folder=None: el manejo de estaticos se hace a mano en
    # _registrar_frontend, para poder hacer fallback a index.html en
    # las rutas de React Router (SPA) -- el static de Flask por si solo
    # no sabe hacer eso.
    app = Flask(__name__, static_folder=None)

    if ENTORNO == "desarrollo":
        # Solo hace falta en desarrollo: Vite (:5173) y Flask (:5000)
        # son dos origenes distintos. En produccion todo se sirve desde
        # el mismo proceso -- ver el criterio de aceptacion de #12.
        CORS(app, resources={r"/api/*": {"origins": ["http://localhost:5173", "http://localhost:4200"]}})
    app.config["CORS_HEADERS"] = "Content-Type"

    # Tope duro de cuerpo de peticion. Se deja por encima del limite real
    # de subida de imagen (imagenes.MAX_SUBIDA_MB) para que el handler
    # devuelva un 400 con mensaje claro en vez de un 413 seco de Werkzeug.
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

    app.config["JWT_SECRET_KEY"] = _resolver_jwt_secret_key()
    # 24h: el POS no reintenta el login solo (ver services/*.ts, ningun
    # fetch usa 'refresh_token' pese a que el backend ya expone
    # /api/autentificacion/refresh) -- con 2h el token expiraba a media
    # jornada y una venta fallaba con "No se pudo registrar la venta" sin
    # pista de que hacia falta reloguear. Cubre un turno completo del
    # negocio; REFRESH dura una semana como margen si la PC queda
    # encendida entre dias sin que nadie cierre sesion.
    app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=24)
    app.config["JWT_REFRESH_TOKEN_EXPIRES"] = timedelta(days=7)
    JWTManager(app)

    # Candado de sucursal: ANTES de construir el sincronizador, para que
    # una PC cuyo .env cambio de dataset nunca suba su diario local a la
    # base de otra tienda (ver utilidades/sucursal.py). Bajo pruebas se
    # salta -- mismo criterio que journal.py/cierres.py con su carpeta real.
    if not bajo_pruebas():
        sucursal.verificar_candado(DATASET)

    # Se construyen aqui (no en __main__) para que el endpoint de estado
    # (#55) siempre tenga a quien preguntarle -- pero SOLO se arrancan
    # (.iniciar()) desde __main__, para que importar main.py o construir
    # la app en un test nunca dispare un hilo real hablandole a BigQuery.
    from almacen_local.espejo_catalogo import EspejoCatalogo
    from almacen_local.programador_cierre import ProgramadorCierre
    from almacen_local.sincronizador import Sincronizador

    app.sincronizador = Sincronizador()
    app.programador_cierre = ProgramadorCierre()
    # Espejo local de solo lectura del catalogo (#13) -- ver
    # catalogos/productos.py::_con_fallback, que lo consulta via
    # current_app.espejo_catalogo.
    app.espejo_catalogo = EspejoCatalogo()

    _registrar_rutas_api(app)
    _registrar_frontend(app, carpeta_frontend)
    _registrar_manejador_de_errores(app)
    return app


def _registrar_manejador_de_errores(app: Flask):
    """
    Sin esto, una excepcion no capturada en una vista solo se ve si la
    ventana de la consola sigue abierta (Flask/Waitress no dejan rastro
    en disco por si solos) -- inutil una vez que el backend corra sin
    consola visible. Registra el traceback completo con nivel ERROR antes
    de devolver el 500, sin cambiar la respuesta que ya recibia el cliente.
    """

    @app.errorhandler(Exception)
    def _manejar_error_no_capturado(error):
        if isinstance(error, HTTPException):
            # abort(404)/abort(400) etc. son respuestas a proposito, no
            # fallas inesperadas -- Flask ya sabe convertirlas a su
            # respuesta HTTP normal, no hace falta loguearlas como ERROR.
            return error

        logger.error(
            "Excepcion no capturada atendiendo %s %s",
            request.method,
            request.path,
            exc_info=True,
        )
        return jsonify(error="Error interno del servidor"), 500


def _registrar_rutas_api(app: Flask):
    # Publico a proposito: la pantalla de login ya muestra en que sucursal
    # se esta entrando, antes de tener token.
    @app.route("/api/sucursal", methods=["GET"])
    def datosSucursal():
        return jsonify(nombre=sucursal.nombre_sucursal(DATASET), dataset=DATASET)

    @app.route("/api/autentificacion/login", methods=["POST"])
    @jwt_required(optional=True)
    def crearToken():
        return credenciales.crear_token()

    @app.route("/api/autentificacion/refresh", methods=["POST"])
    @jwt_required(refresh=True)
    def refresh():
        return credenciales.refresh()

    # --------------------------------------------------- USUARIOS (#46)

    @app.route("/api/usuarios", methods=["GET"])
    @jwt_required(optional=False)
    def listarUsuarios():
        return usuarios_vistas.listar_usuarios()

    @app.route("/api/usuarios/foto", methods=["POST"])
    @jwt_required(optional=False)
    def subirFotoPerfil():
        return usuarios_vistas.subir_foto_perfil()

    @app.route("/api/usuarios/<usuario_id>/rol", methods=["POST"])
    @jwt_required(optional=False)
    def cambiarRolUsuario(usuario_id):
        return usuarios_vistas.cambiar_rol(usuario_id)

    # --------------------------------------------------- CATALOGOS

    @app.route("/api/catalogo", methods=["GET"])
    @jwt_required(optional=False)
    def traerProductos():
        return productos.traer_productos()

    @app.route("/api/catalogo/paginador", methods=["GET"])
    @jwt_required(optional=False)
    def limiteProductos():
        return productos.limite_productos()

    @app.route("/api/catalogo/buscar", methods=["GET"])
    @jwt_required(optional=False)
    def buscarProductos():
        return productos.buscar_productos()

    @app.route("/api/catalogo/categorias", methods=["GET"])
    @jwt_required(optional=False)
    def listarCategorias():
        return productos.listar_categorias()

    @app.route("/api/catalogo/marcas", methods=["GET"])
    @jwt_required(optional=False)
    def listarMarcas():
        return productos.listar_marcas()

    @app.route("/api/catalogo/imagen", methods=["POST"])
    @jwt_required(optional=False)
    def subirImagenProducto():
        return productos.subir_imagen()

    @app.route("/api/catalogo", methods=["POST"])
    @jwt_required(optional=False)
    def agregarProductos():
        return productos.agregar_productos()

    @app.route("/api/catalogo", methods=["DELETE"])
    @jwt_required(optional=False)
    def eliminarProductos():
        return productos.eliminar_productos()

    @app.route("/api/catalogo", methods=["PATCH"])
    @jwt_required(optional=False)
    def actualizarProductos():
        return productos.actualizar_productos()

    # --------------------------------------------------- AGREGACIONES (#34)

    @app.route("/api/agregaciones", methods=["GET"])
    @jwt_required(optional=False)
    def obtenerAgregaciones():
        return agregaciones.obtener_agregaciones()

    @app.route("/api/dashboard/dia", methods=["GET"])
    @jwt_required(optional=False)
    def dashboardDia():
        return dashboard.resumen_dia()

    # --------------------------------------------------------- VENTAS (#20)

    @app.route("/api/ventas", methods=["POST"])
    @jwt_required(optional=False)
    def capturarVenta():
        return capturas.capturar_venta()

    @app.route("/api/ventas/dia", methods=["GET"])
    @jwt_required(optional=False)
    def ventasDelDia():
        return capturas.listar_ventas_del_dia()

    @app.route("/api/ventas/<venta_id>/cancelar", methods=["POST"])
    @jwt_required(optional=False)
    def cancelarVenta(venta_id):
        return cancelaciones.cancelar_venta(venta_id)

    @app.route("/api/ventas/<venta_id>/editar", methods=["POST"])
    @jwt_required(optional=False)
    def editarVenta(venta_id):
        return ediciones.editar_venta(venta_id)

    @app.route("/api/ventas/resumen-dia", methods=["POST"])
    @jwt_required(optional=False)
    def guardarResumenDia():
        return resumen_diario.guardar_resumen_dia()

    @app.route("/api/ventas/gasto-dia", methods=["GET"])
    @jwt_required(optional=False)
    def obtenerGastoDia():
        return resumen_diario.obtener_gasto_dia()

    # ------------------------------------- COMPRAS DE TRABAJADORES
    # Solo sucursal original + rol dueno (compras/acceso.py). Leen y
    # escriben el journal local: funcionan sin internet.

    @app.route("/api/compras", methods=["GET"])
    @jwt_required(optional=False)
    @requiere_duena_lapape
    def listarCompras():
        return compras_vistas.listar()

    @app.route("/api/compras", methods=["POST"])
    @jwt_required(optional=False)
    @requiere_duena_lapape
    def crearCompra():
        return compras_vistas.crear()

    @app.route("/api/compras/abonos", methods=["GET"])
    @jwt_required(optional=False)
    @requiere_duena_lapape
    def listarAbonosCompras():
        return compras_vistas.listar_abonos()

    @app.route("/api/compras/<compra_id>", methods=["PUT"])
    @jwt_required(optional=False)
    @requiere_duena_lapape
    def editarCompra(compra_id):
        return compras_vistas.editar(compra_id)

    @app.route("/api/compras/<compra_id>", methods=["DELETE"])
    @jwt_required(optional=False)
    @requiere_duena_lapape
    def eliminarCompra(compra_id):
        return compras_vistas.eliminar(compra_id)

    @app.route("/api/compras/<compra_id>/abonos", methods=["POST"])
    @jwt_required(optional=False)
    @requiere_duena_lapape
    def abonarCompra(compra_id):
        return compras_vistas.abonar(compra_id)

    @app.route("/api/compras/abonos/<abono_id>", methods=["DELETE"])
    @jwt_required(optional=False)
    @requiere_duena_lapape
    def eliminarAbonoCompra(abono_id):
        return compras_vistas.eliminar_abono(abono_id)

    # ------------------------------------------------ LISTA DE FALTANTES
    # Todos los usuarios, todas las sucursales. Permisos finos (comprado,
    # eliminar) en faltantes/servicio.py. Journal local: sin internet.

    @app.route("/api/faltantes", methods=["GET"])
    @jwt_required(optional=False)
    def listarFaltantes():
        return faltantes_vistas.listar()

    @app.route("/api/faltantes", methods=["POST"])
    @jwt_required(optional=False)
    def crearFaltante():
        return faltantes_vistas.crear()

    @app.route("/api/faltantes/<faltante_id>", methods=["PUT"])
    @jwt_required(optional=False)
    def editarFaltante(faltante_id):
        return faltantes_vistas.editar(faltante_id)

    @app.route("/api/faltantes/<faltante_id>/estado", methods=["PUT"])
    @jwt_required(optional=False)
    def cambiarEstadoFaltante(faltante_id):
        return faltantes_vistas.cambiar_estado(faltante_id)

    @app.route("/api/faltantes/<faltante_id>", methods=["DELETE"])
    @jwt_required(optional=False)
    def eliminarFaltante(faltante_id):
        return faltantes_vistas.eliminar(faltante_id)

    # --------------------------------------------------------- CIERRES (#50)

    @app.route("/api/cierres/dia", methods=["POST"])
    @jwt_required(optional=False)
    def cerrarDiaManual():
        return cierres.cerrar_dia_manual()

    @app.route("/api/cierres/dia/regenerar", methods=["POST"])
    @jwt_required(optional=False)
    def regenerarActaDia():
        return cierres.regenerar_cierre_dia()

    @app.route("/api/cierres/dia", methods=["GET"])
    @jwt_required(optional=False)
    def estadoDia():
        return cierres.obtener_estado_dia()

    # ------------------------------------------------- SINCRONIZACION (#55)

    @app.route("/api/sincronizacion/estado", methods=["GET"])
    @jwt_required(optional=False)
    def estadoSincronizacion():
        return jsonify(app.sincronizador.estado())


def _registrar_frontend(app: Flask, carpeta_frontend: str):
    """
    Sirve el build de produccion del frontend y hace de fallback a
    index.html para las rutas de React Router -- /catalogo, /ventas,
    /admin no son archivos reales en disco, los resuelve el router del
    lado del cliente una vez que index.html carga.
    """

    @app.route("/", defaults={"ruta": ""})
    @app.route("/<path:ruta>")
    def _servir_frontend(ruta):
        if ruta.startswith("api/"):
            # No deberia llegar aqui: las rutas /api/* estan registradas
            # arriba y Werkzeug las resuelve primero por ser mas
            # especificas. Si de todos modos llega, es una ruta de API
            # que no existe -- 404, no la pantalla del SPA.
            abort(404)

        archivo = os.path.join(carpeta_frontend, ruta) if ruta else None
        if archivo and os.path.isfile(archivo):
            return send_from_directory(carpeta_frontend, ruta)

        indice = os.path.join(carpeta_frontend, "index.html")
        if not os.path.isfile(indice):
            abort(
                404,
                description=(
                    "No se encontro frontend/dist/index.html. Corre "
                    "'npm run build' dentro de frontend/ antes de "
                    "levantar el backend."
                ),
            )
        return send_from_directory(carpeta_frontend, "index.html")


app = crear_app()


def iniciar_hilos_de_fondo(app: Flask):
    """
    sincronizador (#15), programador_cierre (#50) y espejo_catalogo (#13)
    ya existen desde crear_app() -- esto solo arranca los hilos. Separado
    de `iniciar_servidor` (y de `if __name__ == "__main__":`) para que el
    servicio de Windows (servicio_windows.py) pueda llamar exactamente a
    la misma logica que `python main.py` en consola, sin duplicarla.
    Nunca se llama al importar main.py ni al construir la app en un test,
    solo desde aqui o desde el servicio.
    """
    app.sincronizador.iniciar()
    app.programador_cierre.iniciar()
    app.espejo_catalogo.iniciar()


def iniciar_servidor(app: Flask, puerto: int):
    """
    Arranca el servidor HTTP: el servidor de desarrollo de Flask si
    ENTORNO=desarrollo, Waitress en cualquier otro caso (produccion, el
    default). Bloquea el hilo que la llama hasta que el servidor se
    detiene. Misma logica para `python main.py` en consola y para el
    servicio de Windows.
    """
    if ENTORNO == "desarrollo":
        app.run(debug=True, host="0.0.0.0", port=puerto)
    else:
        from waitress import serve

        # logger, no print(): un Servicio de Windows no tiene una
        # consola valida donde print() pueda escribir sin problema.
        logger.info("Produccion (Waitress) -- http://localhost:%s", puerto)
        serve(app, host="0.0.0.0", port=puerto)


if __name__ == "__main__":
    iniciar_hilos_de_fondo(app)
    iniciar_servidor(app, int(os.environ.get("PORT", 5000)))
