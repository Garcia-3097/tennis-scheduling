"""
database.py
Gestión de la base de datos SQLite.
"""

import sqlite3
import os
import sys
from typing import List, Dict, Any, Optional

# ------------------------------------------------------------
# Constantes
# ------------------------------------------------------------
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DB_PATH = os.path.join(BASE_DIR, "data", "schedules.db")

def init_db() -> None:
    """Crea tablas y datos iniciales si no existen."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()

        # Tabla personas
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS personas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                grupo TEXT NOT NULL CHECK(grupo IN ('A', 'B')),
                subgrupo TEXT CHECK(subgrupo IN ('B1', 'B2')),
                activo INTEGER DEFAULT 1
            )
        """)

        # Tabla configuracion
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS configuracion (
                id INTEGER PRIMARY KEY CHECK(id=1),
                pais TEXT DEFAULT 'CO',
                ciclo_default TEXT DEFAULT '2x2x2',
                modo_default TEXT DEFAULT 'normal',
                b1_descansa_sabados INTEGER DEFAULT 1,
                b2_descansa_sabados INTEGER DEFAULT 0
            )
        """)

        # Tabla calendario
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

        # Tabla ausencias
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

        # Tabla estado_ciclo
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

        # Datos iniciales
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

        cursor.execute("SELECT COUNT(*) FROM configuracion")
        if cursor.fetchone()[0] == 0:
            cursor.execute("""
                INSERT INTO configuracion (id, pais, ciclo_default, modo_default, b1_descansa_sabados, b2_descansa_sabados)
                VALUES (1, 'CO', '2x2x2', 'normal', 1, 0)
            """)

        conn.commit()

def get_connection() -> sqlite3.Connection:
    """Retorna una conexión a la base de datos."""
    return sqlite3.connect(DB_PATH)

# ------------------------------------------------------------
# Personas
# ------------------------------------------------------------
def obtener_personas(activas: bool = True) -> List[Dict[str, Any]]:
    """Retorna la lista de personas (activas o todas)."""
    with get_connection() as conn:
        cursor = conn.cursor()
        if activas:
            cursor.execute("SELECT id, nombre, grupo, subgrupo FROM personas WHERE activo=1")
        else:
            cursor.execute("SELECT id, nombre, grupo, subgrupo FROM personas")
        return [{"id": row[0], "nombre": row[1], "grupo": row[2], "subgrupo": row[3]}
                for row in cursor.fetchall()]

def actualizar_nombre(persona_id: int, nuevo_nombre: str) -> None:
    """Actualiza el nombre de una persona."""
    with get_connection() as conn:
        conn.execute("UPDATE personas SET nombre = ? WHERE id = ?", (nuevo_nombre, persona_id))
        conn.commit()

def actualizar_grupo(persona_id: int, nuevo_grupo: str, nuevo_subgrupo: Optional[str] = None) -> None:
    """Actualiza el grupo y subgrupo de una persona."""
    with get_connection() as conn:
        conn.execute("UPDATE personas SET grupo = ?, subgrupo = ? WHERE id = ?",
                     (nuevo_grupo, nuevo_subgrupo, persona_id))
        conn.commit()

# ------------------------------------------------------------
# Configuración
# ------------------------------------------------------------
def obtener_configuracion() -> Dict[str, Any]:
    """Retorna la configuración actual."""
    with get_connection() as conn:
        cursor = conn.execute("""
            SELECT pais, ciclo_default, modo_default, b1_descansa_sabados, b2_descansa_sabados
            FROM configuracion WHERE id=1
        """)
        row = cursor.fetchone()
        if row:
            return {
                "pais": row[0],
                "ciclo_default": row[1],
                "modo_default": row[2],
                "b1_descansa_sabados": bool(row[3]),
                "b2_descansa_sabados": bool(row[4])
            }
        return {
            "pais": "CO",
            "ciclo_default": "2x2x2",
            "modo_default": "normal",
            "b1_descansa_sabados": True,
            "b2_descansa_sabados": False
        }

def actualizar_configuracion(
    pais: Optional[str] = None,
    ciclo_default: Optional[str] = None,
    modo_default: Optional[str] = None,
    b1_descansa_sabados: Optional[bool] = None,
    b2_descansa_sabados: Optional[bool] = None
) -> None:
    """Actualiza campos de configuración."""
    updates = []
    values = []
    if pais is not None:
        updates.append("pais = ?")
        values.append(pais)
    if ciclo_default is not None:
        updates.append("ciclo_default = ?")
        values.append(ciclo_default)
    if modo_default is not None:
        updates.append("modo_default = ?")
        values.append(modo_default)
    if b1_descansa_sabados is not None:
        updates.append("b1_descansa_sabados = ?")
        values.append(1 if b1_descansa_sabados else 0)
    if b2_descansa_sabados is not None:
        updates.append("b2_descansa_sabados = ?")
        values.append(1 if b2_descansa_sabados else 0)

    if updates:
        with get_connection() as conn:
            conn.execute(f"UPDATE configuracion SET {', '.join(updates)} WHERE id=1", values)
            conn.commit()