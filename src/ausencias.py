"""
ausencias.py
Módulo para la gestión de ausencias y reasignación dinámica (modo contingencia).
RF-05: Gestión de ausencias y reasignación dinámica.
Versión final con corrección: al cubrir T con libres de A, se excluye a quienes trabajaron ayer.
"""

import sqlite3
from datetime import datetime, timedelta
import pandas as pd
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src import database
from src import ciclos
from src import grupo_b

# ------------------------------------------------------------
# Gestión de ausencias (CRUD)
# ------------------------------------------------------------

def registrar_ausencia(persona_id, fecha_inicio, fecha_fin, tipo, motivo=""):
    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO ausencias (persona_id, fecha_inicio, fecha_fin, tipo, motivo)
        VALUES (?, ?, ?, ?, ?)
    """, (persona_id, fecha_inicio, fecha_fin, tipo, motivo))
    conn.commit()
    conn.close()
    print(f"✅ Ausencia registrada: Persona {persona_id} del {fecha_inicio} al {fecha_fin} ({tipo})")

def eliminar_ausencia(ausencia_id):
    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM ausencias WHERE id = ?", (ausencia_id,))
    conn.commit()
    conn.close()
    print(f"✅ Ausencia {ausencia_id} eliminada.")

def obtener_ausencias(mes=None, año=None, persona_id=None):
    conn = database.get_db_connection()
    cursor = conn.cursor()
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
    
    cursor.execute(query, params)
    filas = cursor.fetchall()
    conn.close()
    return [
        {
            "id": f[0],
            "persona_id": f[1],
            "fecha_inicio": f[2],
            "fecha_fin": f[3],
            "tipo": f[4],
            "motivo": f[5]
        }
        for f in filas
    ]

# ------------------------------------------------------------
# Funciones auxiliares
# ------------------------------------------------------------

def requiere_t(fecha, año, pais='CO'):
    """Determina si un día requiere cobertura en turno T según RF-04."""
    fecha_obj = datetime.strptime(fecha, "%Y-%m-%d").date()
    festivos = ciclos.obtener_festivos(año, pais)
    es_festivo = fecha_obj in festivos
    dia_semana = fecha_obj.weekday()
    if es_festivo or dia_semana == 6:
        return False
    elif dia_semana == 5:
        return True
    else:
        return True

def obtener_programacion_original(persona_id, df_original):
    """Devuelve un diccionario {fecha: turno} para una persona."""
    sub = df_original[df_original['persona_id'] == persona_id]
    return dict(zip(sub['fecha'], sub['turno']))

# ------------------------------------------------------------
# Lógica de reasignación
# ------------------------------------------------------------

def obtener_calendario_mes(año, mes):
    conn = database.get_db_connection()
    query = """
        SELECT c.persona_id, p.grupo, p.subgrupo, c.fecha, c.turno, c.es_festivo
        FROM calendario c
        JOIN personas p ON c.persona_id = p.id
        WHERE c.fecha LIKE ?
    """
    df = pd.read_sql_query(query, conn, params=[f"{año}-{mes:02d}%"])
    conn.close()
    return df

def aplicar_ausencias_al_calendario(df, ausencias):
    conn = database.get_db_connection()
    cursor = conn.cursor()
    
    for aus in ausencias:
        pid = aus['persona_id']
        inicio = datetime.strptime(aus['fecha_inicio'], "%Y-%m-%d")
        fin = datetime.strptime(aus['fecha_fin'], "%Y-%m-%d")
        delta = (fin - inicio).days + 1
        for i in range(delta):
            fecha = (inicio + timedelta(days=i)).strftime("%Y-%m-%d")
            mask = (df['persona_id'] == pid) & (df['fecha'] == fecha)
            if mask.any():
                df.loc[mask, 'turno'] = aus['tipo']
            cursor.execute("""
                UPDATE calendario
                SET turno = ?
                WHERE persona_id = ? AND fecha = ?
            """, (aus['tipo'], pid, fecha))
    
    conn.commit()
    conn.close()
    return df

def verificar_cobertura_minima(df, año, mes):
    deficits = {}
    fechas = sorted(df['fecha'].unique())
    
    for fecha in fechas:
        dia_df = df[df['fecha'] == fecha]
        m_count = len(dia_df[(dia_df['turno'] == 'M')])
        n_count = len(dia_df[(dia_df['turno'] == 'N')])
        t_count = len(dia_df[(dia_df['turno'] == 'T')])
        
        necesarios = {'M': 2, 'N': 2}
        fecha_obj = datetime.strptime(fecha, "%Y-%m-%d").date()
        festivos = ciclos.obtener_festivos(año)
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

def reasignar_por_ausencias(df, año, mes, deficits, df_original, ausencias_list):
    """
    B2 asume los turnos del ausente con la siguiente lógica:
    - Si la ausencia empieza en L, se ignoran los L iniciales hasta el primer M/N.
    - A partir del primer M/N, B2 asume todos los días restantes (incluyendo L posteriores)
      aplicando la regla de pares: primer L de un par -> T si requiere T, segundo L -> L.
    - Si la ausencia empieza en M/N, B2 asume desde el inicio.
    Luego, se cubre el hueco en T (generado por mover B2) con personal de Grupo A,
    priorizando a aquellos que estén en el segundo día de un par de descansos y que no hayan trabajado ayer.
    """
    conn = database.get_db_connection()
    cursor = conn.cursor()
    
    personas = database.obtener_personas()
    info_persona = {p['id']: p for p in personas}
    acciones = []
    
    # Procesar cada ausencia
    for aus in ausencias_list:
        ausente_id = aus['persona_id']
        inicio = datetime.strptime(aus['fecha_inicio'], "%Y-%m-%d")
        fin = datetime.strptime(aus['fecha_fin'], "%Y-%m-%d")
        delta = (fin - inicio).days + 1
        
        prog_original = obtener_programacion_original(ausente_id, df_original)
        
        # Generar lista de fechas de la ausencia en orden
        fechas_ausencia = [(inicio + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(delta)]
        
        # Determinar el índice del primer día que no sea L en la programación original
        primer_no_L = None
        for i, fecha in enumerate(fechas_ausencia):
            if fecha in prog_original and prog_original[fecha] in ['M', 'N']:
                primer_no_L = i
                break
        
        if primer_no_L is None:
            # Toda la ausencia son L -> no se hace nada con B2
            acciones.append(f"Ausencia de {ausente_id} completa en L, no se reasigna B2")
            continue
        
        # A partir de primer_no_L, B2 asume todo
        for i in range(primer_no_L, delta):
            fecha = fechas_ausencia[i]
            if fecha not in prog_original:
                continue
            turno_original = prog_original[fecha]
            
            if turno_original in ['M', 'N']:
                # Asignar directamente
                df.loc[(df['persona_id'] == 8) & (df['fecha'] == fecha), 'turno'] = turno_original
                cursor.execute("UPDATE calendario SET turno = ? WHERE persona_id = 8 AND fecha = ?",
                               (turno_original, fecha))
                acciones.append(f"B2 asume turno {turno_original} de ausente {ausente_id} el {fecha}")
            elif turno_original == 'L':
                # Aplicar regla de pares
                fecha_obj = datetime.strptime(fecha, "%Y-%m-%d").date()
                dia_anterior = (fecha_obj - timedelta(days=1)).isoformat()
                
                # Verificar si el día anterior en la prog original es L (para saber si es segundo)
                if dia_anterior in prog_original and prog_original[dia_anterior] == 'L':
                    es_segundo = True
                else:
                    es_segundo = False
                
                if not es_segundo:
                    # Primer día del par
                    if requiere_t(fecha, año):
                        nuevo_turno = 'T'
                        acciones.append(f"B2 asume primer L de par como T el {fecha}")
                    else:
                        nuevo_turno = 'L'
                        acciones.append(f"B2 asume primer L de par como L (sin T) el {fecha}")
                else:
                    nuevo_turno = 'L'
                    acciones.append(f"B2 asume segundo L de par como L el {fecha}")
                
                df.loc[(df['persona_id'] == 8) & (df['fecha'] == fecha), 'turno'] = nuevo_turno
                cursor.execute("UPDATE calendario SET turno = ? WHERE persona_id = 8 AND fecha = ?",
                               (nuevo_turno, fecha))
    
    # Recalcular déficits después de mover B2
    nuevos_deficits = verificar_cobertura_minima(df, año, mes)
    
    # Cubrir déficits en T con libres de A, priorizando segundo día de par y evitando trabajar dos días seguidos
    for fecha, necesarios in nuevos_deficits.items():
        if 'T' in necesarios:
            cantidad = necesarios['T']
            fecha_obj = datetime.strptime(fecha, "%Y-%m-%d").date()
            ayer = (fecha_obj - timedelta(days=1)).isoformat()
            
            # Personas de Grupo A que hoy están libres (L) en el calendario actual
            libres_hoy = df[(df['fecha'] == fecha) & (df['grupo'] == 'A') & (df['turno'] == 'L')]['persona_id'].tolist()
            
            # Excluir a quienes tuvieron T ayer (trabajaron el día anterior)
            excluir = set()
            for pid in libres_hoy:
                ayer_row = df[(df['persona_id'] == pid) & (df['fecha'] == ayer)]
                if not ayer_row.empty and ayer_row['turno'].values[0] == 'T':
                    excluir.add(pid)
            
            candidatos_posibles = [pid for pid in libres_hoy if pid not in excluir]
            
            # Clasificar según calendario original: prioritarios si ayer también tenían L (segundo día)
            prioritarios = []
            normales = []
            for pid in candidatos_posibles:
                ayer_original = df_original[(df_original['persona_id'] == pid) & (df_original['fecha'] == ayer)]
                if not ayer_original.empty and ayer_original['turno'].values[0] == 'L':
                    prioritarios.append(pid)
                else:
                    normales.append(pid)
            
            candidatos = prioritarios + normales
            for _ in range(min(cantidad, len(candidatos))):
                candidato = candidatos.pop(0)
                df.loc[(df['persona_id'] == candidato) & (df['fecha'] == fecha), 'turno'] = 'T'
                cursor.execute("UPDATE calendario SET turno = ? WHERE persona_id = ? AND fecha = ?",
                               ('T', candidato, fecha))
                acciones.append(f"Persona {candidato} ({info_persona[candidato]['nombre']}) asignada a T el {fecha}")
    
    conn.commit()
    conn.close()
    return df, acciones

def aplicar_contingencia(año, mes):
    """
    Aplica la lógica de contingencia:
    - Obtiene calendario, guarda copia original.
    - Aplica ausencias.
    - Reasigna según reglas.
    Retorna (df, acciones)
    """
    df = obtener_calendario_mes(año, mes)
    if df.empty:
        return None, []
    
    df_original = df.copy()
    ausencias_list = obtener_ausencias(mes=mes, año=año)
    
    if ausencias_list:
        print(f"Se encontraron {len(ausencias_list)} ausencias.")
        df = aplicar_ausencias_al_calendario(df, ausencias_list)
    else:
        print("No hay ausencias registradas para este mes.")
    
    deficits = verificar_cobertura_minima(df, año, mes)
    if deficits and ausencias_list:
        print(f"⚠️ Déficits detectados en {len(deficits)} días.")
        df, acciones = reasignar_por_ausencias(df, año, mes, deficits, df_original, ausencias_list)
    else:
        acciones = []
        print("✅ Cobertura mínima satisfecha sin reasignaciones.")
    
    return df, acciones