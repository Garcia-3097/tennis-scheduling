"""
ausencias.py
Gestión de ausencias y lógica de contingencia.
"""

import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple, Optional

from . import database
from . import ciclos
from . import grupo_b
from . import balanceo

# ------------------------------------------------------------
# CRUD de ausencias
# ------------------------------------------------------------
def registrar_ausencia(persona_id, fecha_inicio, fecha_fin, tipo, motivo=""):
    with database.get_connection() as conn:
        conn.execute("""
            INSERT INTO ausencias (persona_id, fecha_inicio, fecha_fin, tipo, motivo)
            VALUES (?, ?, ?, ?, ?)
        """, (persona_id, fecha_inicio, fecha_fin, tipo, motivo))
        conn.commit()

def eliminar_ausencia(ausencia_id):
    with database.get_connection() as conn:
        conn.execute("DELETE FROM ausencias WHERE id = ?", (ausencia_id,))
        conn.commit()

def obtener_ausencias(mes=None, año=None, persona_id=None):
    query = "SELECT id, persona_id, fecha_inicio, fecha_fin, tipo, motivo FROM ausencias"
    params = []
    condiciones = []
    if mes and año:
        inicio = f"{año}-{mes:02d}-%"
        condiciones.append("(fecha_inicio LIKE ? OR fecha_fin LIKE ?)")
        params.extend([inicio, inicio])
    if persona_id:
        condiciones.append("persona_id = ?")
        params.append(persona_id)
    if condiciones:
        query += " WHERE " + " AND ".join(condiciones)
    with database.get_connection() as conn:
        cursor = conn.execute(query, params)
        return [
            {
                "id": row[0],
                "persona_id": row[1],
                "fecha_inicio": row[2],
                "fecha_fin": row[3],
                "tipo": row[4],
                "motivo": row[5]
            }
            for row in cursor.fetchall()
        ]

# ------------------------------------------------------------
# Funciones auxiliares
# ------------------------------------------------------------
def requiere_t(fecha, año, pais='CO'):
    fecha_obj = datetime.strptime(fecha, "%Y-%m-%d").date()
    festivos = ciclos.obtener_festivos(año, pais)
    es_festivo = fecha_obj in festivos
    dia_semana = fecha_obj.weekday()
    if es_festivo or dia_semana == 6:
        return False
    return True

def obtener_programacion_original(persona_id, df_original):
    sub = df_original[df_original['persona_id'] == persona_id]
    return dict(zip(sub['fecha'], sub['turno']))

def obtener_calendario_mes(año, mes):
    with database.get_connection() as conn:
        query = """
            SELECT c.persona_id, p.grupo, p.subgrupo, c.fecha, c.turno, c.es_festivo
            FROM calendario c
            JOIN personas p ON c.persona_id = p.id
            WHERE c.fecha LIKE ?
        """
        return pd.read_sql_query(query, conn, params=[f"{año}-{mes:02d}%"])

def aplicar_ausencias_al_calendario(df, ausencias_list):
    for aus in ausencias_list:
        pid = aus['persona_id']
        inicio = datetime.strptime(aus['fecha_inicio'], "%Y-%m-%d")
        fin = datetime.strptime(aus['fecha_fin'], "%Y-%m-%d")
        delta = (fin - inicio).days + 1
        for i in range(delta):
            fecha = (inicio + timedelta(days=i)).strftime("%Y-%m-%d")
            mask = (df['persona_id'] == pid) & (df['fecha'] == fecha)
            if mask.any():
                df.loc[mask, 'turno'] = aus['tipo']
    return df

def guardar_ausencias_en_bd(df, ausencias_list, año, mes):
    """Actualiza la base de datos con los turnos de ausencia (V, PNR, etc.) para las fechas afectadas."""
    with database.get_connection() as conn:
        for aus in ausencias_list:
            pid = aus['persona_id']
            inicio = datetime.strptime(aus['fecha_inicio'], "%Y-%m-%d")
            fin = datetime.strptime(aus['fecha_fin'], "%Y-%m-%d")
            delta = (fin - inicio).days + 1
            for i in range(delta):
                fecha = (inicio + timedelta(days=i)).strftime("%Y-%m-%d")
                turno = aus['tipo']
                conn.execute("UPDATE calendario SET turno = ? WHERE persona_id = ? AND fecha = ?",
                             (turno, pid, fecha))
        conn.commit()

def verificar_cobertura_minima(df, año, mes):
    deficits = {}
    fechas = sorted(df['fecha'].unique())
    festivos = ciclos.obtener_festivos(año)
    for fecha in fechas:
        dia_df = df[df['fecha'] == fecha]
        m_count = len(dia_df[dia_df['turno'] == 'M'])
        n_count = len(dia_df[dia_df['turno'] == 'N'])
        t_count = len(dia_df[dia_df['turno'] == 'T'])

        necesarios = {'M': 2, 'N': 2}
        fecha_obj = datetime.strptime(fecha, "%Y-%m-%d").date()
        es_festivo = fecha_obj in festivos
        dia_semana = fecha_obj.weekday()
        if es_festivo or dia_semana == 6:
            necesarios['T'] = 0
        elif dia_semana == 5:
            necesarios['T'] = 1
        else:
            necesarios['T'] = 2

        faltan = {}
        if m_count < necesarios['M']:
            faltan['M'] = necesarios['M'] - m_count
        if n_count < necesarios['N']:
            faltan['N'] = necesarios['N'] - n_count
        if t_count < necesarios['T']:
            faltan['T'] = necesarios['T'] - t_count
        if faltan:
            deficits[fecha] = faltan
    return deficits

# ------------------------------------------------------------
# Lógica de reasignación (solo modifica DataFrame)
# ------------------------------------------------------------
def _reasignar_por_ausencias_df(
    df: pd.DataFrame,
    año: int,
    mes: int,
    deficits: Dict,
    df_original: pd.DataFrame,
    ausencias_list: List[Dict]
) -> Tuple[pd.DataFrame, List[str]]:
    """
    Realiza reasignaciones modificando el DataFrame.
    No escribe en la base de datos.
    """
    acciones = []
    info_persona = {p['id']: p for p in database.obtener_personas()}

    # Procesar cada ausencia
    for aus in ausencias_list:
        ausente_id = aus['persona_id']
        inicio = datetime.strptime(aus['fecha_inicio'], "%Y-%m-%d")
        fin = datetime.strptime(aus['fecha_fin'], "%Y-%m-%d")
        delta = (fin - inicio).days + 1

        prog_original = obtener_programacion_original(ausente_id, df_original)
        fechas_ausencia = [(inicio + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(delta)]

        # Encontrar primer día no L
        primer_no_L = None
        for i, fecha in enumerate(fechas_ausencia):
            if fecha in prog_original and prog_original[fecha] in ['M', 'N']:
                primer_no_L = i
                break

        if primer_no_L is None:
            acciones.append(f"Ausencia de {ausente_id} completa en L, no se reasigna B2")
            continue

        # Desde primer_no_L, B2 asume todos los días
        for i in range(primer_no_L, delta):
            fecha = fechas_ausencia[i]
            if fecha not in prog_original:
                continue
            turno_original = prog_original[fecha]

            if turno_original in ['M', 'N']:
                nuevo_turno = turno_original
                acciones.append(f"B2 asume {nuevo_turno} de ausente {ausente_id} el {fecha}")
            elif turno_original == 'L':
                fecha_obj = datetime.strptime(fecha, "%Y-%m-%d").date()
                dia_anterior = (fecha_obj - timedelta(days=1)).isoformat()
                es_segundo = (dia_anterior in prog_original and prog_original[dia_anterior] == 'L')
                if not es_segundo:
                    if requiere_t(fecha, año):
                        nuevo_turno = 'T'
                    else:
                        nuevo_turno = 'L'
                else:
                    nuevo_turno = 'L'
                acciones.append(f"B2 asume L de par como {nuevo_turno} el {fecha}")

            # Actualizar DataFrame
            mask = (df['persona_id'] == grupo_b.ID_B2) & (df['fecha'] == fecha)
            if mask.any():
                df.loc[mask, 'turno'] = nuevo_turno

    # Recalcular déficits después de mover B2
    nuevos_deficits = verificar_cobertura_minima(df, año, mes)

    # Cubrir déficits en T con libres de A
    for fecha, necesarios in nuevos_deficits.items():
        if 'T' not in necesarios:
            continue
        cantidad = necesarios['T']
        fecha_obj = datetime.strptime(fecha, "%Y-%m-%d").date()
        ayer = (fecha_obj - timedelta(days=1)).isoformat()

        libres_hoy = df[(df['fecha'] == fecha) & (df['grupo'] == 'A') & (df['turno'] == 'L')]['persona_id'].tolist()
        excluir = set()
        for pid in libres_hoy:
            ayer_row = df[(df['persona_id'] == pid) & (df['fecha'] == ayer)]
            if not ayer_row.empty and ayer_row['turno'].values[0] == 'T':
                excluir.add(pid)
        candidatos = [pid for pid in libres_hoy if pid not in excluir]

        # Priorizar segundos de par
        prioritarios = []
        normales = []
        for pid in candidatos:
            ayer_original = df_original[(df_original['persona_id'] == pid) & (df_original['fecha'] == ayer)]
            if not ayer_original.empty and ayer_original['turno'].values[0] == 'L':
                prioritarios.append(pid)
            else:
                normales.append(pid)
        candidatos = prioritarios + normales

        for _ in range(min(cantidad, len(candidatos))):
            candidato = candidatos.pop(0)
            df.loc[(df['persona_id'] == candidato) & (df['fecha'] == fecha), 'turno'] = 'T'
            acciones.append(f"Persona {candidato} ({info_persona[candidato]['nombre']}) asignada a T el {fecha}")

    return df, acciones

# ------------------------------------------------------------
# Funciones que escriben en BD (modo contingencia oficial)
# ------------------------------------------------------------
def reasignar_por_ausencias(df, año, mes, deficits, df_original, ausencias_list):
    """
    Versión que modifica DataFrame y también actualiza la base de datos.
    """
    df_mod, acciones = _reasignar_por_ausencias_df(df, año, mes, deficits, df_original, ausencias_list)

    # Escribir cambios en la BD
    with database.get_connection() as conn:
        # Actualizar turnos de B2
        for fecha in df_mod['fecha'].unique():
            for pid in [grupo_b.ID_B2]:
                turno = df_mod[(df_mod['persona_id'] == pid) & (df_mod['fecha'] == fecha)]['turno'].values
                if len(turno) > 0:
                    conn.execute("UPDATE calendario SET turno = ? WHERE persona_id = ? AND fecha = ?",
                                 (turno[0], pid, fecha))
        # Actualizar turnos de A (los que se asignaron a T)
        for fecha, necesarios in deficits.items():
            if 'T' not in necesarios:
                continue
            # Obtener los candidatos que se asignaron (mirando df_mod)
            asignados = df_mod[(df_mod['fecha'] == fecha) & (df_mod['turno'] == 'T') & (df_mod['grupo'] == 'A')]['persona_id'].tolist()
            for pid in asignados:
                conn.execute("UPDATE calendario SET turno = ? WHERE persona_id = ? AND fecha = ?",
                             ('T', pid, fecha))
        conn.commit()

    return df_mod, acciones

def aplicar_contingencia(año, mes):
    """Versión que lee desde BD, aplica y guarda en BD."""
    df = obtener_calendario_mes(año, mes)
    if df.empty:
        return None, []
    df_original = df.copy()
    ausencias_list = obtener_ausencias(mes=mes, año=año)

    if ausencias_list:
        df = aplicar_ausencias_al_calendario(df, ausencias_list)
        # Persistir los cambios de ausencias en la BD (incluso si no hay déficits)
        guardar_ausencias_en_bd(df, ausencias_list, año, mes)

    deficits = verificar_cobertura_minima(df, año, mes)
    if deficits and ausencias_list:
        df, acciones = reasignar_por_ausencias(df, año, mes, deficits, df_original, ausencias_list)
    else:
        acciones = []

    # --- NUEVO: Aplicar balanceo de equidad ---
    # El balanceo es una optimización no crítica: si falla, las ausencias
    # ya están correctamente aplicadas y el calendario es válido.
    try:
        df = balanceo.aplicar_balanceo(df, año, mes)
        balanceo.guardar_balanceo_en_bd(df, año, mes)
    except Exception as e:
        import logging
        logging.warning(
            f"[balanceo] Error no crítico al balancear/guardar "
            f"({año}-{mes:02d}): {e}"
        )
    # -----------------------------------------

    return df, acciones

def aplicar_contingencia_a_df(df_original, año, mes, pais='CO'):
    """
    Aplica contingencia a un DataFrame dado (no escribe en BD).
    """
    df = df_original.copy()
    ausencias_list = obtener_ausencias(mes=mes, año=año)

    if ausencias_list:
        df = aplicar_ausencias_al_calendario(df, ausencias_list)
    deficits = verificar_cobertura_minima(df, año, mes)
    if deficits and ausencias_list:
        df, acciones = _reasignar_por_ausencias_df(df, año, mes, deficits, df_original, ausencias_list)
    else:
        acciones = []
        
    # --- NUEVO: Aplicar balanceo (solo modifica DataFrame, no persiste) ---
    # El balanceo es no crítico: si falla, el calendario sigue siendo válido.
    try:
        df = balanceo.aplicar_balanceo(df, año, mes)
    except Exception as e:
        import logging
        logging.warning(
            f"[balanceo] Error no crítico en vista previa "
            f"({año}-{mes:02d}): {e}"
        )
    # No se guarda en BD porque esta función se usa para alternativas o vista previa
    # -----------------------------------------------------------------------

    return df, acciones