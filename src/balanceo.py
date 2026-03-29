"""
balanceo.py
Módulo para equilibrar la carga de domingos y festivos entre el Grupo A
mediante intercambios puntuales de turnos, respetando la regla de descanso N→M.
"""

import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Tuple

from . import database
from . import ciclos


def obtener_dias_especiales(año: int, mes: int) -> List[str]:
    """
    Retorna lista de fechas (formato YYYY-MM-DD) que son domingo o festivo en el mes.
    """
    dias = ciclos.generar_rango_fechas(año, mes)
    festivos = ciclos.obtener_festivos(año)
    especiales = []
    for fecha in dias:
        if fecha.weekday() == 6 or fecha in festivos:
            especiales.append(fecha.isoformat())
    return especiales


def calcular_carga_actual(df: pd.DataFrame, dias_especiales: List[str]) -> Dict[int, int]:
    """
    Calcula cuántos días especiales trabaja cada persona del Grupo A (IDs 1..6).
    Se considera trabajado si el turno no es L ni código de ausencia.
    """
    grupo_a_ids = list(range(1, 7))
    carga = {pid: 0 for pid in grupo_a_ids}
    # Turnos que NO cuentan como trabajado en día especial
    no_trabajados = {'L', 'V', 'PNR', 'IM', 'CD'}

    for fecha in dias_especiales:
        for pid in grupo_a_ids:
            turno_series = df[(df['persona_id'] == pid) & (df['fecha'] == fecha)]['turno']
            if not turno_series.empty:
                turno = turno_series.iloc[0]
                if turno not in no_trabajados:
                    carga[pid] += 1
    return carga


def validar_transicion(df: pd.DataFrame, persona_id: int, fecha: str, nuevo_turno: str) -> bool:
    """
    Verifica que asignar nuevo_turno a persona_id en la fecha dada no cree
    una violación de la regla N (noche) → M (mañana) sin descanso.
    Revisa el día anterior y el día posterior si existen en el DataFrame.
    """
    fecha_obj = datetime.strptime(fecha, "%Y-%m-%d").date()

    # Día anterior
    dia_ant = (fecha_obj - timedelta(days=1)).isoformat()
    turno_ant = df[(df['persona_id'] == persona_id) & (df['fecha'] == dia_ant)]['turno']
    if not turno_ant.empty and turno_ant.iloc[0] == 'N' and nuevo_turno == 'M':
        return False

    # Día posterior
    dia_pos = (fecha_obj + timedelta(days=1)).isoformat()
    turno_pos = df[(df['persona_id'] == persona_id) & (df['fecha'] == dia_pos)]['turno']
    if not turno_pos.empty and nuevo_turno == 'N' and turno_pos.iloc[0] == 'M':
        return False

    return True


def aplicar_balanceo(df: pd.DataFrame, año: int, mes: int) -> pd.DataFrame:
    """
    Aplica intercambios de turnos en días especiales (domingos y festivos)
    para que la diferencia de carga entre las personas del Grupo A sea ≤ 1.
    Modifica el DataFrame in-place y lo retorna.
    """
    especiales = obtener_dias_especiales(año, mes)
    if not especiales:
        return df

    carga = calcular_carga_actual(df, especiales)
    grupo_a_ids = list(range(1, 7))

    # Mientras la diferencia máxima sea mayor a 1, intentar intercambios
    while max(carga.values()) - min(carga.values()) > 1:
        # Identificar persona con mayor carga y una con menor carga
        max_pid = max(carga, key=carga.get)
        min_pid = min(carga, key=carga.get)

        encontrado = False
        for fecha in especiales:
            turno_max = df[(df['persona_id'] == max_pid) & (df['fecha'] == fecha)]['turno']
            turno_min = df[(df['persona_id'] == min_pid) & (df['fecha'] == fecha)]['turno']
            if turno_max.empty or turno_min.empty:
                continue

            turno_max_val = turno_max.iloc[0]
            turno_min_val = turno_min.iloc[0]

            # Condición: max_pid trabaja (turno no libre/ausencia) y min_pid está libre (L)
            no_trabajados = {'L', 'V', 'PNR', 'IM', 'CD'}
            if turno_max_val not in no_trabajados and turno_min_val == 'L':
                # Verificar que el intercambio no rompa regla de descanso
                if (validar_transicion(df, max_pid, fecha, 'L') and
                    validar_transicion(df, min_pid, fecha, turno_max_val)):
                    # Realizar intercambio
                    df.loc[(df['persona_id'] == max_pid) & (df['fecha'] == fecha), 'turno'] = 'L'
                    df.loc[(df['persona_id'] == min_pid) & (df['fecha'] == fecha), 'turno'] = turno_max_val
                    # Actualizar cargas
                    carga[max_pid] -= 1
                    carga[min_pid] += 1
                    encontrado = True
                    break

        if not encontrado:
            # No se pudo mejorar más; salir del bucle
            break

    return df


def guardar_balanceo_en_bd(df: pd.DataFrame, año: int, mes: int) -> None:
    """
    Persiste en la base de datos los cambios realizados por el balanceo
    (solo actualiza los días especiales del mes para el Grupo A).
    """
    especiales = obtener_dias_especiales(año, mes)
    if not especiales:
        return

    with database.get_connection() as conn:
        for fecha in especiales:
            for pid in range(1, 7):  # Grupo A
                turno_series = df[(df['persona_id'] == pid) & (df['fecha'] == fecha)]['turno']
                if not turno_series.empty:
                    nuevo_turno = turno_series.iloc[0]
                    conn.execute(
                        "UPDATE calendario SET turno = ? WHERE persona_id = ? AND fecha = ?",
                        (nuevo_turno, pid, fecha)
                    )
        conn.commit()