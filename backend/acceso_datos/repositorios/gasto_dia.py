"""
Repositorio de gasto_dia: el monto de "Gastos" que se captura en el
modal por dia de la pantalla de Ventas (columna al costado de los
totales por categoria). Descuenta de 'papeleria' al calcular el total
con descuento; nunca toca ninguna otra categoria.

Append-only, igual que `cierre`: cada guardado agrega una fila nueva con
el monto vigente del dia (no se hace UPDATE). `obtener` lee la ULTIMA
fila por fecha, asi que reabrir el modal y guardar de nuevo simplemente
reemplaza el valor mostrado, sin acumular historial visible.

Deliberadamente FUERA de `venta` (a diferencia de las categorias del
resumen diario, ver acceso_datos/repositorios/resumen_diario.py): un
gasto es un egreso, no una venta, y mezclarlo en `venta` corromperia
`total`/`num_ventas` en los reportes agregados (#34) y en el dashboard
del dia (#35).
"""

import datetime
import uuid

from acceso_datos.consultas import ejecutar_uno
from acceso_datos.escrituras import insertar_filas
from esquema.tablas import DATASET

TABLA = f"{DATASET}.gasto_dia"


def obtener(fecha: datetime.date) -> float:
    """El monto de gasto vigente del dia, o 0.0 si nunca se capturo."""
    sql = f"""
        SELECT monto FROM `{TABLA}`
        WHERE fecha = @fecha
        ORDER BY generado_en DESC
        LIMIT 1
    """
    fila = ejecutar_uno(sql, {"fecha": fecha}, {"fecha": "DATE"})
    return float(fila["monto"]) if fila else 0.0


def guardar(fecha: datetime.date, monto: float, usuario_id: str) -> dict:
    """Agrega una fila nueva con el monto vigente. Devuelve {fecha, monto}."""
    fila = {
        "id": str(uuid.uuid4()),
        "fecha": fecha,
        "monto": round(float(monto), 2),
        "usuario_id": usuario_id,
        "generado_en": datetime.datetime.now(datetime.timezone.utc),
    }
    insertar_filas(TABLA, [fila])
    return {"fecha": fecha.isoformat(), "monto": fila["monto"]}
