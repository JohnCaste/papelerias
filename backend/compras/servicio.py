"""
Logica de compras de trabajadores sobre el journal local
(almacen_local/compras.py). Aqui viven los calculos y las validaciones;
las vistas solo traducen HTTP.

Valores CALCULADOS, nunca capturados (ver la spec compras-de-trabajadores):

    importe = precio x cantidad
    pagado  = suma de los abonos vigentes de la compra
    total   = importe - pagado          (lo que resta)
    estatus = pendiente | parcial | pagado

Dinero con Decimal redondeado a 2 decimales, y guardado en el journal como
texto ("45.00") para no arrastrar errores de float.
"""

import datetime
import uuid
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from almacen_local import compras as journal_compras
from utilidades import zona_negocio

CENTAVO = Decimal("0.01")
CERO = Decimal("0.00")
MAX_NOMBRE = 80
MAX_PRODUCTO = 200
MAX_CANTIDAD = 100000
MAX_MONTO = Decimal("1000000")

PENDIENTE = "pendiente"
PARCIAL = "parcial"
PAGADO = "pagado"


class ErrorCompras(Exception):
    """Error de negocio con el status HTTP que le corresponde."""

    def __init__(self, mensaje: str, status: int = 400, campo: str | None = None):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.status = status
        self.campo = campo


# ------------------------------------------------------------ utilidades

def _dinero(valor) -> Decimal:
    return Decimal(str(valor)).quantize(CENTAVO, rounding=ROUND_HALF_UP)


def _a_float(valor: Decimal) -> float:
    return float(valor)


def normalizar_nombre(texto: str) -> str:
    return " ".join(str(texto).split())


def _clave_nombre(texto: str) -> str:
    return normalizar_nombre(texto).casefold()


def _texto(datos: dict, campo: str, etiqueta: str, maximo: int) -> str:
    valor = datos.get(campo)
    if not isinstance(valor, str) or not normalizar_nombre(valor):
        raise ErrorCompras(f"{etiqueta} es obligatorio", campo=campo)
    valor = normalizar_nombre(valor)
    if len(valor) > maximo:
        raise ErrorCompras(f"{etiqueta} admite como maximo {maximo} caracteres", campo=campo)
    return valor


def _cantidad(datos: dict) -> int:
    valor = datos.get("cantidad")
    if isinstance(valor, bool):
        valor = None
    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, ValueError):
        numero = None
    if numero is None or not numero.is_finite() or numero != numero.to_integral_value():
        raise ErrorCompras("La cantidad debe ser un numero entero", campo="cantidad")
    numero = int(numero)
    if numero < 1 or numero > MAX_CANTIDAD:
        raise ErrorCompras("La cantidad debe ser al menos 1", campo="cantidad")
    return numero


def _monto(datos: dict, campo: str, etiqueta: str, obligatorio=True, minimo_exclusivo=False) -> Decimal:
    valor = datos.get(campo)
    if valor is None or valor == "":
        if obligatorio:
            raise ErrorCompras(f"{etiqueta} es obligatorio", campo=campo)
        return CERO
    if isinstance(valor, bool):
        raise ErrorCompras(f"{etiqueta} debe ser un numero", campo=campo)
    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, ValueError):
        raise ErrorCompras(f"{etiqueta} debe ser un numero", campo=campo) from None
    if not numero.is_finite():
        raise ErrorCompras(f"{etiqueta} debe ser un numero", campo=campo)
    numero = numero.quantize(CENTAVO, rounding=ROUND_HALF_UP)
    if numero < 0 or (minimo_exclusivo and numero == 0):
        condicion = "mayor que 0" if minimo_exclusivo else "0 o mas"
        raise ErrorCompras(f"{etiqueta} debe ser {condicion}", campo=campo)
    if numero > MAX_MONTO:
        raise ErrorCompras(f"{etiqueta} es demasiado grande", campo=campo)
    return numero


def _fecha(datos: dict, campo="fecha") -> datetime.date:
    hoy = zona_negocio.hoy()
    valor = datos.get(campo)
    if valor in (None, ""):
        return hoy
    try:
        fecha = datetime.date.fromisoformat(str(valor))
    except ValueError:
        raise ErrorCompras("La fecha no es valida (usa AAAA-MM-DD)", campo=campo) from None
    if fecha > hoy:
        raise ErrorCompras("La fecha no puede ser futura", campo=campo)
    if fecha.year < 2000:
        raise ErrorCompras("La fecha no es valida", campo=campo)
    return fecha


# ------------------------------------------------------------ lectura

def _estatus(importe: Decimal, pagado: Decimal) -> str:
    if pagado >= importe:
        return PAGADO
    if pagado > 0:
        return PARCIAL
    return PENDIENTE


def _armar(eventos: list) -> tuple[dict, list]:
    """compras vigentes por compra_id (con calculos) y sus abonos vigentes."""
    compras = {}
    for c in journal_compras.compras_vigentes(eventos=eventos):
        importe = _dinero(c["precio"]) * c["cantidad"]
        compras[c["compra_id"]] = {
            "compra_id": c["compra_id"],
            "nombre": c["nombre"],
            "producto": c["producto"],
            "cantidad": c["cantidad"],
            "precio": _dinero(c["precio"]),
            "fecha": c["fecha"],
            "registrado_por": c.get("registrado_por"),
            "generado_en": c["generado_en"],
            "importe": importe.quantize(CENTAVO),
            "pagado": CERO,
        }

    abonos = [
        a for a in journal_compras.abonos_vigentes(eventos=eventos)
        if a["compra_id"] in compras
    ]
    for a in abonos:
        compras[a["compra_id"]]["pagado"] += _dinero(a["monto"])

    for c in compras.values():
        c["total"] = c["importe"] - c["pagado"]
        c["estatus"] = _estatus(c["importe"], c["pagado"])
    return compras, abonos


def _nombres_sugeridos(compras: dict) -> list:
    """Un nombre por persona: la forma mas usada (empate: la primera vista)."""
    conteo = {}
    for c in compras.values():
        clave = _clave_nombre(c["nombre"])
        formas = conteo.setdefault(clave, {})
        formas[c["nombre"]] = formas.get(c["nombre"], 0) + 1
    nombres = [max(formas, key=formas.get) for formas in conteo.values()]
    return sorted(nombres, key=str.casefold)


def _compra_json(c: dict) -> dict:
    return {
        **c,
        "precio": _a_float(c["precio"]),
        "importe": _a_float(c["importe"]),
        "pagado": _a_float(c["pagado"]),
        "total": _a_float(c["total"]),
    }


def estado(carpeta=None) -> dict:
    """Todo lo que muestra la pantalla, leido del journal local."""
    eventos = journal_compras.leer_eventos(carpeta)
    compras, abonos = _armar(eventos)

    hoy = zona_negocio.hoy()
    mes_actual = hoy.isoformat()[:7]

    lista_compras = sorted(
        compras.values(), key=lambda c: (c["fecha"], c["generado_en"]), reverse=True
    )
    lista_abonos = sorted(
        abonos, key=lambda a: (a["fecha"], a["generado_en"]), reverse=True
    )

    resumen = {
        "por_cobrar": _a_float(sum((c["total"] for c in compras.values()), CERO)),
        "compras_abiertas": sum(1 for c in compras.values() if c["estatus"] != PAGADO),
        "abonado_mes": _a_float(
            sum((_dinero(a["monto"]) for a in abonos if a["fecha"][:7] == mes_actual), CERO)
        ),
    }

    return {
        "compras": [_compra_json(c) for c in lista_compras],
        "abonos": [
            {
                "abono_id": a["abono_id"],
                "compra_id": a["compra_id"],
                "monto": _a_float(_dinero(a["monto"])),
                "fecha": a["fecha"],
                "registrado_por": a.get("registrado_por"),
                "nombre": compras[a["compra_id"]]["nombre"],
                "producto": compras[a["compra_id"]]["producto"],
                "fecha_compra": compras[a["compra_id"]]["fecha"],
            }
            for a in lista_abonos
        ],
        "resumen": resumen,
        "nombres": _nombres_sugeridos(compras),
        "pendientes_subir": len(journal_compras.leer_pendientes(eventos=eventos)),
        "hoy": hoy.isoformat(),
    }


# ------------------------------------------------------------ escritura

def _campos_compra(datos: dict, compras: dict) -> dict:
    nombre = _texto(datos, "nombre", "El nombre", MAX_NOMBRE)
    # Si la persona ya existe con otra capitalizacion, se usa la forma ya
    # registrada: asi "ana" y "Ana" quedan agrupadas en filtros y totales.
    for forma in _nombres_sugeridos(compras):
        if _clave_nombre(forma) == _clave_nombre(nombre):
            nombre = forma
            break
    return {
        "nombre": nombre,
        "producto": _texto(datos, "producto", "El producto", MAX_PRODUCTO),
        "cantidad": _cantidad(datos),
        "precio": _monto(datos, "precio", "El precio"),
        "fecha": _fecha(datos),
    }


def _instantanea(campos: dict, compra_id: str, usuario_id: str, registrado_por, eliminada=False) -> dict:
    return {
        "compra_id": compra_id,
        "nombre": campos["nombre"],
        "producto": campos["producto"],
        "cantidad": campos["cantidad"],
        "precio": str(campos["precio"]),
        "fecha": campos["fecha"].isoformat() if isinstance(campos["fecha"], datetime.date) else campos["fecha"],
        "eliminada": eliminada,
        "usuario_id": usuario_id,
        "registrado_por": registrado_por,
    }


def _buscar(compras: dict, compra_id: str) -> dict:
    compra = compras.get(compra_id)
    if compra is None:
        raise ErrorCompras("La compra no existe o fue eliminada", status=404)
    return compra


def crear_compra(datos: dict, usuario_id: str, registrado_por=None, carpeta=None) -> dict:
    with journal_compras.lock:
        compras, _ = _armar(journal_compras.leer_eventos(carpeta))
        campos = _campos_compra(datos, compras)
        pago = _monto(datos, "pago", "El pago", obligatorio=False)
        importe = (campos["precio"] * campos["cantidad"]).quantize(CENTAVO)
        if pago > importe:
            raise ErrorCompras(
                f"El pago ({pago}) no puede ser mayor que el importe ({importe})", campo="pago"
            )

        compra_id = str(uuid.uuid4())
        journal_compras.escribir_compra(
            _instantanea(campos, compra_id, usuario_id, registrado_por), carpeta
        )
        if pago > 0:
            journal_compras.escribir_abono(
                {
                    "abono_id": str(uuid.uuid4()),
                    "compra_id": compra_id,
                    "monto": str(pago),
                    "fecha": campos["fecha"].isoformat(),
                    "usuario_id": usuario_id,
                    "registrado_por": registrado_por,
                },
                carpeta,
            )
        compras, _ = _armar(journal_compras.leer_eventos(carpeta))
        return _compra_json(compras[compra_id])


def editar_compra(compra_id: str, datos: dict, usuario_id: str, registrado_por=None, carpeta=None) -> dict:
    with journal_compras.lock:
        compras, _ = _armar(journal_compras.leer_eventos(carpeta))
        actual = _buscar(compras, compra_id)
        otras = {k: v for k, v in compras.items() if k != compra_id}
        campos = _campos_compra(datos, otras)
        importe = (campos["precio"] * campos["cantidad"]).quantize(CENTAVO)
        if importe < actual["pagado"]:
            raise ErrorCompras(
                f"El importe ({importe}) no puede quedar por debajo de lo ya pagado "
                f"({actual['pagado']}). Elimina antes el abono que sobra.",
                campo="precio",
            )
        journal_compras.escribir_compra(
            _instantanea(campos, compra_id, usuario_id, registrado_por), carpeta
        )
        compras, _ = _armar(journal_compras.leer_eventos(carpeta))
        return _compra_json(compras[compra_id])


def eliminar_compra(compra_id: str, usuario_id: str, registrado_por=None, carpeta=None) -> dict:
    with journal_compras.lock:
        compras, _ = _armar(journal_compras.leer_eventos(carpeta))
        actual = _buscar(compras, compra_id)
        journal_compras.escribir_compra(
            _instantanea(actual, compra_id, usuario_id, registrado_por, eliminada=True), carpeta
        )
        return {"compra_id": compra_id, "eliminada": True}


def abonar(compra_id: str, datos: dict, usuario_id: str, registrado_por=None, carpeta=None) -> dict:
    with journal_compras.lock:
        compras, _ = _armar(journal_compras.leer_eventos(carpeta))
        actual = _buscar(compras, compra_id)
        monto = _monto(datos, "monto", "El abono", minimo_exclusivo=True)
        fecha = _fecha(datos)
        if monto > actual["total"]:
            raise ErrorCompras(
                f"El abono no puede ser mayor que lo que resta ({actual['total']})",
                campo="monto",
            )
        abono = journal_compras.escribir_abono(
            {
                "abono_id": str(uuid.uuid4()),
                "compra_id": compra_id,
                "monto": str(monto),
                "fecha": fecha.isoformat(),
                "usuario_id": usuario_id,
                "registrado_por": registrado_por,
            },
            carpeta,
        )
        compras, _ = _armar(journal_compras.leer_eventos(carpeta))
        return {"abono_id": abono["abono_id"], "compra": _compra_json(compras[compra_id])}


def eliminar_abono(abono_id: str, usuario_id: str, registrado_por=None, carpeta=None) -> dict:
    with journal_compras.lock:
        _, abonos = _armar(journal_compras.leer_eventos(carpeta))
        abono = next((a for a in abonos if a["abono_id"] == abono_id), None)
        if abono is None:
            raise ErrorCompras("El abono no existe o fue eliminado", status=404)
        journal_compras.escribir_abono(
            {
                "abono_id": abono_id,
                "compra_id": abono["compra_id"],
                "monto": abono["monto"],
                "fecha": abono["fecha"],
                "eliminado": True,
                "usuario_id": usuario_id,
                "registrado_por": registrado_por,
            },
            carpeta,
        )
        return {"abono_id": abono_id, "eliminado": True}
