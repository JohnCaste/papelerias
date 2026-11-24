"""
Reglas de validacion de un producto -- UNA sola fuente de verdad para el
alta individual (catalogos/productos.py) y la importacion desde Excel/CSV
(catalogos/importacion.py). Ver openspec/changes/importacion-catalogo-excel,
design.md Decision 2.

Funciones puras: no consultan BigQuery. La unicidad del codigo de barras y
la lista de categorias se resuelven con datos precargados que pasa quien
llama, para que validar un lote de 2000 filas no haga 2000 consultas.

Los mensajes no llevan acentos, igual que los que ya devolvia el alta
individual (el frontend los muestra tal cual).
"""

import re
import unicodedata

CAMPOS_REQUERIDOS = ("nombre", "categoria", "precio")

MENSAJE_CODIGO_EN_USO = "El codigo de barras ya esta en uso"

# (campo, etiqueta, femenino) -- para "X no puede ser negativo/a".
CAMPOS_NUMERICOS = (
    ("precio", "El precio", False),
    ("costo", "El costo", False),
    ("cantidad", "La cantidad", True),
    ("stock_minimo", "El stock minimo", False),
)

_ARTICULO_FALTA = {"nombre": "el nombre", "categoria": "la categoria", "precio": "el precio"}

_MILES_CON_COMA = re.compile(r"^\d{1,3}(,\d{3})+(\.\d+)?$")
_DECIMAL_CON_COMA = re.compile(r"^\d+,\d{1,2}$")


def normalizar_clave(texto) -> str:
    """Minusculas, sin acentos (NFD sin marcas Mn) y espacios colapsados.
    Para comparar categorias, encabezados y nombres sin que importe como
    se escribieron."""
    if texto is None:
        return ""
    descompuesto = unicodedata.normalize("NFD", str(texto))
    sin_acentos = "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")
    return " ".join(sin_acentos.lower().split())


def texto_limpio(valor):
    """Recorta; vacio -> None. Un numero que trae Excel (12.0) se vuelve '12'."""
    if valor is None:
        return None
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    valor = str(valor).strip()
    return valor or None


def normalizar_codigo(valor):
    """
    Codigo de barras / codigo interno como texto. Excel suele entregar
    7501234567890 como float: se convierte a '7501234567890', sin
    decimales ni notacion cientifica. Vacio -> None (guardar '' romperia la
    unicidad: '' == '').
    """
    if isinstance(valor, bool):
        return str(valor)
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return texto_limpio(valor)


def normalizar_codigo_barras_estricto(valor):
    """Comportamiento historico del alta individual: solo acepta str."""
    if not isinstance(valor, str):
        return None
    return valor.strip() or None


def a_numero(valor, tolerante: bool = False):
    """
    Devuelve float, o lanza ValueError si no es un numero.

    `tolerante` (importacion): acepta '$1,234.50', '1 234', '12,5'. Una coma
    solo se toma como separador de miles si el patron es inequivoco
    (1,234 / 12,345,678); '12,5' se lee como decimal; cualquier otra
    combinacion es ambigua y se rechaza.
    """
    if isinstance(valor, bool):
        raise ValueError("booleano")
    if isinstance(valor, (int, float)):
        return float(valor)
    if not tolerante:
        return float(valor)

    texto = str(valor).strip().replace("$", "").replace(" ", "").replace(" ", "")
    if "," in texto:
        if _MILES_CON_COMA.match(texto):
            texto = texto.replace(",", "")
        elif _DECIMAL_CON_COMA.match(texto):
            texto = texto.replace(",", ".")
        else:
            raise ValueError("ambiguo")
    numero = float(texto)
    if numero != numero or numero in (float("inf"), float("-inf")):
        raise ValueError("no finito")
    return numero


def validar_no_negativo(valor, etiqueta: str, femenino: bool = False, tolerante: bool = False):
    """(numero | None, error | None). Vacio -> (None, None)."""
    if valor in (None, ""):
        return None, None
    try:
        numero = a_numero(valor, tolerante=tolerante)
    except (TypeError, ValueError):
        return None, f"{etiqueta} no es un numero valido"
    if numero < 0:
        return None, f"{etiqueta} no puede ser {'negativa' if femenino else 'negativo'}"
    return numero, None


def error_precio(valor):
    """Mensaje de error del precio (alta/edicion individual), o None."""
    return validar_no_negativo(valor, "El precio")[1]


def faltantes(datos: dict) -> list:
    """Campos requeridos ausentes. 'precio' = 0 es valido: se comprueba
    presencia, no verdad."""
    return [campo for campo in CAMPOS_REQUERIDOS if datos.get(campo) in (None, "")]


def mapa_categorias(nombres) -> dict:
    """{clave_normalizada: nombre_canonico} de la tabla `categoria`."""
    return {normalizar_clave(nombre): nombre for nombre in nombres}


def resolver_categoria(valor, mapa_canonico: dict):
    """(nombre_canonico | None, error | None)."""
    texto = texto_limpio(valor)
    if texto is None:
        return None, "Falta la categoria"
    canonico = mapa_canonico.get(normalizar_clave(texto))
    if canonico is None:
        return None, f'La categoria "{texto}" no existe'
    return canonico, None


def validar_fila(datos: dict, mapa_canonico: dict):
    """
    Valida y normaliza una fila cruda (como sale del archivo o del cuerpo
    de la confirmacion). Devuelve (producto_normalizado, errores). No
    revisa la unicidad del codigo de barras: eso necesita el lote completo
    (ver catalogos/importacion.py::validar_lote).
    """
    errores = []
    producto = {}

    nombre = texto_limpio(datos.get("nombre"))
    if nombre is None:
        errores.append("Falta el nombre")
    producto["nombre"] = nombre

    categoria, error = resolver_categoria(datos.get("categoria"), mapa_canonico)
    if error:
        errores.append(error)
    producto["categoria"] = categoria

    if datos.get("precio") in (None, "") or texto_limpio(datos.get("precio")) is None:
        errores.append("Falta el precio")
        producto["precio"] = None
    for campo, etiqueta, femenino in CAMPOS_NUMERICOS:
        valor = datos.get(campo)
        if isinstance(valor, str) and not valor.strip():
            valor = None
        numero, error = validar_no_negativo(valor, etiqueta, femenino, tolerante=True)
        if error:
            errores.append(error)
        if campo != "precio" or numero is not None:
            producto[campo] = numero

    producto["codigo_barras"] = normalizar_codigo(datos.get("codigo_barras"))
    producto["codigo_interno"] = normalizar_codigo(datos.get("codigo_interno"))
    producto["marca"] = texto_limpio(datos.get("marca"))
    producto["descripcion"] = texto_limpio(datos.get("descripcion"))
    return producto, errores
