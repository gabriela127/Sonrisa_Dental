# Sonrisa Dental — versión con módulos CRUD dinámicos

## Qué incluye
- Inicio de sesión y cierre de sesión conservados.
- Dashboard con módulos de pacientes, citas, tratamientos, facturas, pagos, detalles de factura, tratamientos realizados y usuarios.
- Listado, registro, edición y eliminación/desactivación de registros.
- Los formularios consultan los nombres y tipos de columnas que ya existen en MySQL.
- Los campos de relaciones (claves foráneas) se muestran como listas de opciones cuando MySQL define esas relaciones.
- El módulo de usuarios solo aparece para la sesión con rol `ADMIN`; las contraseñas se guardan con hash y nunca se muestran.
- No crea, elimina ni modifica tablas y no inserta datos de prueba.

## Instalación en Windows / VS Code
1. Descomprime este ZIP.
2. Abre la carpeta `ConsultorioDental` en Visual Studio Code.
3. **Conserva tu archivo `.env` actual** (no se incluye en el ZIP para proteger la contraseña de MySQL). Si no tienes `.env`, copia `.env.example` como `.env` y completa los valores.
4. Abre Terminal > New Terminal.
5. Crea/activa el entorno e instala dependencias:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r requirements.txt
   ```
   Si ya tienes `.venv`, puedes activarlo en vez de crear otro.
6. Ejecuta:
   ```powershell
   python app.py
   ```
7. Abre http://127.0.0.1:5000 e inicia sesión con tu administrador existente.

## Notas importantes
- No se incluye el entorno virtual `.venv`; se instala en tu equipo con `requirements.txt`.
- No se incluye `.env` por seguridad.
- El formulario se adapta a las columnas reales de cada tabla. Si una tabla tiene campos obligatorios sin valor predeterminado, deberás completarlos; si un campo obligatorio o una regla de negocio no puede inferirse automáticamente, MySQL mostrará un mensaje de error.
- Las operaciones de eliminación desactivan el registro cuando la tabla contiene una columna `activo`; en las tablas sin esa columna intentan eliminarlo físicamente y MySQL impedirá la operación si hay relaciones que lo prohíban.
- El panel es una base CRUD genérica para las tablas existentes, no sustituye reglas de negocio específicas (por ejemplo, evitar solapamiento de citas, cálculos de factura o validación de pagos). Estas reglas requieren conocer el diseño exacto y los requisitos de tu curso.
- Para usar datos reales de pacientes, añade medidas de seguridad adecuadas y cambia `SECRET_KEY` por una clave privada larga en `.env`.
