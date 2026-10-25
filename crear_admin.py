import os
import getpass

import mysql.connector
from mysql.connector import Error
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash

load_dotenv()


def obtener_conexion():
    """Conecta con la base de datos configurada en .env."""
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "consultorio_dental"),
    )


def crear_administrador():
    print("\n====================================")
    print(" REGISTRO DEL PRIMER ADMINISTRADOR")
    print("       SONRISA DENTAL")
    print("====================================\n")

    nombre = input("Nombre completo: ").strip()
    correo = input("Correo electrónico: ").strip().lower()

    if not nombre:
        print("Error: el nombre es obligatorio.")
        return

    if not correo or "@" not in correo:
        print("Error: ingresa un correo electrónico válido.")
        return

    contrasena = getpass.getpass("Crea una contraseña: ")
    confirmar = getpass.getpass("Confirma la contraseña: ")

    if len(contrasena) < 10:
        print("Error: la contraseña debe tener al menos 10 caracteres.")
        return

    if contrasena != confirmar:
        print("Error: las contraseñas no coinciden.")
        return

    conexion = None
    cursor = None

    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor(dictionary=True)

        # Evita crear otro administrador si ya existe uno.
        cursor.execute(
            "SELECT id_usuario FROM usuarios WHERE rol = 'ADMIN' LIMIT 1"
        )

        if cursor.fetchone():
            print(
                "\nYa existe un administrador. "
                "No se creó ningún usuario."
            )
            return

        # Comprueba si el correo ya está registrado.
        cursor.execute(
            "SELECT id_usuario FROM usuarios WHERE correo = %s LIMIT 1",
            (correo,),
        )

        if cursor.fetchone():
            print(
                "\nEse correo ya está registrado. "
                "Utiliza otro correo."
            )
            return

        password_hash = generate_password_hash(contrasena)

        cursor.execute(
            """
            INSERT INTO usuarios
                (nombre, correo, password_hash, rol, activo)
            VALUES
                (%s, %s, %s, 'ADMIN', TRUE)
            """,
            (nombre, correo, password_hash),
        )

        conexion.commit()

        print("\n¡Administrador registrado correctamente!")
        print("Ya puedes utilizar el formulario de inicio de sesión.")
        print("Correo registrado:", correo)
        print("Por seguridad, la contraseña no se muestra.")

    except Error:
        if conexion is not None and conexion.is_connected():
            conexion.rollback()

        print("\nNo fue posible registrar al administrador.")
        print(
            "Verifica la conexión, el archivo .env "
            "y la estructura de la tabla usuarios."
        )

    finally:
        if cursor is not None:
            cursor.close()

        if conexion is not None and conexion.is_connected():
            conexion.close()


if __name__ == "__main__":
    crear_administrador()
