"""
grupo_b.py
Módulo para la generación de calendarios del Grupo B (fijo).
Ahora lee la configuración de descansos desde la base de datos.
"""

import pandas as pd
import sys
import os
from datetime import date

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ciclos
import database

ID_B1 = 7
ID_B2 = 8

def generar_calendario_grupoB(año, mes, pais='CO'):
    """
    Genera un DataFrame con el calendario mensual para las 2 personas del Grupo B.
    Lee de la BD si B1 descansa sábados y si B2 descansa sábados.
    """
    dias = ciclos.generar_rango_fechas(año, mes)
    festivos = ciclos.obtener_festivos(año, pais)

    # Leer configuración
    config = database.obtener_configuracion()
    b1_descansa_sab = config['b1_descansa_sabados']
    b2_descansa_sab = config['b2_descansa_sabados']

    filas = []
    for fecha in dias:
        es_festivo = 1 if fecha in festivos else 0
        dia_semana = fecha.weekday()  # 0=lunes, 6=domingo

        # --- B1 ---
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

        # --- B2 ---
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

    df = pd.DataFrame(filas)
    return df

def guardar_calendario_grupoB_en_bd(df, año, mes):
    conn = database.get_db_connection()
    cursor = conn.cursor()
    fecha_like = f"{año}-{mes:02d}%"
    cursor.execute("DELETE FROM calendario WHERE fecha LIKE ? AND persona_id IN (?, ?)",
                   (fecha_like, ID_B1, ID_B2))
    df.to_sql('calendario', conn, if_exists='append', index=False)
    conn.commit()
    conn.close()
    print(f"✅ Calendario Grupo B de {mes}/{año} guardado.")

def resumen_cobertura_tarde(df, año, mes):
    print(f"\n📊 Cobertura en turno Tarde para {mes}/{año}:")
    for fecha in sorted(df['fecha'].unique()):
        sub = df[df['fecha'] == fecha]
        personas_t = sub[sub['turno'] == 'T']
        print(f"{fecha}: {len(personas_t)} persona(s) en T")
        if not personas_t.empty:
            ids = personas_t['persona_id'].tolist()
            nombres = ["B1" if i == ID_B1 else "B2" for i in ids]
            print(f"      ({', '.join(nombres)})")

if __name__ == "__main__":
    año = 2025
    mes = 3
    df = generar_calendario_grupoB(año, mes)
    print(df.head(10))
    resumen_cobertura_tarde(df, año, mes)