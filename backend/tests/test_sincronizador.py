"""
Tests de almacen_local/sincronizador.py -- sin BigQuery real, sin hilos
donde se pueda evitar (el backoff se prueba como funcion pura).
"""

import datetime
import time

import pytest

import acceso_datos.repositorios.cierres as cierres_repo
from almacen_local import journal, sincronizador


@pytest.fixture(autouse=True)
def _sin_bigquery_real_para_cierres(monkeypatch):
    """
    Red de seguridad para TODO este archivo: si algun test deja
    `carpeta_cierre` sin apuntar a una carpeta temporal, esto evita que
    se intente una llamada real a BigQuery en vez de fallar en silencio
    o tronar.
    """
    monkeypatch.setattr(cierres_repo, "existe", lambda *a, **k: False)
    monkeypatch.setattr(cierres_repo, "obtener_vigente", lambda *a, **k: None)
    monkeypatch.setattr(cierres_repo, "marcar_corregido", lambda *a, **k: None)
    monkeypatch.setattr(cierres_repo, "insertar", lambda *a, **k: None)


def _venta(**overrides):
    datos = {
        "total": 20,
        "metodo_pago": "efectivo",
        "usuario_id": "u1",
        "lineas": [
            {
                "tipo": "categoria",
                "categoria": "pilas",
                "cantidad": 1,
                "precio_unitario": 20,
                "subtotal": 20,
            }
        ],
    }
    datos.update(overrides)
    return datos


def _linea_producto(producto_id="p1", cantidad=3, precio_unitario=5):
    return {
        "tipo": "producto",
        "producto_id": producto_id,
        "cantidad": cantidad,
        "precio_unitario": precio_unitario,
        "subtotal": cantidad * precio_unitario,
    }


# --------------------------------------------------- calcular_siguiente_espera

def test_backoff_sin_fallos_usa_el_intervalo_base():
    assert sincronizador.calcular_siguiente_espera(0, base=5, maximo=60) == 5


def test_backoff_crece_exponencial_con_cada_fallo():
    assert sincronizador.calcular_siguiente_espera(1, base=5, maximo=60) == 10
    assert sincronizador.calcular_siguiente_espera(2, base=5, maximo=60) == 20
    assert sincronizador.calcular_siguiente_espera(3, base=5, maximo=60) == 40


def test_backoff_no_supera_el_maximo():
    assert sincronizador.calcular_siguiente_espera(20, base=5, maximo=60) == 60


# --------------------------------------------------- _generar_movimientos_de_venta (#21)

def test_generar_movimientos_ignora_lineas_que_no_son_producto():
    venta = {"id": "v1", "fecha_hora": "2026-08-31", "usuario_id": "u1", "lineas": [
        {"tipo": "categoria", "categoria": "dulces", "cantidad": 1},
    ]}
    assert sincronizador._generar_movimientos_de_venta(venta) == []


def test_generar_movimientos_de_venta_normal_resta_stock():
    venta = _venta(id="v1", lineas=[_linea_producto("p1", cantidad=3)])
    venta["fecha_hora"] = "2026-08-31T12:00:00+00:00"

    movimientos = sincronizador._generar_movimientos_de_venta(venta)

    assert len(movimientos) == 1
    mov = movimientos[0]
    assert mov["producto_id"] == "p1"
    assert mov["tipo"] == "venta"
    assert mov["cantidad"] == -3.0  # sale stock
    assert mov["referencia_id"] == "v1"
    assert mov["usuario_id"] == "u1"


def test_generar_movimientos_de_reversion_devuelve_stock():
    """
    Una cancelacion (#26) es una venta con venta_original_id y lineas ya
    negadas -- el mismo calculo de signo debe devolver el stock, no
    volver a restarlo.
    """
    venta = _venta(
        id="v-reversion",
        venta_original_id="v1",
        lineas=[_linea_producto("p1", cantidad=-3)],
    )
    venta["fecha_hora"] = "2026-08-31T12:00:00+00:00"

    movimientos = sincronizador._generar_movimientos_de_venta(venta)

    assert movimientos[0]["tipo"] == "cancelacion"
    assert movimientos[0]["cantidad"] == 3.0  # entra de vuelta


def test_generar_movimientos_de_edicion_de_monto_netean_a_cero():
    """
    Editar el monto (editar-ventas) escribe una reversion (lineas negadas)
    y una recaptura (lineas con la MISMA cantidad que la original). Como la
    cantidad no cambia, la reversion devuelve stock y la recaptura lo vuelve
    a descontar: el efecto neto sobre el inventario es cero. Los ids de
    movimiento difieren entre ambas filas, asi que las dos se insertan.
    """
    reversa = _venta(
        id="v1-editada-reversa",
        venta_original_id="v1",
        lineas=[_linea_producto("p1", cantidad=-3)],
    )
    recaptura = _venta(
        id="v1-editada",
        venta_original_id="v1",
        lineas=[_linea_producto("p1", cantidad=3)],
    )
    for v in (reversa, recaptura):
        v["fecha_hora"] = "2026-08-31T12:00:00+00:00"

    mov_reversa = sincronizador._generar_movimientos_de_venta(reversa)
    mov_recaptura = sincronizador._generar_movimientos_de_venta(recaptura)

    assert mov_reversa[0]["cantidad"] == 3.0  # entra de vuelta
    assert mov_recaptura[0]["cantidad"] == -3.0  # vuelve a salir
    assert mov_reversa[0]["cantidad"] + mov_recaptura[0]["cantidad"] == 0
    assert mov_reversa[0]["id"] != mov_recaptura[0]["id"]


def test_generar_movimientos_ids_deterministas_por_venta_e_indice():
    venta = _venta(
        id="v1",
        lineas=[_linea_producto("p1", cantidad=1), _linea_producto("p2", cantidad=2)],
    )
    venta["fecha_hora"] = "2026-08-31T12:00:00+00:00"

    primera_pasada = sincronizador._generar_movimientos_de_venta(venta)
    segunda_pasada = sincronizador._generar_movimientos_de_venta(venta)

    ids_primera = [m["id"] for m in primera_pasada]
    ids_segunda = [m["id"] for m in segunda_pasada]
    assert ids_primera == ids_segunda  # mismo id en cada corrida -> BigQuery deduplica
    assert len(set(ids_primera)) == 2  # pero distinto por linea


# --------------------------------------------------------- sincronizar_una_vez

def test_sincronizar_una_vez_sin_pendientes_no_hace_nada(tmp_path, monkeypatch):
    llamado = []
    monkeypatch.setattr(sincronizador, "insertar_filas", lambda *a, **k: llamado.append(1))

    resultado = sincronizador.sincronizar_una_vez(carpeta=tmp_path)

    assert resultado == {"enviadas": 0, "exito": True, "error": None}
    assert llamado == []


def test_sincronizar_una_vez_sube_lo_pendiente_y_lo_marca_confirmado(tmp_path, monkeypatch):
    hoy = datetime.datetime.now(datetime.timezone.utc)
    v1 = journal.escribir_venta(_venta(fecha_hora=hoy), carpeta=tmp_path)
    v2 = journal.escribir_venta(_venta(fecha_hora=hoy, total=30), carpeta=tmp_path)

    capturado = {}
    monkeypatch.setattr(
        sincronizador, "insertar_filas", lambda tabla, filas: capturado.update(tabla=tabla, filas=filas)
    )

    resultado = sincronizador.sincronizar_una_vez(carpeta=tmp_path)

    assert resultado == {"enviadas": 2, "exito": True, "error": None}
    assert len(capturado["filas"]) == 2
    assert journal.leer_pendientes(hoy.date(), carpeta=tmp_path) == []
    ids_enviados = {f["id"] for f in capturado["filas"]}
    assert ids_enviados == {v1["id"], v2["id"]}


def test_la_fila_enviada_a_bigquery_no_lleva_estado_local(tmp_path, monkeypatch):
    hoy = datetime.datetime.now(datetime.timezone.utc)
    journal.escribir_venta(_venta(fecha_hora=hoy), carpeta=tmp_path)

    capturado = {}
    monkeypatch.setattr(
        sincronizador, "insertar_filas", lambda tabla, filas: capturado.update(filas=filas)
    )
    sincronizador.sincronizar_una_vez(carpeta=tmp_path)

    assert "estado_local" not in capturado["filas"][0]


def test_sincronizar_una_vez_si_falla_no_marca_confirmada_nada(tmp_path, monkeypatch):
    hoy = datetime.datetime.now(datetime.timezone.utc)
    journal.escribir_venta(_venta(fecha_hora=hoy), carpeta=tmp_path)

    def falla(*a, **k):
        raise ConnectionError("sin internet")

    monkeypatch.setattr(sincronizador, "insertar_filas", falla)

    resultado = sincronizador.sincronizar_una_vez(carpeta=tmp_path)

    assert resultado["exito"] is False
    assert "sin internet" in resultado["error"]
    assert len(journal.leer_pendientes(hoy.date(), carpeta=tmp_path)) == 1


def test_sincronizar_una_vez_recoge_backlog_de_varios_dias(tmp_path, monkeypatch):
    hoy = datetime.date.today()
    for delta in range(3):
        fecha = datetime.datetime.combine(
            hoy - datetime.timedelta(days=delta), datetime.time(12, 0), tzinfo=datetime.timezone.utc
        )
        journal.escribir_venta(_venta(fecha_hora=fecha), carpeta=tmp_path)

    enviadas_totales = []
    monkeypatch.setattr(
        sincronizador,
        "insertar_filas",
        lambda tabla, filas: enviadas_totales.extend(filas),
    )

    resultado = sincronizador.sincronizar_una_vez(carpeta=tmp_path)

    assert resultado["enviadas"] == 3
    assert len(enviadas_totales) == 3


def test_sincronizar_sube_movimientos_de_inventario_para_lineas_de_producto(tmp_path, monkeypatch):
    """Criterio de aceptacion de #21: al subir una venta detallada, sale
    un movimiento_inventario tipo 'venta' que descuenta exactamente lo
    vendido."""
    hoy = datetime.datetime.now(datetime.timezone.utc)
    venta = journal.escribir_venta(
        _venta(fecha_hora=hoy, detallada=True, lineas=[_linea_producto("lapiz-1", cantidad=3)]),
        carpeta=tmp_path,
    )

    llamadas = []
    monkeypatch.setattr(
        sincronizador,
        "insertar_filas",
        lambda tabla, filas: llamadas.append((tabla, filas)),
    )

    resultado = sincronizador.sincronizar_una_vez(carpeta=tmp_path)

    assert resultado == {"enviadas": 1, "exito": True, "error": None}
    assert [tabla for tabla, _ in llamadas] == [
        sincronizador.TABLA_VENTA,
        sincronizador.TABLA_MOVIMIENTO_INVENTARIO,
    ]
    movimientos = llamadas[1][1]
    assert len(movimientos) == 1
    assert movimientos[0]["producto_id"] == "lapiz-1"
    assert movimientos[0]["cantidad"] == -3.0
    assert movimientos[0]["referencia_id"] == venta["id"]
    assert journal.leer_pendientes(hoy.date(), carpeta=tmp_path) == []


def test_sincronizar_venta_solo_categoria_no_sube_movimientos(tmp_path, monkeypatch):
    hoy = datetime.datetime.now(datetime.timezone.utc)
    journal.escribir_venta(_venta(fecha_hora=hoy), carpeta=tmp_path)

    llamadas = []
    monkeypatch.setattr(
        sincronizador,
        "insertar_filas",
        lambda tabla, filas: llamadas.append((tabla, filas)),
    )

    sincronizador.sincronizar_una_vez(carpeta=tmp_path)

    assert [tabla for tabla, _ in llamadas] == [sincronizador.TABLA_VENTA]


def test_si_fallan_los_movimientos_no_se_marca_confirmada_la_venta(tmp_path, monkeypatch):
    """
    Si la venta ya se subio pero los movimientos truenan, la venta debe
    seguir 'pendiente' -- el siguiente ciclo reintenta ambos y, gracias a
    los ids deterministas, no descuenta el stock dos veces.
    """
    hoy = datetime.datetime.now(datetime.timezone.utc)
    journal.escribir_venta(
        _venta(fecha_hora=hoy, detallada=True, lineas=[_linea_producto("lapiz-1", cantidad=3)]),
        carpeta=tmp_path,
    )

    def falla_solo_movimientos(tabla, filas):
        if tabla == sincronizador.TABLA_MOVIMIENTO_INVENTARIO:
            raise ConnectionError("sin internet")

    monkeypatch.setattr(sincronizador, "insertar_filas", falla_solo_movimientos)

    resultado = sincronizador.sincronizar_una_vez(carpeta=tmp_path)

    assert resultado["exito"] is False
    assert len(journal.leer_pendientes(hoy.date(), carpeta=tmp_path)) == 1


def test_un_dia_que_falla_corta_el_ciclo_sin_tocar_los_demas(tmp_path, monkeypatch):
    """
    Si el dia mas reciente falla (tipicamente: sin internet), no tiene
    caso seguir intentando los 29 dias restantes en el mismo ciclo.
    """
    hoy = datetime.date.today()
    ayer = hoy - datetime.timedelta(days=1)
    journal.escribir_venta(
        _venta(fecha_hora=datetime.datetime.combine(hoy, datetime.time(9, 0), tzinfo=datetime.timezone.utc)),
        carpeta=tmp_path,
    )
    journal.escribir_venta(
        _venta(fecha_hora=datetime.datetime.combine(ayer, datetime.time(9, 0), tzinfo=datetime.timezone.utc)),
        carpeta=tmp_path,
    )

    llamadas = []

    def falla_siempre(tabla, filas):
        llamadas.append(filas)
        raise ConnectionError("sin internet")

    monkeypatch.setattr(sincronizador, "insertar_filas", falla_siempre)

    resultado = sincronizador.sincronizar_una_vez(carpeta=tmp_path)

    assert resultado["exito"] is False
    assert len(llamadas) == 1  # se corto tras el primer fallo, no intento el segundo dia


# --------------------------------------------------------------- Sincronizador

def test_ejecutar_ciclo_actualiza_estado_en_exito(tmp_path, monkeypatch):
    monkeypatch.setattr(sincronizador, "insertar_filas", lambda *a, **k: None)

    sinc = sincronizador.Sincronizador(carpeta=tmp_path, carpeta_cierre=tmp_path)
    assert sinc.estado()["ultima_sincronizacion_exitosa"] is None

    sinc.ejecutar_ciclo()

    estado = sinc.estado()
    assert estado["ultima_sincronizacion_exitosa"] is not None
    assert estado["fallos_consecutivos"] == 0
    assert estado["ultimo_error"] is None


def test_ejecutar_ciclo_cuenta_fallos_consecutivos(tmp_path, monkeypatch):
    hoy = datetime.datetime.now(datetime.timezone.utc)
    journal.escribir_venta(_venta(fecha_hora=hoy), carpeta=tmp_path)

    def falla(*a, **k):
        raise ConnectionError("sin internet")

    monkeypatch.setattr(sincronizador, "insertar_filas", falla)

    sinc = sincronizador.Sincronizador(carpeta=tmp_path, carpeta_cierre=tmp_path)
    sinc.ejecutar_ciclo()
    sinc.ejecutar_ciclo()

    estado = sinc.estado()
    assert estado["fallos_consecutivos"] == 2
    assert "sin internet" in estado["ultimo_error"]
    assert estado["ultima_sincronizacion_exitosa"] is None


def test_ejecutar_ciclo_nunca_lanza_aunque_algo_truene_inesperado(tmp_path, monkeypatch):
    def truena(*a, **k):
        raise RuntimeError("algo no previsto")

    monkeypatch.setattr(sincronizador, "sincronizar_una_vez", truena)

    sinc = sincronizador.Sincronizador(carpeta=tmp_path, carpeta_cierre=tmp_path)
    resultado = sinc.ejecutar_ciclo()  # no debe lanzar

    assert resultado["exito"] is False
    assert sinc.estado()["fallos_consecutivos"] == 1


def test_estado_persiste_entre_instancias_como_tras_un_reinicio(tmp_path, monkeypatch):
    monkeypatch.setattr(sincronizador, "insertar_filas", lambda *a, **k: None)

    primero = sincronizador.Sincronizador(carpeta=tmp_path, carpeta_cierre=tmp_path)
    primero.ejecutar_ciclo()
    marca = primero.estado()["ultima_sincronizacion_exitosa"]
    assert marca is not None

    # Simula un reinicio del proceso: instancia nueva, mismo carpeta.
    segundo = sincronizador.Sincronizador(carpeta=tmp_path, carpeta_cierre=tmp_path)
    assert segundo.estado()["ultima_sincronizacion_exitosa"] == marca


def test_iniciar_y_detener_el_hilo_de_verdad(tmp_path, monkeypatch):
    """
    Unico test que usa un hilo real -- confirma que el ciclo completo
    (arrancar, sincronizar, detener) funciona de punta a punta.
    """
    hoy = datetime.datetime.now(datetime.timezone.utc)
    v1 = journal.escribir_venta(_venta(fecha_hora=hoy), carpeta=tmp_path)

    monkeypatch.setattr(sincronizador, "insertar_filas", lambda *a, **k: None)

    sinc = sincronizador.Sincronizador(carpeta=tmp_path, carpeta_cierre=tmp_path, intervalo_base=0.05, intervalo_maximo=0.1)
    sinc.iniciar()
    try:
        for _ in range(100):
            if journal.leer_pendientes(hoy.date(), carpeta=tmp_path) == []:
                break
            time.sleep(0.02)
    finally:
        sinc.detener(timeout=2)

    assert journal.leer_pendientes(hoy.date(), carpeta=tmp_path) == []


def test_estado_persistido_ilegible_no_revienta_al_construir(tmp_path):
    archivo = sincronizador._archivo_estado(tmp_path)
    archivo.write_text("esto no es json valido {{{", encoding="utf-8")

    sinc = sincronizador.Sincronizador(carpeta=tmp_path, carpeta_cierre=tmp_path)
    assert sinc.estado()["ultima_sincronizacion_exitosa"] is None


def test_construir_no_toca_disco(tmp_path):
    """
    Construir un Sincronizador no debe leer ni crear nada -- main.py
    construye uno dentro de crear_app(), que se ejecuta en cuanto
    pytest IMPORTA un archivo de test (antes de cualquier fixture). Si
    __init__ tocara disco aqui, tocaria la carpeta REAL en ese momento.
    """
    carpeta_vigilada = tmp_path / "no_debe_crearse"
    sincronizador.Sincronizador(carpeta=carpeta_vigilada, carpeta_cierre=carpeta_vigilada)
    assert not carpeta_vigilada.exists()


def test_estado_solo_lee_el_archivo_persistido_una_vez(tmp_path, monkeypatch):
    llamadas = []
    original = sincronizador._leer_estado_persistido

    def espia(carpeta):
        llamadas.append(carpeta)
        return original(carpeta)

    monkeypatch.setattr(sincronizador, "_leer_estado_persistido", espia)

    sinc = sincronizador.Sincronizador(carpeta=tmp_path, carpeta_cierre=tmp_path)
    sinc.estado()
    sinc.estado()
    sinc.estado()

    assert len(llamadas) == 1


# ------------------------------------------ sincronizar_cierres_una_vez (#50/#54)

from almacen_local import cierres as cierres_locales  # noqa: E402


def test_sincronizar_cierres_sube_un_acta_nueva(tmp_path, monkeypatch):
    ayer = datetime.date.today() - datetime.timedelta(days=1)
    cierres_locales.generar_cierre_dia(ayer, "perezoso", carpeta_journal=tmp_path, carpeta_cierre=tmp_path)

    subidos = []
    monkeypatch.setattr(cierres_repo, "obtener_vigente", lambda *a, **k: None)
    monkeypatch.setattr(cierres_repo, "insertar", lambda acta: subidos.append(acta))

    resultado = sincronizador.sincronizar_cierres_una_vez(carpeta_cierre=tmp_path)

    assert resultado["enviados"] == 1
    assert len(subidos) == 1
    assert cierres_locales.obtener_cierre_local(ayer, tmp_path)["sincronizado"] is True


def test_sincronizar_cierres_regenerado_marca_corregido_el_anterior(tmp_path, monkeypatch):
    ayer = datetime.date.today() - datetime.timedelta(days=1)
    hora = datetime.datetime.combine(ayer, datetime.time(10, 0), tzinfo=datetime.timezone.utc)
    journal.escribir_venta(_venta(fecha_hora=hora), carpeta=tmp_path)

    primera = cierres_locales.generar_cierre_dia(
        ayer, "automatico", carpeta_journal=tmp_path, carpeta_cierre=tmp_path
    )
    cierres_locales.marcar_sincronizado(ayer, tmp_path)

    # Entra otra venta y se regenera el acta.
    journal.escribir_venta(_venta(fecha_hora=hora, total=50), carpeta=tmp_path)
    segunda = cierres_locales.regenerar_cierre_dia(
        ayer, "regeneracion", carpeta_journal=tmp_path, carpeta_cierre=tmp_path
    )

    corregidos, subidos = [], []
    monkeypatch.setattr(cierres_repo, "obtener_vigente", lambda *a, **k: {"id": primera["id"]})
    monkeypatch.setattr(cierres_repo, "marcar_corregido", lambda id_: corregidos.append(id_))
    monkeypatch.setattr(cierres_repo, "insertar", lambda acta: subidos.append(acta))

    resultado = sincronizador.sincronizar_cierres_una_vez(carpeta_cierre=tmp_path)

    assert resultado["enviados"] == 1
    assert corregidos == [primera["id"]]
    assert len(subidos) == 1 and subidos[0]["id"] == segunda["id"]
    assert cierres_locales.obtener_cierre_local(ayer, tmp_path)["sincronizado"] is True


def test_sincronizar_cierres_no_reinserta_si_el_id_ya_es_el_vigente(tmp_path, monkeypatch):
    ayer = datetime.date.today() - datetime.timedelta(days=1)
    acta = cierres_locales.generar_cierre_dia(
        ayer, "perezoso", carpeta_journal=tmp_path, carpeta_cierre=tmp_path
    )

    monkeypatch.setattr(cierres_repo, "obtener_vigente", lambda *a, **k: {"id": acta["id"]})

    def no_debe_insertar(_):
        raise AssertionError("no debio reinsertar: el id vigente ya coincide")

    monkeypatch.setattr(cierres_repo, "insertar", no_debe_insertar)

    resultado = sincronizador.sincronizar_cierres_una_vez(carpeta_cierre=tmp_path)

    assert resultado["enviados"] == 1
    assert cierres_locales.obtener_cierre_local(ayer, tmp_path)["sincronizado"] is True
