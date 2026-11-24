"""
Crea el dataset y las tablas definidas en tablas.py, si no existen.

Idempotente: se puede correr las veces que haga falta, nunca duplica ni
borra nada (usa exists_ok=True en dataset y tablas).

Estado: ya se corrio contra `mi-proyecto-gcp` el 2026-09-01 -- el
dataset `lapape` y sus seis tablas existen. #1 (revocar la llave vieja) y
#2 (purgar el historial de git) estan resueltos; las credenciales se leen
de variables de entorno (ver autentificacion/serviciosCloud.py y
backend/.env.example). Volver a correrlo es seguro (no cambia nada si ya
existe).

Uso:
    cd backend
    python -m esquema.crear_dataset
"""

from google.cloud import bigquery

import autentificacion.serviciosCloud as serviciosCloud
from esquema.tablas import DATASET, TABLAS
from utilidades import sucursal


def crear_dataset():
    client = bigquery.Client(
        credentials=serviciosCloud.get_credentials(),
        project=serviciosCloud.get_project_id(),
    )

    dataset_id = f"{client.project}.{DATASET}"
    # Sin confirmacion (es idempotente y lo corren los instaladores), pero
    # siempre a la vista a que sucursal se le crean las tablas.
    print(f"Sucursal: {sucursal.nombre_sucursal(DATASET)}  |  destino: {dataset_id}")
    dataset = bigquery.Dataset(dataset_id)
    dataset.location = "US"
    client.create_dataset(dataset, exists_ok=True)
    print(f"Dataset listo: {dataset_id}")

    for definicion in TABLAS:
        tabla = bigquery.Table(
            f"{dataset_id}.{definicion.nombre}", schema=definicion.schema
        )
        if definicion.particion_por:
            tabla.time_partitioning = bigquery.TimePartitioning(
                type_=bigquery.TimePartitioningType.DAY,
                field=definicion.particion_por,
            )
        if definicion.cluster_por:
            tabla.clustering_fields = definicion.cluster_por

        creada = client.create_table(tabla, exists_ok=True)
        print(f"  tabla lista: {creada.table_id}")


if __name__ == "__main__":
    crear_dataset()
