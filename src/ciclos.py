"""
ciclos.py
Módulo para la generación de calendarios del Grupo A (rotativo).
Implementa los ciclos 2x2x2 y 4x2, con continuidad entre meses y
detección de cambio de ciclo para mantener 2 personas por turno siempre.
"""

import pandas as pd
import holidays
from datetime import date, timedelta
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import database

# ------------------------------------------------------------
# Funciones auxiliares
# ------------------------------------------------------------

def obtener_festivos(año, pais='CO'):
    """Devuelve un set de objetos date con los festivos del año."""
    co_holidays = holidays.CountryHoliday(pais, years=año)
    return set(co_holidays.keys())

def generar_rango_fechas(año, mes):
    """Genera una lista de objetos date para todos los días del mes."""
    inicio = date(año, mes, 1)
    if mes == 12:
        fin = date(año + 1, 1, 1) - timedelta(days=1)
    else:
        fin = date(año, mes + 1, 1) - timedelta(days=1)
    dias = []
    dia_actual = inicio
    while dia_actual <= fin:
        dias.append(dia_actual)
        dia_actual += timedelta(days=1)
    return dias

# ------------------------------------------------------------
# Gestión de offsets en BD
# ------------------------------------------------------------

def guardar_offsets(offsets, año, mes, ciclo):
    """
    Guarda los offsets finales de cada persona para el mes dado.
    offsets: lista de 6 enteros.
    """
    conn = database.get_db_connection()
    cursor = conn.cursor()
    for persona_id, offset in enumerate(offsets, start=1):
        cursor.execute("""
            INSERT OR REPLACE INTO estado_ciclo (persona_id, año, mes, offset, ciclo)
            VALUES (?, ?, ?, ?, ?)
        """, (persona_id, año, mes, offset, ciclo))
    conn.commit()
    conn.close()

def cargar_offsets(año, mes):
    """
    Carga los offsets iniciales para el mes actual a partir del mes anterior.
    Retorna (offsets, ciclo_anterior) o (None, None) si no existe.
    """
    if mes == 1:
        año_ant = año - 1
        mes_ant = 12
    else:
        año_ant = año
        mes_ant = mes - 1

    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT persona_id, offset, ciclo
        FROM estado_ciclo
        WHERE año = ? AND mes = ?
        ORDER BY persona_id
    """, (año_ant, mes_ant))
    filas = cursor.fetchall()
    conn.close()

    if len(filas) != 6:
        return None, None
    offsets = [f[1] for f in filas]
    ciclo_anterior = filas[0][2] if filas else None
    return offsets, ciclo_anterior

# ------------------------------------------------------------
# Generación de ciclos
# ------------------------------------------------------------

def ciclo_2x2x2(dias, offsets_iniciales=None, num_personas=6):
    """
    Ciclo 2x2x2: patrón [M,M,N,N,L,L] de 6 días.
    Offsets por defecto: [0,1,2,3,4,5] (garantiza 2 personas por turno).
    """
    patron = ['M', 'M', 'N', 'N', 'L', 'L']
    if offsets_iniciales is None:
        offsets_iniciales = list(range(num_personas))
    turnos_por_persona = []
    offsets_finales = []
    for p in range(num_personas):
        offset = offsets_iniciales[p]
        turnos = []
        for i in range(len(dias)):
            idx = (i + offset) % len(patron)
            turnos.append(patron[idx])
        turnos_por_persona.append(turnos)
        offsets_finales.append((offset + len(dias)) % len(patron))
    return turnos_por_persona, offsets_finales

def ciclo_4x2(dias, offsets_iniciales=None, num_personas=6):
    """
    Ciclo 4x2: patrón [M,M,M,M, L,L, N,N,N,N, L,L] de 12 días.
    Offsets por defecto: [0,2,4,6,8,10] (garantiza 2 personas por turno).
    """
    patron = ['M', 'M', 'M', 'M', 'L', 'L', 'N', 'N', 'N', 'N', 'L', 'L']
    if offsets_iniciales is None:
        offsets_iniciales = [i * 2 for i in range(num_personas)]  # [0,2,4,6,8,10]
    turnos_por_persona = []
    offsets_finales = []
    for p in range(num_personas):
        offset = offsets_iniciales[p]
        turnos = []
        for i in range(len(dias)):
            idx = (i + offset) % len(patron)
            turnos.append(patron[idx])
        turnos_por_persona.append(turnos)
        offsets_finales.append((offset + len(dias)) % len(patron))
    return turnos_por_persona, offsets_finales

def verificar_regla_descanso(turnos_por_persona, dias):
    """
    RF-02: Verifica que no haya transición Noche -> Mañana sin Libre intermedio.
    """
    advertencias = []
    for p, turnos in enumerate(turnos_por_persona):
        for i in range(len(turnos)-1):
            if turnos[i] == 'N' and turnos[i+1] == 'M':
                advertencias.append(
                    f"Persona {p+1}: {dias[i]} N → {dias[i+1]} M"
                )
    return advertencias

# ------------------------------------------------------------
# Función principal
# ------------------------------------------------------------

def generar_calendario_grupoA(año, mes, ciclo='2x2x2', pais='CO', offsets_iniciales=None):
    """
    Genera DataFrame y offsets finales.
    Si offsets_iniciales es None, intenta cargar desde mes anterior.
    Si hay cambio de ciclo, se ignoran los offsets cargados y se usan los por defecto.
    """
    dias = generar_rango_fechas(año, mes)
    num_personas = 6

    # Determinar offsets iniciales
    if offsets_iniciales is None:
        offsets_cargados, ciclo_ant = cargar_offsets(año, mes)
        if offsets_cargados is not None:
            if ciclo_ant == ciclo:
                offsets_iniciales = offsets_cargados
                print(f"Usando offsets del mes anterior (mismo ciclo: {ciclo})")
            else:
                print(f"Cambio de ciclo detectado: {ciclo_ant} → {ciclo}. Usando offsets por defecto.")
                # No asignamos offsets_iniciales, cada ciclo usará su default
        else:
            print("No hay mes anterior, usando offsets por defecto del ciclo.")

    # Generar según ciclo
    if ciclo == '2x2x2':
        turnos_por_persona, offsets_finales = ciclo_2x2x2(dias, offsets_iniciales, num_personas)
    elif ciclo == '4x2':
        turnos_por_persona, offsets_finales = ciclo_4x2(dias, offsets_iniciales, num_personas)
    else:
        raise ValueError("Ciclo no válido. Use '2x2x2' o '4x2'.")

    # Verificar RF-02
    advertencias = verificar_regla_descanso(turnos_por_persona, dias)
    if advertencias:
        print("⚠️  Se detectaron posibles violaciones a RF-02:")
        for adv in advertencias:
            print(f"   {adv}")

    # Obtener festivos
    festivos = obtener_festivos(año, pais)

    # Construir DataFrame
    filas = []
    for p in range(num_personas):
        persona_id = p + 1  # IDs 1..6
        for i, fecha in enumerate(dias):
            filas.append({
                'persona_id': persona_id,
                'fecha': fecha.isoformat(),
                'turno': turnos_por_persona[p][i],
                'es_festivo': 1 if fecha in festivos else 0
            })

    df = pd.DataFrame(filas)
    return df, offsets_finales

def guardar_calendario_en_bd(df, año, mes):
    """
    Inserta el DataFrame en la tabla calendario, reemplazando registros existentes.
    """
    conn = database.get_db_connection()
    cursor = conn.cursor()
    fecha_like = f"{año}-{mes:02d}%"
    cursor.execute("DELETE FROM calendario WHERE fecha LIKE ?", (fecha_like,))
    df.to_sql('calendario', conn, if_exists='append', index=False)
    conn.commit()
    conn.close()
    print(f"✅ Calendario Grupo A de {mes}/{año} guardado en base de datos.")