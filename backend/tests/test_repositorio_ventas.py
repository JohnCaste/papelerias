"""
Tests del repositorio de venta -- en particular la logica de cancelacion,
que es la parte mas delicada (debe revertir sin tocar la fila original).
"""

import acceso_datos.repositorios.ventas as ventas


def test_insertar_normaliza_lineas_y_genera_id(monkeypatch):
    capturado = {}

    def falsa_insertar_filas(tabla, filas):
        capturado["filas"] = filas

    monkeypatch.setattr(ventas, "insertar_filas", falsa_insertar_filas)

    fila = ventas.insertar(
        {
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
    )

    assert fila["id"]
    assert fila["estado"] == "activa"
    assert fila["origen"] == "pos"
    assert fila["lineas"][0]["categoria"] == "pilas"
    assert capturado["filas"] == [fila]


def test_insertar_respeta_id_provisto_para_idempotencia(monkeypatch):
    monkeypatch.setattr(ventas, "insertar_filas", lambda tabla, filas: None)
    fila = ventas.insertar(
        {"id": "id-fijo", "total": 1, "metodo_pago": "efectivo", "usuario_id": "u1"}
    )
    assert fila["id"] == "id-fijo"


def test_cancelar_no_existe_lanza_error(monkeypatch):
    monkeypatch.setattr(ventas, "obtener_por_id", lambda id_: None)
    try:
        ventas.cancelar("no-existe", "u1", "motivo")
        assert False, "debia lanzar ValueError"
    except ValueError:
        pass


def test_cancelar_no_permite_cancelar_una_reversion(monkeypatch):
    monkeypatch.setattr(
        ventas,
        "obtener_por_id",
        lambda id_: {"venta_original_id": "otra-venta"},
    )
    try:
        ventas.cancelar("id-reversion", "u1", "motivo")
        assert False, "debia lanzar ValueError"
    except ValueError:
        pass


def test_cancelar_invierte_signos_de_lineas_y_total(monkeypatch):
    original = {
        "id": "venta-1",
        "total": 100.0,
        "metodo_pago": "efectivo",
        "detallada": False,
        "venta_original_id": None,
        "lineas": [
            {
                "tipo": "categoria",
                "categoria": "dulces",
                "cantidad": 1.0,
                "precio_unitario": 60.0,
                "subtotal": 60.0,
                "monto_comision": None,
            },
            {
                "tipo": "recarga",
                "categoria": None,
                "cantidad": 1.0,
                "precio_unitario": 40.0,
                "subtotal": 40.0,
                "monto_comision": 4.0,
            },
        ],
    }
    monkeypatch.setattr(ventas, "obtener_por_id", lambda id_: original)

    capturado = {}
    monkeypatch.setattr(ventas, "insertar_filas", lambda tabla, filas: capturado.update(filas=filas))

    reversion = ventas.cancelar("venta-1", "u2", "cliente se arrepintio")

    assert reversion["total"] == -100.0
    assert reversion["estado"] == "cancelada"
    assert reversion["venta_original_id"] == "venta-1"
    assert reversion["motivo_cancelacion"] == "cliente se arrepintio"
    assert reversion["cancelada_por"] == "u2"
    assert reversion["cancelada_en"] is not None
    # el motivo de cancelacion NO va en el campo de extemporaneas (#26)
    assert reversion["motivo_extemporanea"] is None

    l1, l2 = reversion["lineas"]
    assert l1["cantidad"] == -1.0
    assert l1["subtotal"] == -60.0
    assert l2["subtotal"] == -40.0
    assert l2["monto_comision"] == -4.0

    # el neto de original + reversion debe ser exactamente cero
    assert original["total"] + reversion["total"] == 0


def test_total_del_rango_no_filtra_por_estado(monkeypatch):
    """
    Nota de diseno del modulo: el total se calcula sumando TODAS las
    filas (incluidas las reversiones), sin WHERE estado = 'activa'.
    """
    capturado = {}

    def falso_ejecutar_uno(sql, valores=None, tipos=None):
        capturado["sql"] = sql
        return {"total": 0, "num_ventas": 0}

    monkeypatch.setattr(ventas, "ejecutar_uno", falso_ejecutar_uno)
    ventas.total_del_rango("2026-08-01", "2026-08-31")

    assert "estado" not in capturado["sql"]
    assert "venta_original_id IS NULL" in capturado["sql"]
