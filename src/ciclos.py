"""
ciclos.py
Generación de calendarios rotativos para Grupo A.
"""

import random
import pandas as pd
import holidays
from datetime import date, timedelta
from typing import List, Tuple, Optional

from . import database  # <--- CAMBIO: importación relativa

# ------------------------------------------------------------
# Constantes
# ------------------------------------------------------------
NUM_PERSONAS_A = 6
CICLO_2X2X2 = "2x2x2"
CICLO_4X2 = "4x2"
PATRON_2X2X2 = ['M', 'M', 'N', 'N', 'L', 'L']
PATRON_4X2 = ['M', 'M', 'M', 'M', 'L', 'L', 'N', 'N', 'N', 'N', 'L', 'L']

# ------------------------------------------------------------
# Festivos
# ------------------------------------------------------------
def obtener_festivos(año: int, pais: str = 'CO') -> set:
    """Retorna un set de fechas festivas del año."""
    return set(holidays.CountryHoliday(pais, years=año).keys())

def generar_rango_fechas(año: int, mes: int) -> List[date]:
    """Genera lista de objetos date para todos los días del mes."""
    inicio = date(año, mes, 1)
    if mes == 12:
        fin = date(año + 1, 1, 1) - timedelta(days=1)
    else:
        fin = date(año, mes + 1, 1) - timedelta(days=1)
    return [inicio + timedelta(days=i) for i in range((fin - inicio).days + 1)]

# ------------------------------------------------------------
# Offsets en BD
# ------------------------------------------------------------
def guardar_offsets(offsets: List[int], año: int, mes: int, ciclo: str) -> None:
    """Guarda los offsets finales de cada persona del Grupo A."""
    with database.get_connection() as conn:
        for persona_id, offset in enumerate(offsets, start=1):
            conn.execute("""
                INSERT OR REPLACE INTO estado_ciclo (persona_id, año, mes, offset, ciclo)
                VALUES (?, ?, ?, ?, ?)
            """, (persona_id, año, mes, offset, ciclo))
        conn.commit()

def cargar_offsets(año: int, mes: int) -> Tuple[Optional[List[int]], Optional[str]]:
    """Carga los offsets del mes anterior (si existen). Retorna (offsets, ciclo_anterior)."""
    if mes == 1:
        año_ant, mes_ant = año - 1, 12
    else:
        año_ant, mes_ant = año, mes - 1

    with database.get_connection() as conn:
        cursor = conn.execute("""
            SELECT persona_id, offset, ciclo
            FROM estado_ciclo
            WHERE año = ? AND mes = ?
            ORDER BY persona_id
        """, (año_ant, mes_ant))
        filas = cursor.fetchall()

    if len(filas) != NUM_PERSONAS_A:
        return None, None
    offsets = [f[1] for f in filas]
    ciclo_ant = filas[0][2] if filas else None
    return offsets, ciclo_ant

# ------------------------------------------------------------
# Ciclos
# ------------------------------------------------------------
def ciclo_2x2x2(dias: List[date], offsets_iniciales: List[int]) -> Tuple[List[List[str]], List[int]]:
    """Genera turnos con ciclo 2x2x2."""
    periodo = len(PATRON_2X2X2)
    turnos_por_persona = []
    offsets_finales = []
    for p in range(NUM_PERSONAS_A):
        offset = offsets_iniciales[p]
        turnos = []
        for i in range(len(dias)):
            idx = (i + offset) % periodo
            turnos.append(PATRON_2X2X2[idx])
        turnos_por_persona.append(turnos)
        offsets_finales.append((offset + len(dias)) % periodo)
    return turnos_por_persona, offsets_finales

def ciclo_4x2(dias: List[date], offsets_iniciales: List[int]) -> Tuple[List[List[str]], List[int]]:
    """Genera turnos con ciclo 4x2."""
    periodo = len(PATRON_4X2)
    turnos_por_persona = []
    offsets_finales = []
    for p in range(NUM_PERSONAS_A):
        offset = offsets_iniciales[p]
        turnos = []
        for i in range(len(dias)):
            idx = (i + offset) % periodo
            turnos.append(PATRON_4X2[idx])
        turnos_por_persona.append(turnos)
        offsets_finales.append((offset + len(dias)) % periodo)
    return turnos_por_persona, offsets_finales

def verificar_regla_descanso(turnos_por_persona: List[List[str]], dias: List[date]) -> List[str]:
    """Verifica que no haya N → M sin Libre intermedio."""
    advertencias = []
    for p, turnos in enumerate(turnos_por_persona):
        for i in range(len(turnos) - 1):
            if turnos[i] == 'N' and turnos[i+1] == 'M':
                advertencias.append(
                    f"Persona {p+1}: {dias[i]} N → {dias[i+1]} M"
                )
    return advertencias

# ------------------------------------------------------------
# Generador principal
# ------------------------------------------------------------
def generar_calendario_grupoA(
    año: int,
    mes: int,
    ciclo: str = CICLO_2X2X2,
    pais: str = 'CO',
    offsets_iniciales: Optional[List[int]] = None
) -> Tuple[pd.DataFrame, List[int]]:
    """
    Genera DataFrame con calendario del Grupo A.
    Si offsets_iniciales es None, intenta cargar desde mes anterior.
    """
    dias = generar_rango_fechas(año, mes)

    # Determinar offsets iniciales
    if offsets_iniciales is None:
        offsets_cargados, ciclo_ant = cargar_offsets(año, mes)
        if offsets_cargados is not None and ciclo_ant == ciclo:
            offsets_iniciales = offsets_cargados
        else:
            # Usar offsets por defecto del ciclo
            if ciclo == CICLO_2X2X2:
                offsets_iniciales = list(range(NUM_PERSONAS_A))
            elif ciclo == CICLO_4X2:
                offsets_iniciales = [i * 2 for i in range(NUM_PERSONAS_A)]
            else:
                raise ValueError("Ciclo no válido")

    # Generar según ciclo
    if ciclo == CICLO_2X2X2:
        turnos_por_persona, offsets_finales = ciclo_2x2x2(dias, offsets_iniciales)
    elif ciclo == CICLO_4X2:
        turnos_por_persona, offsets_finales = ciclo_4x2(dias, offsets_iniciales)
    else:
        raise ValueError("Ciclo no válido. Use '2x2x2' o '4x2'.")

    # Verificar regla de descanso
    advertencias = verificar_regla_descanso(turnos_por_persona, dias)
    if advertencias:
        print("⚠️ Posibles violaciones a RF-02:")
        for adv in advertencias:
            print(f"   {adv}")

    # Obtener festivos
    festivos = obtener_festivos(año, pais)

    # Construir DataFrame
    filas = []
    for p in range(NUM_PERSONAS_A):
        persona_id = p + 1
        for i, fecha in enumerate(dias):
            filas.append({
                'persona_id': persona_id,
                'fecha': fecha.isoformat(),
                'turno': turnos_por_persona[p][i],
                'es_festivo': 1 if fecha in festivos else 0
            })
    df = pd.DataFrame(filas)
    return df, offsets_finales

def guardar_calendario_en_bd(df: pd.DataFrame, año: int, mes: int) -> None:
    """Inserta el DataFrame en la tabla calendario (reemplazando el mes)."""
    with database.get_connection() as conn:
        fecha_like = f"{año}-{mes:02d}%"
        conn.execute("DELETE FROM calendario WHERE fecha LIKE ?", (fecha_like,))
        df.to_sql('calendario', conn, if_exists='append', index=False)
        conn.commit()

# ------------------------------------------------------------
# Alternativas
# ------------------------------------------------------------
def generar_variantes_offsets(
    ciclo: str,
    num_variantes: int = 7,
    semilla_base: int = 42
) -> List[List[int]]:
    """
    Genera múltiples conjuntos de offsets iniciales para el Grupo A.
    Cada conjunto es una permutación de los offsets base del ciclo.
    """
    if ciclo == CICLO_2X2X2:
        offsets_base = list(range(6))  # [0,1,2,3,4,5]
    elif ciclo == CICLO_4X2:
        offsets_base = [i * 2 for i in range(6)]  # [0,2,4,6,8,10]
    else:
        raise ValueError(f"Ciclo no soportado: {ciclo}")

    variantes = []
    for v in range(num_variantes):
        rng = random.Random(semilla_base + v)
        offsets_permutados = offsets_base[:]
        rng.shuffle(offsets_permutados)
        variantes.append(offsets_permutados)
    return variantes