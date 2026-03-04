"""
app.py
Interfaz de usuario con Streamlit para el sistema SecureSchedule.
Versión final con soporte para ejecutable (lanzamiento automático del servidor).
"""

import streamlit as st
import pandas as pd
import sys
import os
from datetime import datetime, date
import calendar

# ------------------------------------------------------------
# Configuración de rutas para ejecutable
# ------------------------------------------------------------
if getattr(sys, 'frozen', False):
    # Modo ejecutable (PyInstaller)
    BASE_DIR = os.path.dirname(sys.executable)
else:
    # Modo desarrollo
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

OUTPUT_DIR = os.path.join(BASE_DIR, "output")
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Función para recursos empaquetados (logo)
def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# Agregar ruta para imports de src
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from src import database, ciclos, grupo_b, ausencias
from src.exportar import generar_excel_con_formato, generar_pdf_calendario

# Inicializar base de datos (crea las tablas si no existen)
database.init_db()

# ------------------------------------------------------------
# Configuración de página
# ------------------------------------------------------------
st.set_page_config(page_title="Tennis Scheduling Solutions", page_icon="📅", layout="wide")

# CSS personalizado (cursor pointer, márgenes, etc.)
st.markdown("""
<style>
    /* Cursor pointer en todos los elementos cliqueables */
    div[data-testid*="stSelectbox"] *,
    div[data-testid*="stRadio"] *,
    div[data-testid*="stCheckbox"] *,
    .stSelectbox *,
    .stRadio *,
    .stCheckbox *,
    [data-baseweb="select"] *,
    [data-testid="stBaseButton-primary"] * {
        cursor: pointer !important;
    }
    div[data-testid*="stSelectbox"],
    div[data-testid*="stRadio"],
    div[data-testid*="stCheckbox"],
    .stSelectbox,
    .stRadio,
    .stCheckbox {
        cursor: pointer;
    }
    /* Ajustes de espacio */
    .css-1lcbmhc {
        padding-top: 1rem;
    }
    .stButton button {
        margin-bottom: 0.2rem;
    }
    .stSelectbox, .stRadio {
        margin-bottom: 0.5rem;
    }
    /* Compactar inputs en expander de edición */
    .stExpander [data-testid="stTextInput"] input,
    .stExpander [data-testid="stSelectbox"] div[data-baseweb="select"] {
        padding-top: 0.2rem !important;
        padding-bottom: 0.2rem !important;
        font-size: 0.9rem !important;
    }
    .stExpander .stHorizontalBlock {
        margin-bottom: 0.2rem !important;
    }
    .stExpander [data-testid="stSelectbox"] {
        min-width: 60px;
    }
</style>
""", unsafe_allow_html=True)

# Colores de la paleta
COLOR_FONDO = "#ECF0F1"
COLOR_TEXTO = "#2C3E50"
COLOR_M = "#27AE60"
COLOR_T = "#F39C12"
COLOR_N = "#34495E"
COLOR_FESTIVO = "#E74C3C"
COLOR_AUSENCIA = "#E74C3C"

# ------------------------------------------------------------
# Funciones auxiliares
# ------------------------------------------------------------
def cargar_datos_mes(año, mes):
    conn = database.get_db_connection()
    query = """
        SELECT c.persona_id, p.nombre, p.grupo, p.subgrupo, c.fecha, c.turno, c.es_festivo
        FROM calendario c
        JOIN personas p ON c.persona_id = p.id
        WHERE c.fecha LIKE ?
        ORDER BY c.fecha, p.grupo, p.id
    """
    fecha_like = f"{año}-{mes:02d}%"
    df = pd.read_sql_query(query, conn, params=[fecha_like])
    conn.close()
    return df

def generar_calendario_completo(año, mes, ciclo, pais='CO'):
    with st.spinner("Generando calendario..."):
        dfA, offsets_finales = ciclos.generar_calendario_grupoA(año, mes, ciclo=ciclo, pais=pais)
        ciclos.guardar_calendario_en_bd(dfA, año, mes)
        ciclos.guardar_offsets(offsets_finales, año, mes, ciclo)

        dfB = grupo_b.generar_calendario_grupoB(año, mes, pais=pais)
        grupo_b.guardar_calendario_grupoB_en_bd(dfB, año, mes)

        st.success("Calendario generado y guardado correctamente.")

# ------------------------------------------------------------
# Sidebar
# ------------------------------------------------------------
with st.sidebar:
    st.image(resource_path("assets/logo.png"), width=200)
    st.title("⚙️ Configuración")

    # Selectores de año y mes en columnas
    col_a, col_m = st.columns(2)
    with col_a:
        año_actual = datetime.now().year
        años = list(range(año_actual - 1, año_actual + 5))
        año = st.selectbox("Año", options=años, index=1, key="select_año", label_visibility="collapsed")
    with col_m:
        mes_actual = datetime.now().month
        mes_actual_index = mes_actual - 1
        mes = st.selectbox("Mes", options=range(1, 13), format_func=lambda x: calendar.month_name[x],
                           index=mes_actual_index, key="select_mes", label_visibility="collapsed")

    ciclo = st.selectbox("Ciclo A", options=['2x2x2', '4x2'], key="select_ciclo")
    modo = st.radio("Modo", options=['normal', 'contingencia'], index=0, key="radio_modo", horizontal=True)

    if st.button("🔄 Generar/Actualizar", key="btn_generar", use_container_width=True):
        generar_calendario_completo(año, mes, ciclo)

    st.markdown("---")

    # --- Expander de personas ---
    with st.expander("👥 Personas"):
        personas = database.obtener_personas()
        st.markdown("""
        <style>
        div[data-testid="stExpander"] div[data-baseweb="select"] { min-width: 80px !important; }
        div[data-testid="stExpander"] div[data-testid="stTextInput"] input,
        div[data-testid="stExpander"] div[data-baseweb="select"] * { font-size: 13px !important; padding: 2px !important; }
        div[data-testid="stExpander"] .stButton button { font-size: 13px !important; padding: 2px 6px !important; }
        div[data-testid="stExpander"] .stHorizontalBlock { margin-bottom: 3px !important; gap: 3px !important; }
        </style>
        """, unsafe_allow_html=True)

        for p in personas:
            cols = st.columns([2.5, 1.0, 1.0, 0.6])
            with cols[0]:
                nuevo_nombre = st.text_input("Nombre", value=p['nombre'], key=f"nombre_{p['id']}",
                                             label_visibility="collapsed", placeholder="Nombre")
            with cols[1]:
                grupo_options = ['A', 'B']
                grupo_index = grupo_options.index(p['grupo']) if p['grupo'] in grupo_options else 0
                nuevo_grupo = st.selectbox("Grupo", options=grupo_options, index=grupo_index,
                                           key=f"grupo_{p['id']}", label_visibility="collapsed")
            with cols[2]:
                if nuevo_grupo == 'B':
                    subgrupo_options = ['B1', 'B2']
                    subgrupo_index = subgrupo_options.index(p['subgrupo']) if p['subgrupo'] in subgrupo_options else 0
                    nuevo_subgrupo = st.selectbox("Subgrupo", options=subgrupo_options, index=subgrupo_index,
                                                  key=f"subgrupo_{p['id']}", label_visibility="collapsed")
                else:
                    nuevo_subgrupo = None
                    st.empty()
            with cols[3]:
                if st.button("💾", key=f"btn_guardar_{p['id']}"):
                    database.actualizar_nombre(p['id'], nuevo_nombre)
                    if nuevo_grupo != p['grupo'] or nuevo_subgrupo != p['subgrupo']:
                        database.actualizar_grupo(p['id'], nuevo_grupo, nuevo_subgrupo)
                    st.success("✅")
                    st.rerun()

        st.markdown("---")
        config = database.obtener_configuracion()
        b1_desc = st.checkbox("B1 descansa sábados", value=config['b1_descansa_sabados'], key="chk_b1")
        b2_desc = st.checkbox("B2 descansa sábados", value=config['b2_descansa_sabados'], key="chk_b2")
        if st.button("Guardar Grupo B", key="btn_guardar_config", use_container_width=True):
            database.actualizar_configuracion(b1_descansa_sabados=b1_desc, b2_descansa_sabados=b2_desc)
            st.success("Configuración guardada.")
            st.rerun()

    # --- Expander de ausencias ---
    with st.expander("📅 Ausencias"):
        with st.container():
            st.markdown("**Registrar**")
            personas_dict = {p['id']: p['nombre'] for p in database.obtener_personas()}
            persona_id = st.selectbox("Persona", options=list(personas_dict.keys()), format_func=lambda x: personas_dict[x], key="select_persona_aus")
            fecha_inicio = st.date_input("Inicio", value=date(año, mes, 1), key="date_inicio")
            fecha_fin = st.date_input("Fin", value=date(año, mes, 1), key="date_fin")
            tipo = st.selectbox("Tipo", options=['V', 'PNR', 'IM', 'CD'], key="select_tipo")
            motivo = st.text_input("Motivo", key="txt_motivo")
            if st.button("Registrar", key="btn_registrar_aus", use_container_width=True):
                ausencias.registrar_ausencia(persona_id, fecha_inicio.isoformat(), fecha_fin.isoformat(), tipo, motivo)
                st.success("Ausencia registrada.")
                st.rerun()

        st.markdown("---")
        with st.container():
            st.markdown("**Listado**")
            ausencias_mes = ausencias.obtener_ausencias(mes=mes, año=año)
            if ausencias_mes:
                for aus in ausencias_mes:
                    st.text(f"ID {aus['id']}: Pers.{aus['persona_id']} {aus['fecha_inicio'][5:]}→{aus['fecha_fin'][5:]} ({aus['tipo']})")
                    if st.button(f"Eliminar {aus['id']}", key=f"btn_eliminar_{aus['id']}"):
                        ausencias.eliminar_ausencia(aus['id'])
                        st.success("Eliminada.")
                        st.rerun()
            else:
                st.info("No hay ausencias")

    # --- Exportación con descarga directa ---
    with st.expander("📤 Exportar"):
        col1, col2 = st.columns(2)
        with col1:
            df = cargar_datos_mes(año, mes)
            if not df.empty:
                # Generar Excel en memoria
                output_path_excel = os.path.join(OUTPUT_DIR, f"calendario_{año}_{mes:02d}.xlsx")
                os.makedirs(OUTPUT_DIR, exist_ok=True)
                generar_excel_con_formato(df, año, mes, ciclo, output_path_excel)
                with open(output_path_excel, "rb") as file:
                    st.download_button(
                        label="📥 Excel",
                        data=file,
                        file_name=f"calendario_{año}_{mes:02d}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="btn_excel",
                        use_container_width=True
                    )
            else:
                st.button("📥 Excel", disabled=True, key="btn_excel_disabled", use_container_width=True)
                st.warning("Sin datos")

        with col2:
            df = cargar_datos_mes(año, mes)
            if not df.empty:
                output_path_pdf = os.path.join(OUTPUT_DIR, f"calendario_{año}_{mes:02d}.pdf")
                os.makedirs(OUTPUT_DIR, exist_ok=True)
                generar_pdf_calendario(df, año, mes, ciclo, output_path_pdf)
                with open(output_path_pdf, "rb") as file:
                    st.download_button(
                        label="📄 PDF",
                        data=file,
                        file_name=f"calendario_{año}_{mes:02d}.pdf",
                        mime="application/pdf",
                        key="btn_pdf",
                        use_container_width=True
                    )
            else:
                st.button("📄 PDF", disabled=True, key="btn_pdf_disabled", use_container_width=True)
                st.warning("Sin datos")
                
    # --- Info colores ---
    with st.expander("🎨 Colores"):
        st.markdown("""
        - 🟢 Mañana (M)
        - 🟡 Tarde (T)
        - 🔵 Noche (N)
        - 🔴 Festivos/Domingos/Ausencias
        """)

# ------------------------------------------------------------
# Cuerpo principal
# ------------------------------------------------------------
st.title("📅 Tennis Scheduling Solutions")
st.markdown(f"#### {calendar.month_name[mes]} {año} - Ciclo {ciclo} - Modo {modo}")

df = cargar_datos_mes(año, mes)

if df.empty:
    st.warning("No hay calendario generado para este mes. Usa el botón en la barra lateral para generar uno.")
else:
    if modo == 'contingencia':
        with st.spinner("Aplicando lógica de contingencia..."):
            resultado = ausencias.aplicar_contingencia(año, mes)
            if resultado[0] is None:
                st.error("Error al aplicar contingencia.")
                st.stop()
            df, _ = resultado
            st.success("Contingencia aplicada correctamente.")
            df = cargar_datos_mes(año, mes)

    personas = df['nombre'].unique()
    dias = sorted(df['fecha'].unique())

    pivot_data = []
    for persona in personas:
        persona_df = df[df['nombre'] == persona]
        fila = {'Persona': persona}
        for dia in dias:
            turno = persona_df[persona_df['fecha'] == dia]['turno'].values
            fila[dia] = turno[0] if len(turno) > 0 else ''
        pivot_data.append(fila)
    pivot_df = pd.DataFrame(pivot_data)
    pivot_df.set_index('Persona', inplace=True)

    festivos_por_dia = df.groupby('fecha')['es_festivo'].max().to_dict()

    def colorear_celda(val, fecha):
        if pd.isna(val) or val == '':
            return ''
        es_festivo = festivos_por_dia.get(fecha, 0)
        if es_festivo:
            return f"background-color: {COLOR_FESTIVO}; color: white; font-weight: bold"
        if val == 'M':
            return f"background-color: {COLOR_M}; color: white"
        elif val == 'T':
            return f"background-color: {COLOR_T}; color: white"
        elif val == 'N':
            return f"background-color: {COLOR_N}; color: white"
        elif val in ('V', 'PNR', 'IM', 'CD'):
            return f"background-color: {COLOR_AUSENCIA}; color: white; font-weight: bold"
        else:
            return ''

    dias_es = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']
    html = "<table style='border-collapse: collapse; width: 100%; font-size: 12px;'>"
    html += "<tr><th style='background-color: #2C3E50; color: white; padding: 5px;'>Persona</th>"
    for dia in dias:
        fecha_obj = datetime.strptime(dia, "%Y-%m-%d").date()
        es_festivo = festivos_por_dia.get(dia, 0)
        dia_semana = fecha_obj.weekday()
        nombre_dia = dias_es[dia_semana]
        estilo_th = f"background-color: {COLOR_FESTIVO if (es_festivo or dia_semana==6) else '#2C3E50'}; color: white; padding: 5px; text-align: center;"
        html += f"<th style='{estilo_th}'>{nombre_dia}<br>{fecha_obj.day}</th>"
    html += "</tr>"

    for idx, row in pivot_df.iterrows():
        html += "<tr>"
        html += f"<td style='background-color: #2C3E50; color: white; padding: 5px; font-weight: bold; white-space: nowrap; min-width: 150px;'>{idx}</td>"
        for dia in dias:
            val = row[dia]
            estilo = colorear_celda(val, dia)
            html += f"<td style='{estilo} padding: 5px; text-align: center; border: 1px solid #ddd;'>{val}</td>"
        html += "</tr>"
    html += "</table>"
    st.markdown(html, unsafe_allow_html=True)

    # Estadísticas
    st.subheader("Resumen de cobertura")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total personas", len(personas))
    with col2:
        df_a = df[df['grupo'] == 'A']
        dias_completos = 0
        for dia in dias:
            dia_a = df_a[df_a['fecha'] == dia]
            if len(dia_a[dia_a['turno'] == 'M']) == 2 and len(dia_a[dia_a['turno'] == 'N']) == 2:
                dias_completos += 1
        st.metric("Días cobertura A completa", f"{dias_completos}/{len(dias)}")
    with col3:
        df_b = df[df['grupo'] == 'B']
        st.metric("Personas Grupo B", len(df_b['persona_id'].unique()))

    st.markdown("---")
    st.markdown("**Leyenda:** 🟢 M = Mañana, 🟡 T = Tarde, 🔵 N = Noche, 🔴 Festivo/Domingo, 🔴 V/PNR/IM/CD = Ausencia")

# ------------------------------------------------------------
# Footer
# ------------------------------------------------------------
st.markdown("---")
st.markdown(
    "<div style='text-align: left;'> © 2026 Dairo García. Licencia MIT. Desarrollado para Tennis S.A.</div>",
    unsafe_allow_html=True
)

# ------------------------------------------------------------
# Lanzamiento del servidor (solo para ejecutable)
# ------------------------------------------------------------
if getattr(sys, 'frozen', False):
    base_path = sys._MEIPASS
    script_path = os.path.join(base_path, "app.py")
    sys.argv = ["streamlit", "run", script_path]   # sin --server.headless
else:
    sys.argv = ["streamlit", "run", sys.argv[0]]