"""
grupo_b.py
Generación de calendario fijo para Grupo B.
"""

import pandas as pd
from datetime import date

from . import ciclos
from . import database

# ------------------------------------------------------------
# Constantes
# ------------------------------------------------------------
ID_B1 = 7
ID_B2 = 8

def generar_calendario_grupoB(año: int, mes: int, pais: str = 'CO') -> pd.DataFrame:
    """Genera DataFrame con calendario de Grupo B."""
    dias = ciclos.generar_rango_fechas(año, mes)
    festivos = ciclos.obtener_festivos(año, pais)

    config = database.obtener_configuracion()
    b1_descansa_sab = config['b1_descansa_sabados']
    b2_descansa_sab = config['b2_descansa_sabados']

    filas = []
    for fecha in dias:
        es_festivo = 1 if fecha in festivos else 0
        dia_semana = fecha.weekday()

        # B1
        if dia_semana == 6 or es_festivo or (dia_semana == 5 and b1_descansa_sab):
            turno_b1 = 'L'
        else:
            turno_b1 = 'T'
        filas.append({
            'persona_id': ID_B1,
            'fecha': fecha.isoformat(),
            'turno': turno_b1,
            'es_festivo': es_festivo
        })

        # B2
        if dia_semana == 6 or es_festivo or (dia_semana == 5 and b2_descansa_sab):
            turno_b2 = 'L'
        else:
            turno_b2 = 'T'
        filas.append({
            'persona_id': ID_B2,
            'fecha': fecha.isoformat(),
            'turno': turno_b2,
            'es_festivo': es_festivo
        })

    return pd.DataFrame(filas)

def guardar_calendario_grupoB_en_bd(df: pd.DataFrame, año: int, mes: int) -> None:
    """Guarda calendario Grupo B en la base de datos."""
    with database.get_connection() as conn:
        fecha_like = f"{año}-{mes:02d}%"
        conn.execute("DELETE FROM calendario WHERE fecha LIKE ? AND persona_id IN (?, ?)",
                     (fecha_like, ID_B1, ID_B2))
        df.to_sql('calendario', conn, if_exists='append', index=False)
        conn.commit()