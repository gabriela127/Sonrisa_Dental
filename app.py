import os
import re
from datetime import date, datetime, timedelta
from decimal import Decimal

import mysql.connector
from mysql.connector import Error, IntegrityError
from dotenv import load_dotenv
from flask import Flask, render_template, jsonify, request, session, redirect, url_for
from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "clave-temporal-solo-desarrollo")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=2)

# Tablas que se muestran en el panel. No se crean ni modifican tablas.
MODULES = {
    "pacientes": "Pacientes",
    "citas": "Citas",
    "tratamientos": "Tratamientos",
    "facturas": "Facturas",
    "pagos": "Pagos",
    "detalle_factura": "Detalles de factura",
    "tratamientos_realizados": "Tratamientos realizados",
    "usuarios": "Usuarios",
}
HIDDEN_COLUMNS = {"password_hash"}
SYSTEM_COLUMNS = {"password_hash"}
IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_]+$")


def obtener_conexion():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "consultorio_dental"),
    )


def logged_in():
    return "usuario_id" in session


def require_login():
    if not logged_in():
        return jsonify({"mensaje": "Debes iniciar sesión."}), 401
    return None


def is_admin():
    return str(session.get("rol", "")).upper() == "ADMIN"


def table_allowed(table):
    return table in MODULES and IDENTIFIER_RE.fullmatch(table) is not None


def quote_identifier(value):
    if not IDENTIFIER_RE.fullmatch(value or ""):
        raise ValueError("Identificador no válido.")
    return "`" + value + "`"


def json_value(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat(sep=" ") if isinstance(value, datetime) else value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def json_row(row):
    return {key: json_value(value) for key, value in row.items() if key not in HIDDEN_COLUMNS}


def get_columns(cursor, table):
    cursor.execute(f"SHOW FULL COLUMNS FROM {quote_identifier(table)}")
    raw = cursor.fetchall()
    columns = []
    for col in raw:
        # Funciona tanto con cursores normales como con cursores dictionary=True.
        if isinstance(col, dict):
            field_name = col.get("Field")
            field_type = col.get("Type")
            nullable = col.get("Null")
            key = col.get("Key")
            default = col.get("Default")
            extra = col.get("Extra")
        else:
            field_name, field_type, _collation, nullable, key, default, extra = col[:7]
        columns.append({
            "name": field_name,
            "type": str(field_type or "").lower(),
            "nullable": nullable == "YES",
            "key": key or "",
            "default": json_value(default),
            "extra": str(extra or "").lower(),
            "primary": key == "PRI",
            "auto_increment": "auto_increment" in str(extra or "").lower(),
        })
    return columns


def get_primary_key(columns):
    return [c["name"] for c in columns if c["primary"]]


def get_foreign_keys(cursor, table):
    cursor.execute("""
        SELECT COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
        FROM information_schema.KEY_COLUMN_USAGE
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
          AND REFERENCED_TABLE_NAME IS NOT NULL
    """, (table,))
    result = {}
    for row in cursor.fetchall():
        if isinstance(row, dict):
            col_name = row.get("COLUMN_NAME")
            ref_table = row.get("REFERENCED_TABLE_NAME")
            ref_column = row.get("REFERENCED_COLUMN_NAME")
        else:
            col_name, ref_table, ref_column = row
        result[col_name] = {"table": ref_table, "column": ref_column}
    return result


def get_foreign_options(cursor, foreign_key):
    ref_table = foreign_key["table"]
    ref_column = foreign_key["column"]
    if not IDENTIFIER_RE.fullmatch(ref_table or "") or not IDENTIFIER_RE.fullmatch(ref_column or ""):
        return []
    cursor.execute(f"SHOW COLUMNS FROM {quote_identifier(ref_table)}")
    ref_cols = []
    for row in cursor.fetchall():
        ref_cols.append(row.get("Field") if isinstance(row, dict) else row[0])
    if ref_column not in ref_cols:
        return []
    label_candidates = [
        c for c in ref_cols
        if c != ref_column and c.lower() not in HIDDEN_COLUMNS
        and any(token in c.lower() for token in ("nombre", "name", "descripcion", "descripción", "correo", "codigo", "número", "numero"))
    ]
    label_col = label_candidates[0] if label_candidates else next(
        (c for c in ref_cols if c != ref_column and c.lower() not in HIDDEN_COLUMNS),
        ref_column
    )
    query = (
        f"SELECT {quote_identifier(ref_column)} AS fk_value, "
        f"{quote_identifier(label_col)} AS fk_label "
        f"FROM {quote_identifier(ref_table)} "
        f"ORDER BY {quote_identifier(label_col)} LIMIT 300"
    )
    cursor.execute(query)
    options = []
    for row in cursor.fetchall():
        if isinstance(row, dict):
            value, label = row.get("fk_value"), row.get("fk_label")
        else:
            value, label = row[0], row[1]
        options.append({"value": json_value(value), "label": str(label if label is not None else value)})
    return options


def describe_table(cursor, table):
    columns = get_columns(cursor, table)
    foreign_keys = get_foreign_keys(cursor, table)
    fields = []
    for col in columns:
        if col["name"] in HIDDEN_COLUMNS or col["auto_increment"] or col["primary"]:
            continue
        field = dict(col)
        if col["name"] in foreign_keys:
            fk = foreign_keys[col["name"]]
            field["foreign_key"] = fk
            field["options"] = get_foreign_options(cursor, fk)
        else:
            field["foreign_key"] = None
            field["options"] = []
        # Users enter a new password, never a raw hash.
        fields.append(field)
    if table == "usuarios":
        fields.append({
            "name": "contrasena", "type": "password", "nullable": False,
            "key": "", "default": None, "extra": "", "primary": False,
            "auto_increment": False, "foreign_key": None, "options": [],
            "password_field": True
        })
    return {
        "table": table,
        "label": MODULES[table],
        "columns": [c["name"] for c in columns if c["name"] not in HIDDEN_COLUMNS],
        "primary_key": get_primary_key(columns),
        "fields": fields,
        "has_active": any(c["name"].lower() == "activo" for c in columns),
    }


def list_rows(cursor, table, columns):
    visible = [c["name"] for c in columns if c["name"] not in HIDDEN_COLUMNS]
    if not visible:
        return []
    sql = f"SELECT {', '.join(quote_identifier(c) for c in visible)} FROM {quote_identifier(table)} LIMIT 500"
    cursor.execute(sql)
    return [json_row(row) for row in cursor.fetchall()]


def get_schema_and_rows(table):
    conexion = obtener_conexion()
    cursor = None
    try:
        cursor = conexion.cursor(dictionary=True)
        columns = get_columns(cursor, table)
        description = describe_table(cursor, table)
        rows = list_rows(cursor, table, columns)
        return description, rows
    finally:
        if cursor is not None:
            cursor.close()
        if conexion.is_connected():
            conexion.close()


def sanitize_data(cursor, table, data, inserting=False):
    if not isinstance(data, dict):
        raise ValueError("Envía los datos como un objeto JSON.")
    columns = get_columns(cursor, table)
    column_map = {c["name"]: c for c in columns}
    primary = set(get_primary_key(columns))
    output = {}
    for name, value in data.items():
        if name == "contrasena" and table == "usuarios":
            if value is None or str(value) == "":
                continue
            if len(str(value)) < 10:
                raise ValueError("La contraseña debe tener al menos 10 caracteres.")
            if "password_hash" in column_map:
                output["password_hash"] = generate_password_hash(str(value))
            continue
        if name not in column_map or name in HIDDEN_COLUMNS:
            continue
        col = column_map[name]
        if col["auto_increment"] or (col["primary"] and inserting):
            continue
        if not inserting and col["primary"]:
            continue
        if value == "" and col["nullable"]:
            value = None
        elif value == "" and col["default"] is not None:
            continue
        elif value == "" and not col["nullable"]:
            continue
        output[name] = value
    return output


def get_row_by_pk(cursor, table, pk_values):
    columns = get_columns(cursor, table)
    primary = get_primary_key(columns)
    if not primary:
        raise ValueError("La tabla no tiene una clave primaria; no se pueden editar sus filas de forma segura.")
    if len(primary) != 1:
        raise ValueError("La tabla usa una clave primaria compuesta y este panel no puede editarla automáticamente.")
    key = primary[0]
    if key not in pk_values:
        raise ValueError("No se recibió la clave primaria del registro.")
    return key, pk_values[key], columns


@app.route("/", methods=["GET"])
def inicio():
    if logged_in():
        return redirect(url_for("panel"))
    return render_template("index.html")


@app.route("/panel", methods=["GET"])
def panel():
    if not logged_in():
        return redirect(url_for("inicio"))
    return render_template("panel.html")


@app.route("/api/estado", methods=["GET"])
def estado():
    conexion = cursor = None
    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        cursor.execute("SELECT DATABASE()")
        base_datos = cursor.fetchone()[0]
        return jsonify({"aplicacion": "correcta", "mysql": "conectado", "base_datos": base_datos}), 200
    except (Error, ValueError):
        app.logger.exception("No se pudo conectar con MySQL")
        return jsonify({"aplicacion": "correcta", "mysql": "sin_conexion",
                        "mensaje": "Revisa la configuración DB_* del archivo .env y verifica que MySQL esté iniciado."}), 503
    finally:
        if cursor is not None:
            cursor.close()
        if conexion is not None and conexion.is_connected():
            conexion.close()


@app.route("/api/auth/login", methods=["POST"])
def iniciar_sesion():
    datos = request.get_json(silent=True)
    if not isinstance(datos, dict):
        return jsonify({"mensaje": "Debes enviar los datos en formato JSON."}), 400
    correo = datos.get("correo", "")
    contrasena = datos.get("contrasena", "")
    if not isinstance(correo, str) or not isinstance(contrasena, str):
        return jsonify({"mensaje": "El correo y la contraseña deben ser válidos."}), 400
    correo = correo.strip().lower()
    if not correo or not contrasena:
        return jsonify({"mensaje": "El correo y la contraseña son obligatorios."}), 400

    conexion = cursor = None
    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor(dictionary=True)
        cursor.execute("""
            SELECT id_usuario, nombre, correo, password_hash, rol, activo
            FROM usuarios WHERE correo = %s LIMIT 1
        """, (correo,))
        usuario = cursor.fetchone()
        if usuario is None:
            return jsonify({"mensaje": "Correo o contraseña incorrectos."}), 401
        if not usuario["activo"]:
            return jsonify({"mensaje": "La cuenta está desactivada."}), 403
        if not check_password_hash(usuario["password_hash"], contrasena):
            return jsonify({"mensaje": "Correo o contraseña incorrectos."}), 401
        session.clear()
        session.permanent = True
        session["usuario_id"] = usuario["id_usuario"]
        session["nombre"] = usuario["nombre"]
        session["correo"] = usuario["correo"]
        session["rol"] = usuario["rol"]
        return jsonify({
            "mensaje": "Inicio de sesión correcto.",
            "redireccion": url_for("panel"),
            "usuario": {"id": usuario["id_usuario"], "nombre": usuario["nombre"],
                        "correo": usuario["correo"], "rol": usuario["rol"]}
        }), 200
    except Error:
        app.logger.exception("Error al procesar el inicio de sesión")
        return jsonify({"mensaje": "No fue posible procesar el inicio de sesión."}), 500
    finally:
        if cursor is not None:
            cursor.close()
        if conexion is not None and conexion.is_connected():
            conexion.close()


@app.route("/api/auth/me", methods=["GET"])
def usuario_actual():
    if not logged_in():
        return jsonify({"mensaje": "Debes iniciar sesión."}), 401
    return jsonify({"id": session["usuario_id"], "nombre": session["nombre"],
                    "correo": session["correo"], "rol": session["rol"]}), 200


@app.route("/api/auth/logout", methods=["POST"])
def cerrar_sesion():
    session.clear()
    return jsonify({"mensaje": "Sesión cerrada correctamente.", "redireccion": url_for("inicio")}), 200


@app.route("/api/modulos", methods=["GET"])
def listar_modulos():
    error = require_login()
    if error:
        return error
    modules = [{"id": key, "nombre": value} for key, value in MODULES.items()
               if key != "usuarios" or is_admin()]
    return jsonify({"modulos": modules})


@app.route("/api/modulos/<table>", methods=["GET", "POST", "PUT", "DELETE"])
def api_modulo(table):
    error = require_login()
    if error:
        return error
    if not table_allowed(table):
        return jsonify({"mensaje": "Módulo no permitido."}), 404
    if table == "usuarios" and not is_admin():
        return jsonify({"mensaje": "Solo un administrador puede gestionar usuarios."}), 403

    conexion = cursor = None
    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor(dictionary=True)
        columns = get_columns(cursor, table)
        primary = get_primary_key(columns)

        if request.method == "GET":
            description = describe_table(cursor, table)
            rows = list_rows(cursor, table, columns)
            return jsonify({"esquema": description, "registros": rows}), 200

        data = request.get_json(silent=True) or {}
        if request.method == "POST":
            clean = sanitize_data(cursor, table, data, inserting=True)
            if table == "usuarios" and not clean.get("password_hash"):
                return jsonify({"mensaje": "La contraseña es obligatoria para crear un usuario."}), 400
            if not clean:
                return jsonify({"mensaje": "No se recibieron campos válidos para guardar."}), 400
            fields = list(clean.keys())
            sql = (f"INSERT INTO {quote_identifier(table)} "
                   f"({', '.join(quote_identifier(f) for f in fields)}) "
                   f"VALUES ({', '.join(['%s'] * len(fields))})")
            cursor.execute(sql, [clean[f] for f in fields])
            conexion.commit()
            return jsonify({"mensaje": f"{MODULES[table]} registrado correctamente.",
                            "id": cursor.lastrowid}), 201

        if request.method == "PUT":
            pk_values = data.get("pk", {})
            payload = data.get("datos", {})
            key, key_value, _ = get_row_by_pk(cursor, table, pk_values)
            clean = sanitize_data(cursor, table, payload, inserting=False)
            if not clean:
                return jsonify({"mensaje": "No hay cambios para guardar."}), 400
            assignments = ", ".join(f"{quote_identifier(f)} = %s" for f in clean)
            cursor.execute(
                f"UPDATE {quote_identifier(table)} SET {assignments} WHERE {quote_identifier(key)} = %s",
                list(clean.values()) + [key_value]
            )
            conexion.commit()
            return jsonify({"mensaje": f"{MODULES[table]} actualizado correctamente."}), 200

        # DELETE uses soft delete when the table has an 'activo' column.
        pk_values = data.get("pk", {})
        key, key_value, cols = get_row_by_pk(cursor, table, pk_values)
        active_col = next((c["name"] for c in cols if c["name"].lower() == "activo"), None)
        if active_col:
            cursor.execute(
                f"UPDATE {quote_identifier(table)} SET {quote_identifier(active_col)} = %s "
                f"WHERE {quote_identifier(key)} = %s",
                (False, key_value)
            )
            conexion.commit()
            return jsonify({"mensaje": f"{MODULES[table]} desactivado correctamente."}), 200
        cursor.execute(
            f"DELETE FROM {quote_identifier(table)} WHERE {quote_identifier(key)} = %s",
            (key_value,)
        )
        conexion.commit()
        return jsonify({"mensaje": f"{MODULES[table]} eliminado correctamente."}), 200

    except ValueError as exc:
        if conexion is not None and conexion.is_connected():
            conexion.rollback()
        return jsonify({"mensaje": str(exc)}), 400
    except IntegrityError:
        if conexion is not None and conexion.is_connected():
            conexion.rollback()
        app.logger.exception("Restricción de integridad en módulo %s", table)
        return jsonify({"mensaje": "No se pudo guardar/eliminar porque el registro tiene campos obligatorios o relaciones con otros registros. Revisa los datos y las dependencias."}), 409
    except Error:
        if conexion is not None and conexion.is_connected():
            conexion.rollback()
        app.logger.exception("Error en el módulo %s", table)
        return jsonify({"mensaje": "Ocurrió un error en MySQL. Revisa la terminal de Flask para conocer el detalle."}), 500
    finally:
        if cursor is not None:
            cursor.close()
        if conexion is not None and conexion.is_connected():
            conexion.close()


@app.errorhandler(404)
def pagina_no_encontrada(error):
    if request.path.startswith("/api/"):
        return jsonify({"mensaje": "La ruta solicitada no existe."}), 404
    return "Página no encontrada.", 404


if __name__ == "__main__":
    print("\nRutas registradas en Flask:")
    print(app.url_map)
    print("\nAbre http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=True)
