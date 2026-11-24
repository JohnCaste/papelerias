r"""
Alta de un usuario del punto de venta en la tabla legada
`nuevas_tablas.login` (la misma que consulta el login, ver
autentificacion/credenciales.py).

No existe todavia un endpoint de alta de usuarios -- la pestana
Configuracion solo lista, cambia el rol y sube la foto. Mientras eso no
exista, este script es la forma soportada de dar de alta a alguien.

La contrasena se guarda SIEMPRE hasheada con bcrypt: nunca en texto
plano, aunque el legado tenga filas asi (credenciales.py las re-hashea
sola en el primer login correcto).

Uso (desde backend/):
    .\venv\Scripts\python.exe -m esquema.crear_usuario --nombre <nombre> --password <contrasena>
    .\venv\Scripts\python.exe -m esquema.crear_usuario --nombre <nombre> --password <contrasena> --rol dueno
    .\venv\Scripts\python.exe -m esquema.crear_usuario --nombre <nombre> --password <contrasena> --dry-run

Si el nombre ya existe NO se duplica: se avisa y no se escribe nada
(--reemplazar-password cambia la contrasena del que ya esta).

Nota BigQuery: la fila se inserta por DML (INSERT), no por streaming,
para que el login la vea de inmediato.
"""

import argparse
import uuid

import bcrypt

import acceso_datos.repositorios.usuario_roles as roles_repo
from acceso_datos.consultas import ejecutar_query, ejecutar_uno
from autentificacion.credenciales import PAPELERIA, TABLA_LOGIN_LEGADO
from utilidades import sucursal

# La columna `papeleria` de la tabla legada es REQUIRED y separa a los
# usuarios de cada sucursal: "1" en la tienda original, el nombre del
# dataset en las demas (ver utilidades/sucursal.py::papeleria_login).
PAPELERIA_POR_DEFECTO = PAPELERIA


def _hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def buscar_por_nombre(nombre: str, papeleria: str = PAPELERIA_POR_DEFECTO):
    # Por papeleria: el mismo nombre puede existir en otra sucursal.
    return ejecutar_uno(
        f"SELECT id, nombre FROM `{TABLA_LOGIN_LEGADO}` "
        "WHERE nombre = @nombre AND papeleria = @papeleria LIMIT 1",
        {"nombre": nombre, "papeleria": papeleria},
    )


def crear(
    nombre: str,
    password: str,
    rol: str = roles_repo.ROL_EMPLEADO,
    telefono: str | None = None,
    papeleria: str = PAPELERIA_POR_DEFECTO,
    reemplazar_password: bool = False,
    dry_run: bool = False,
) -> dict:
    existente = buscar_por_nombre(nombre, papeleria)

    if existente and not reemplazar_password:
        return {"accion": "sin_cambios", "id": existente["id"], "nombre": nombre}

    if existente:
        if not dry_run:
            ejecutar_query(
                f"UPDATE `{TABLA_LOGIN_LEGADO}` SET password = @password WHERE id = @id",
                {"password": _hash(password), "id": existente["id"]},
            )
            roles_repo.guardar(existente["id"], rol)
        return {"accion": "password_reemplazada", "id": existente["id"], "nombre": nombre}

    usuario_id = str(uuid.uuid4())
    if not dry_run:
        ejecutar_query(
            f"INSERT INTO `{TABLA_LOGIN_LEGADO}` "
            "(id, nombre, password, telefono, papeleria) "
            "VALUES (@id, @nombre, @password, @telefono, @papeleria)",
            {
                "id": usuario_id,
                "nombre": nombre,
                "password": _hash(password),
                "telefono": telefono,
                "papeleria": papeleria,
            },
            # `telefono` es opcional: si va vacio llega como None y el tipo
            # no se puede inferir solo, hay que declararlo.
            {"telefono": "STRING"},
        )
        roles_repo.guardar(usuario_id, rol)
    return {"accion": "creado", "id": usuario_id, "nombre": nombre}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nombre", required=True, help="Nombre con el que inicia sesion")
    parser.add_argument("--password", required=True)
    parser.add_argument(
        "--rol",
        default=roles_repo.ROL_EMPLEADO,
        choices=sorted(roles_repo.ROLES_VALIDOS),
        help="empleado (por defecto) o dueno",
    )
    parser.add_argument("--telefono", default=None)
    parser.add_argument("--papeleria", default=PAPELERIA_POR_DEFECTO)
    parser.add_argument(
        "--reemplazar-password",
        action="store_true",
        help="Si el nombre ya existe, le cambia la contrasena en vez de no hacer nada",
    )
    parser.add_argument("--dry-run", action="store_true", help="Solo reporta, no escribe")
    parser.add_argument("--si", action="store_true", help="No pedir confirmacion (instaladores)")
    args = parser.parse_args()

    if not args.dry_run and not sucursal.confirmar_destino(
        f"crear/actualizar el usuario {args.nombre!r} (papeleria {args.papeleria})", si=args.si
    ):
        print("Cancelado. No se escribio nada.")
        raise SystemExit(1)

    resultado = crear(
        nombre=args.nombre,
        password=args.password,
        rol=args.rol,
        telefono=args.telefono,
        papeleria=args.papeleria,
        reemplazar_password=args.reemplazar_password,
        dry_run=args.dry_run,
    )

    prefijo = "[dry-run] " if args.dry_run else ""
    if resultado["accion"] == "sin_cambios":
        print(
            f"{prefijo}Ya existe un usuario llamado {args.nombre!r} (id {resultado['id']}). "
            "No se toco nada. Usa --reemplazar-password si querias cambiarle la contrasena."
        )
    elif resultado["accion"] == "password_reemplazada":
        print(f"{prefijo}Contrasena de {args.nombre!r} reemplazada (id {resultado['id']}, rol {args.rol}).")
    else:
        print(f"{prefijo}Usuario {args.nombre!r} creado (id {resultado['id']}, rol {args.rol}).")


if __name__ == "__main__":
    main()
