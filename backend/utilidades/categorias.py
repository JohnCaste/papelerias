"""
Lista canonica de categorias de venta -- UNA sola fuente de verdad.

Antes vivia duplicada en tres sitios que se desincronizaron:
`ventas/capturas.py` validaba 8 claves, la captura manual del resumen
diario (`acceso_datos/repositorios/resumen_diario.py`) solo conocia 5, y
el frontend tenia su propia copia. Agregar una categoria obligaba a
tocar todo eso a mano.

Reglas:
  - `CLAVE` es lo que se guarda en `venta.lineas[].categoria` (minusculas,
    sin acentos): NUNCA se renombra, la historia en BigQuery ya la usa.
  - `ETIQUETA` es solo presentacion; se puede cambiar cuando se quiera
    (el frontend tiene su propia copia de las etiquetas, ver
    frontend/src/categorias.ts -- misma lista, mismo orden).
  - El orden de esta lista es el orden en que se muestran (y las teclas
    rapidas 1..N del punto de venta).

Espejo en el frontend: frontend/src/categorias.ts
"""

# (clave, etiqueta)
CATEGORIAS: tuple[tuple[str, str], ...] = (
    ("papeleria", "Papeleria"),
    ("copias", "Copias y hojas"),
    ("dulces", "Dulces y Bebidas"),
    ("helados", "Helados"),
    ("recargas", "Recargas"),
    ("sublimacion", "Sublimacion"),
    ("limpieza", "Limpieza"),
    ("terramar", "Terramar"),
    ("otros", "Otros"),
)

CLAVES: tuple[str, ...] = tuple(clave for clave, _ in CATEGORIAS)
ETIQUETAS: dict[str, str] = dict(CATEGORIAS)
CLAVES_VALIDAS: frozenset[str] = frozenset(CLAVES)

# Claves legadas -> canonica. La migracion #10 escribio historia con
# 'productos'; 'hojas' se pliega con copias por decision de negocio.
PLIEGUE_LEGADO: dict[str, str] = {"productos": "papeleria", "hojas": "copias"}


def canonica(clave: str) -> str:
    return PLIEGUE_LEGADO.get(clave, clave)
