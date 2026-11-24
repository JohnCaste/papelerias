"""
Agrega la columna `vendedor` (STRING, NULLABLE) a la tabla `lapape.venta`.

`crear_dataset.py` usa `create_table(exists_ok=True)`, que NO altera una
tabla que ya existe -- por eso esta migracion aparte para el campo nuevo
que pide el reporte "quien vendio".

Idempotente: si la columna ya esta, no hace nada. Agregar una columna
NULLABLE en BigQuery es una operacion de solo metadatos (no reescribe
datos) y las filas existentes quedan con `vendedor = NULL`.

Uso:
    cd backend
    python -m esquema.migrar_vendedor
"""

from google.cloud import bigquery

import autentificacion.serviciosCloud as serviciosCloud
from esquema.tablas import DATASET
from utilidades import sucursal

COLUMNA = bigquery.SchemaField("vendedor", "STRING", mode="NULLABLE")


def migrar_vendedor():
    client = bigquery.Client(
        credentials=serviciosCloud.get_credentials(),
        project=serviciosCloud.get_project_id(),
    )

    tabla_id = f"{client.project}.{DATASET}.venta"
    print(f"Sucursal: {sucursal.nombre_sucursal(DATASET)}  |  destino: {tabla_id}")
    tabla = client.get_table(tabla_id)

    if any(campo.name == COLUMNA.name for campo in tabla.schema):
        print(f"La columna '{COLUMNA.name}' ya existe en {tabla_id}; nada que hacer.")
        return

    tabla.schema = list(tabla.schema) + [COLUMNA]
    client.update_table(tabla, ["schema"])
    print(f"Columna '{COLUMNA.name}' agregada a {tabla_id}.")


if __name__ == "__main__":
    migrar_vendedor()
