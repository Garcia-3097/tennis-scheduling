"""
database.py
Módulo para la creación y gestión de la base de datos SQLite del sistema SecureSchedule.
Adaptado para ejecutables de PyInstaller: la BD se guarda en la misma carpeta que el .exe.
"""

import sqlite3
import os
import sys

# Determinar la carpeta base (donde está el ejecutable o el script)
if getattr(sys, 'frozen', False):
    # Modo ejecutable (PyInstaller)
    BASE_DIR = os.path.dirname(sys.executable)
else:
    # Modo desarrollo (script Python)
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DB_PATH = os.path.join(BASE_DIR, "data", "schedules.db")

def init_db():
    """Crea todas las tablas y carga datos iniciales si no existen."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # --- Tabla personas ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS personas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            grupo TEXT NOT NULL CHECK(grupo IN ('A', 'B')),
            subgrupo TEXT CHECK(subgrupo IN ('B1', 'B2')),
            activo INTEGER DEFAULT 1
        )
    """)

    # --- Tabla configuracion ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS configuracion (
            id INTEGER PRIMARY KEY CHECK(id=1),
            pais TEXT DEFAULT 'CO',
            ciclo_default TEXT DEFAULT '2x2x2',
            modo_default TEXT DEFAULT 'normal'
        )
    """)
    try:
        cursor.execute("ALTER TABLE configuracion ADD COLUMN b1_descansa_sabados INTEGER DEFAULT 1")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE configuracion ADD COLUMN b2_descansa_sabados INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    # --- Tabla calendario ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS calendario (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            persona_id INTEGER NOT NULL,
            fecha TEXT NOT NULL,
            turno TEXT NOT NULL,
            es_festivo INTEGER DEFAULT 0,
            FOREIGN KEY (persona_id) REFERENCES personas (id),
            UNIQUE(persona_id, fecha)
        )
    """)

    # --- Tabla ausencias ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ausencias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            persona_id INTEGER NOT NULL,
            fecha_inicio TEXT NOT NULL,
            fecha_fin TEXT NOT NULL,
            tipo TEXT NOT NULL CHECK(tipo IN ('V', 'PNR', 'IM', 'CD')),
            motivo TEXT,
            FOREIGN KEY (persona_id) REFERENCES personas (id)
        )
    """)

    # --- Tabla estado_ciclo ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS estado_ciclo (
            persona_id INTEGER NOT NULL,
            año INTEGER NOT NULL,
            mes INTEGER NOT NULL,
            offset INTEGER NOT NULL,
            ciclo TEXT NOT NULL,
            FOREIGN KEY (persona_id) REFERENCES personas (id),
            PRIMARY KEY (persona_id, año, mes)
        )
    """)

    # --- Insertar personas iniciales (si tabla vacía) ---
    cursor.execute("SELECT COUNT(*) FROM personas")
    if cursor.fetchone()[0] == 0:
        personas_iniciales = [
            ("Persona A1", "A", None),
            ("Persona A2", "A", None),
            ("Persona A3", "A", None),
            ("Persona A4", "A", None),
            ("Persona A5", "A", None),
            ("Persona A6", "A", None),
            ("B1 - Nombre", "B", "B1"),
            ("B2 - Nombre", "B", "B2"),
        ]
        cursor.executemany(
            "INSERT INTO personas (nombre, grupo, subgrupo) VALUES (?, ?, ?)",
            personas_iniciales
        )
        print("✅ Personas iniciales insertadas.")

    # --- Insertar configuración por defecto ---
    cursor.execute("SELECT COUNT(*) FROM configuracion")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
            INSERT INTO configuracion (id, pais, ciclo_default, modo_default, b1_descansa_sabados, b2_descansa_sabados)
            VALUES (1, 'CO', '2x2x2', 'normal', 1, 0)
        """)
        print("✅ Configuración por defecto insertada.")

    conn.commit()
    conn.close()
    print("✅ Base de datos inicializada correctamente.")

def get_db_connection():
    """Devuelve una conexión a la base de datos."""
    return sqlite3.connect(DB_PATH)

def obtener_personas(activas_solo=True):
    conn = get_db_connection()
    cursor = conn.cursor()
    if activas_solo:
        cursor.execute("SELECT id, nombre, grupo, subgrupo FROM personas WHERE activo=1")
    else:
        cursor.execute("SELECT id, nombre, grupo, subgrupo FROM personas")
    filas = cursor.fetchall()
    conn.close()
    return [{"id": f[0], "nombre": f[1], "grupo": f[2], "subgrupo": f[3]} for f in filas]

def actualizar_nombre(persona_id, nuevo_nombre):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE personas SET nombre = ? WHERE id = ?", (nuevo_nombre, persona_id))
    conn.commit()
    conn.close()
    print(f"✅ Nombre de persona {persona_id} actualizado.")

def obtener_configuracion():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT pais, ciclo_default, modo_default, b1_descansa_sabados, b2_descansa_sabados FROM configuracion WHERE id=1")
    fila = cursor.fetchone()
    conn.close()
    if fila:
        return {
            "pais": fila[0],
            "ciclo_default": fila[1],
            "modo_default": fila[2],
            "b1_descansa_sabados": bool(fila[3]),
            "b2_descansa_sabados": bool(fila[4])
        }
    else:
        return {
            "pais": "CO",
            "ciclo_default": "2x2x2",
            "modo_default": "normal",
            "b1_descansa_sabados": True,
            "b2_descansa_sabados": False
        }

def actualizar_configuracion(pais=None, ciclo_default=None, modo_default=None,
                             b1_descansa_sabados=None, b2_descansa_sabados=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    campos = []
    valores = []
    if pais is not None:
        campos.append("pais = ?")
        valores.append(pais)
    if ciclo_default is not None:
        campos.append("ciclo_default = ?")
        valores.append(ciclo_default)
    if modo_default is not None:
        campos.append("modo_default = ?")
        valores.append(modo_default)
    if b1_descansa_sabados is not None:
        campos.append("b1_descansa_sabados = ?")
        valores.append(1 if b1_descansa_sabados else 0)
    if b2_descansa_sabados is not None:
        campos.append("b2_descansa_sabados = ?")
        valores.append(1 if b2_descansa_sabados else 0)
    if campos:
        query = f"UPDATE configuracion SET {', '.join(campos)} WHERE id=1"
        cursor.execute(query, valores)
        conn.commit()
    conn.close()
    print("✅ Configuración actualizada.")

def actualizar_grupo(persona_id, nuevo_grupo, nuevo_subgrupo=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE personas SET grupo = ?, subgrupo = ? WHERE id = ?",
                   (nuevo_grupo, nuevo_subgrupo, persona_id))
    conn.commit()
    conn.close()
    print(f"✅ Grupo de persona {persona_id} actualizado a {nuevo_grupo} {nuevo_subgrupo or ''}")

if __name__ == "__main__":
    init_db()
    print("\n📋 Personas en la base de datos:")
    for p in obtener_personas():
        print(f"  ID {p['id']}: {p['nombre']} (Grupo {p['grupo']}{' - '+p['subgrupo'] if p['subgrupo'] else ''})")