"""
app.py
Interfaz de usuario con Streamlit – Versión optimizada.
"""

import streamlit as st
import pandas as pd
import sys
import os
from datetime import datetime, date
import calendar
import logging

from src import database, ciclos, grupo_b, ausencias, balanceo
from src.exportar import generar_excel_con_formato, generar_pdf_calendario

# ------------------------------------------------------------
# Configuración de página (DEBE ser lo primero)
# ------------------------------------------------------------
st.set_page_config(page_title="Tennis Scheduling Solutions", page_icon="📅", layout="wide")

# ------------------------------------------------------------
# CSS personalizado (cursor tipo mano en controles)
# ------------------------------------------------------------
st.markdown("""
<style>
    /* Cursor tipo mano en todos los controles interactivos */
    div[data-testid*="stSelectbox"] *,
    div[data-testid*="stRadio"] *,
    div[data-testid*="stCheckbox"] *,
    .stSelectbox *,
    .stRadio *,
    .stCheckbox *,
    [data-baseweb="select"] *,
    [data-testid="stBaseButton-primary"] *,
    /* Asegurar también dentro del formulario de configuración */
    div[data-testid="stForm"] div[data-testid="stSelectbox"] *,
    div[data-testid="stForm"] div[data-testid="stRadio"] * {
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
    .css-1lcbmhc { padding-top: 1rem; }
    .stButton button { margin-bottom: 0.2rem; }
    .stSelectbox, .stRadio { margin-bottom: 0.5rem; }
    .stExpander [data-testid="stTextInput"] input,
    .stExpander [data-testid="stSelectbox"] div[data-baseweb="select"] {
        padding-top: 0.2rem !important;
        padding-bottom: 0.2rem !important;
        font-size: 0.9rem !important;
    }
    .stExpander .stHorizontalBlock { margin-bottom: 0.2rem !important; }
    .stExpander [data-testid="stSelectbox"] { min-width: 60px; }
</style>
""", unsafe_allow_html=True)

# ------------------------------------------------------------
# Configuración de rutas y recursos
# ------------------------------------------------------------
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

OUTPUT_DIR = os.path.join(BASE_DIR, "output")
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

def resource_path(relative_path: str) -> str:
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# Inicializar BD y configurar logging
database.init_db()
logging.basicConfig(level=logging.INFO)

# ------------------------------------------------------------
# Colores de la paleta
# ------------------------------------------------------------
COLOR_M = "#27AE60"
COLOR_T = "#F39C12"
COLOR_N = "#34495E"
COLOR_FESTIVO = "#E74C3C"

# ------------------------------------------------------------
# Funciones auxiliares de UI
# ------------------------------------------------------------
def cargar_datos_mes(año: int, mes: int) -> pd.DataFrame:
    """Carga el calendario de un mes desde la base de datos."""
    conn = database.get_connection()
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

def generar_calendario_completo(año: int, mes: int, ciclo: str, pais: str = 'CO', balancear: bool = False) -> pd.DataFrame:
    """
    Genera el calendario completo (Grupo A + Grupo B), lo guarda en BD y retorna el DataFrame resultante.
    Si balancear es True, aplica el balanceo después de guardar.
    """
    with st.spinner("Generando calendario..."):
        # Grupo A
        dfA, offsets_finales = ciclos.generar_calendario_grupoA(año, mes, ciclo=ciclo, pais=pais)
        ciclos.guardar_calendario_en_bd(dfA, año, mes)
        ciclos.guardar_offsets(offsets_finales, año, mes, ciclo)

        # Grupo B
        dfB = grupo_b.generar_calendario_grupoB(año, mes, pais=pais)
        grupo_b.guardar_calendario_grupoB_en_bd(dfB, año, mes)

        # Obtener el calendario combinado recién guardado
        df_completo = ausencias.obtener_calendario_mes(año, mes)

        if balancear:
            try:
                df_balanceado = balanceo.aplicar_balanceo(df_completo, año, mes)
                balanceo.guardar_balanceo_en_bd(df_balanceado, año, mes)
                df_completo = df_balanceado
            except Exception as e:
                logging.warning(f"[balanceo] Error no crítico al balancear calendario normal ({año}-{mes:02d}): {e}")
        return df_completo

def mostrar_calendario_html(df: pd.DataFrame, año: int, mes: int) -> None:
    """Muestra el calendario en formato HTML con los colores definidos."""

    # ------------------------------------------------------------------
    # 1. Asegurar que existe la columna 'nombre'
    # ------------------------------------------------------------------
    if 'nombre' not in df.columns:
        # Obtener los nombres desde la tabla personas
        personas = database.obtener_personas()
        df_nombres = pd.DataFrame(personas)[['id', 'nombre']]
        # Unir con df usando persona_id
        df = df.merge(df_nombres, left_on='persona_id', right_on='id', how='left')
        # Eliminar la columna 'id' sobrante
        df = df.drop(columns=['id'], errors='ignore')
        # Si después del merge aún no hay 'nombre', abortar
        if 'nombre' not in df.columns:
            st.error("No se puede mostrar el calendario: faltan los nombres.")
            return

    # ------------------------------------------------------------------
    # 2. Construcción de la tabla HTML (código original)
    # ------------------------------------------------------------------
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
    pivot_df = pd.DataFrame(pivot_data).set_index('Persona')

    festivos_por_dia = df.groupby('fecha')['es_festivo'].max().to_dict()

    def colorear_celda(val: str, fecha: str) -> str:
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
            return f"background-color: {COLOR_FESTIVO}; color: white; font-weight: bold"
        return ''

    dias_es = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']
    html = "<table style='border-collapse: collapse; width: 100%; font-size: 12px;'>"
    html += "<thead><th style='background-color: #2C3E50; color: white; padding: 5px;'>Persona</th>"
    for dia in dias:
        fecha_obj = datetime.strptime(dia, "%Y-%m-%d").date()
        es_festivo = festivos_por_dia.get(dia, 0)
        dia_semana = fecha_obj.weekday()
        nombre_dia = dias_es[dia_semana]
        estilo_th = f"background-color: {COLOR_FESTIVO if (es_festivo or dia_semana==6) else '#2C3E50'}; color: white; padding: 5px; text-align: center;"
        html += f"<th style='{estilo_th}'>{nombre_dia}<br>{fecha_obj.day}</th>"
    html += "</thead><tbody>"

    for idx, row in pivot_df.iterrows():
        html += "<tr>"
        html += f"<td style='background-color: #2C3E50; color: white; padding: 5px; font-weight: bold; white-space: nowrap; min-width: 150px;'>{idx}</td>"
        for dia in dias:
            val = row[dia]
            estilo = colorear_celda(val, dia)
            html += f"<td style='{estilo} padding: 5px; text-align: center; border: 1px solid #ddd;'>{val}</td>"
        html += "</tr>"
    html += "</tbody></table>"

    st.markdown(html, unsafe_allow_html=True)

@st.cache_data(ttl=3600, show_spinner=False)
def generar_alternativas(año, mes, ciclo, pais, num_alternativas=7, modo='normal'):
    """Genera alternativas de calendario con diferentes offsets y aplica balanceo."""
    variantes_offsets = ciclos.generar_variantes_offsets(ciclo, num_alternativas)

    alternativas = []
    personas = database.obtener_personas()
    grupo_map = {p['id']: p['grupo'] for p in personas}
    nombre_map = {p['id']: p['nombre'] for p in personas}

    for offsets in variantes_offsets:
        dfA, final_offsets = ciclos.generar_calendario_grupoA(año, mes, ciclo=ciclo, pais=pais, offsets_iniciales=offsets)
        dfB = grupo_b.generar_calendario_grupoB(año, mes, pais=pais)
        df_combinado = pd.concat([dfA, dfB], ignore_index=True)
        df_combinado['grupo'] = df_combinado['persona_id'].map(grupo_map)
        df_combinado['nombre'] = df_combinado['persona_id'].map(nombre_map)

        if modo == 'contingencia':
            df_mostrar, _ = ausencias.aplicar_contingencia_a_df(df_combinado, año, mes, pais)
        else:
            df_mostrar = df_combinado

        # Aplicar balanceo (no crítico)
        try:
            df_mostrar = balanceo.aplicar_balanceo(df_mostrar, año, mes)
        except Exception as e:
            logging.warning(f"[balanceo] Error en alternativas: {e}")

        alternativas.append({
            'df': df_mostrar,
            'offsets': offsets,
            'final_offsets': final_offsets
        })
    return alternativas

# ------------------------------------------------------------
# Inicialización del estado de sesión
# ------------------------------------------------------------
def init_session_state():
    """Inicializa las variables de sesión necesarias."""
    if 'config' not in st.session_state:
        # Valores por defecto
        config = database.obtener_configuracion()
        st.session_state.config = config
        st.session_state.año = datetime.now().year
        st.session_state.mes = datetime.now().month
        st.session_state.ciclo = config['ciclo_default']
        st.session_state.modo = 'normal'   # 'normal' o 'contingencia'
        st.session_state.calendario_actual = None
        st.session_state.alternativas = None

init_session_state()

# ------------------------------------------------------------
# Sidebar con formulario y grupos lógicos
# ------------------------------------------------------------
with st.sidebar:
    st.image(resource_path("assets/logo.png"), width=200)
    st.title("⚙️ Configuración")

    # Formulario para los parámetros principales (evita re-ejecuciones al cambiar)
    with st.form("config_form"):
        col1, col2 = st.columns(2)
        with col1:
            año_actual = datetime.now().year
            años = list(range(año_actual - 1, año_actual + 5))
            año = st.selectbox("Año", options=años, index=años.index(st.session_state.año) if st.session_state.año in años else 1)
        with col2:
            meses = list(range(1, 13))
            mes = st.selectbox("Mes", options=meses, format_func=lambda x: calendar.month_name[x], index=st.session_state.mes - 1)

        ciclo = st.selectbox("Rotación (Grupo A)", options=['2x2x2', '4x2'], index=0 if st.session_state.ciclo == '2x2x2' else 1)
        modo = st.radio("Modo", options=['normal', 'contingencia'], index=0 if st.session_state.modo == 'normal' else 1, horizontal=True,
                        format_func=lambda x: "Estándar" if x == 'normal' else "Con ausencias")

        submitted = st.form_submit_button("📅 Generar calendario", use_container_width=True)

    if submitted:
        # Actualizar estado con los nuevos valores
        st.session_state.año = año
        st.session_state.mes = mes
        st.session_state.ciclo = ciclo
        st.session_state.modo = modo

        # Generar el calendario según el modo
        with st.spinner("Generando calendario..."):
            if modo == 'normal':
                # Modo normal: generar y balancear automáticamente
                df = generar_calendario_completo(año, mes, ciclo, st.session_state.config['pais'], balancear=True)
                st.session_state.calendario_actual = df
                st.session_state.alternativas = None
                st.toast("Calendario generado correctamente", icon="✅")
            else:  # contingencia
                # Primero generar el calendario base sin balanceo (se balanceará dentro de aplicar_contingencia)
                df_base = generar_calendario_completo(año, mes, ciclo, st.session_state.config['pais'], balancear=False)
                # Aplicar contingencia (esto incluye balanceo)
                with st.spinner("Aplicando contingencia..."):
                    df_final, acciones = ausencias.aplicar_contingencia(año, mes)
                    if df_final is None:
                        st.error("Error al aplicar contingencia")
                        st.stop()
                    st.session_state.calendario_actual = df_final
                    st.session_state.alternativas = None
                    st.toast("Contingencia aplicada correctamente", icon="✅")
        st.rerun()

    st.markdown("---")

    # Botón para generar alternativas (usa los valores actuales del estado)
    if st.button("🔍 Ver otras opciones (7 variantes)", use_container_width=True):
        with st.spinner("Generando alternativas..."):
            alts = generar_alternativas(st.session_state.año, st.session_state.mes,
                                        st.session_state.ciclo, st.session_state.config['pais'],
                                        7, st.session_state.modo)
            st.session_state.alternativas = alts
            st.toast("Se generaron 7 opciones alternativas", icon="✨")
        st.rerun()

    st.markdown("---")

    # Expandir para gestión de personas
    with st.expander("👥 Administrar personas"):
        personas = database.obtener_personas()
        for p in personas:
            cols = st.columns([2.5, 1.0, 1.0, 0.6])
            with cols[0]:
                nuevo_nombre = st.text_input("Nombre", value=p['nombre'], key=f"nombre_{p['id']}", label_visibility="collapsed")
            with cols[1]:
                grupo_options = ['A', 'B']
                idx_grupo = grupo_options.index(p['grupo'])
                nuevo_grupo = st.selectbox("Grupo", options=grupo_options, index=idx_grupo, key=f"grupo_{p['id']}", label_visibility="collapsed")
            with cols[2]:
                if nuevo_grupo == 'B':
                    subgrupo_options = ['B1', 'B2']
                    idx_sub = subgrupo_options.index(p['subgrupo']) if p['subgrupo'] else 0
                    nuevo_subgrupo = st.selectbox("Subgrupo", options=subgrupo_options, index=idx_sub, key=f"sub_{p['id']}", label_visibility="collapsed")
                else:
                    nuevo_subgrupo = None
                    st.empty()
            with cols[3]:
                if st.button("💾", key=f"save_{p['id']}"):
                    database.actualizar_nombre(p['id'], nuevo_nombre)
                    if nuevo_grupo != p['grupo'] or nuevo_subgrupo != p['subgrupo']:
                        database.actualizar_grupo(p['id'], nuevo_grupo, nuevo_subgrupo)
                    st.toast(f"Persona {p['id']} actualizada", icon="✅")
                    st.rerun()

        st.markdown("---")
        config = database.obtener_configuracion()
        b1_desc = st.checkbox("B1 descansa sábados", value=config['b1_descansa_sabados'])
        b2_desc = st.checkbox("B2 descansa sábados", value=config['b2_descansa_sabados'])
        if st.button("Guardar configuración Grupo B", use_container_width=True):
            database.actualizar_configuracion(b1_descansa_sabados=b1_desc, b2_descansa_sabados=b2_desc)
            st.session_state.config = database.obtener_configuracion()
            st.toast("Configuración guardada", icon="✅")
            st.rerun()

    # Expandir para ausencias
    with st.expander("📅 Registrar ausencias"):
        with st.container():
            st.markdown("**Nueva ausencia**")
            personas_dict = {p['id']: p['nombre'] for p in database.obtener_personas()}
            persona_id = st.selectbox("Persona", options=list(personas_dict.keys()), format_func=lambda x: personas_dict[x], key="aus_persona")
            fecha_inicio = st.date_input("Inicio", value=date(st.session_state.año, st.session_state.mes, 1), key="aus_inicio")
            fecha_fin = st.date_input("Fin", value=date(st.session_state.año, st.session_state.mes, 1), key="aus_fin")
            tipo = st.selectbox("Tipo", options=['V', 'PNR', 'IM', 'CD'], key="aus_tipo")
            motivo = st.text_input("Motivo", key="aus_motivo")
            if st.button("Registrar", use_container_width=True):
                ausencias.registrar_ausencia(persona_id, fecha_inicio.isoformat(), fecha_fin.isoformat(), tipo, motivo)
                st.toast("Ausencia registrada", icon="✅")
                st.rerun()

        st.markdown("---")
        st.markdown("**Ausencias del mes**")
        ausencias_mes = ausencias.obtener_ausencias(mes=st.session_state.mes, año=st.session_state.año)
        if ausencias_mes:
            for aus in ausencias_mes:
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.text(f"{personas_dict[aus['persona_id']]}: {aus['fecha_inicio'][5:]} → {aus['fecha_fin'][5:]} ({aus['tipo']})")
                with col2:
                    if st.button("❌", key=f"del_{aus['id']}"):
                        ausencias.eliminar_ausencia(aus['id'])
                        st.toast("Ausencia eliminada", icon="🗑️")
                        st.rerun()
        else:
            st.info("No hay ausencias registradas")

    # Expandir para colores (solo información)
    with st.expander("🎨 Colores"):
        st.markdown("""
        - 🟢 **M** = Mañana
        - 🟡 **T** = Tarde
        - 🔵 **N** = Noche
        - 🔴 **Festivo/Domingo**
        - 🔴 **V/PNR/IM/CD** = Ausencia
        """)

# ------------------------------------------------------------
# Cuerpo principal
# ------------------------------------------------------------
st.title("📅 Tennis Scheduling Solutions")

# --- Título del mes (con términos traducidos) ---
# Obtener el nombre legible del modo (igual que en el sidebar)
modo_legible = "Estándar" if st.session_state.modo == 'normal' else "Con ausencias"
st.markdown(f"#### {calendar.month_name[st.session_state.mes]} {st.session_state.año} - Rotación: {st.session_state.ciclo} - {modo_legible}")

# Mostrar el calendario actual o las alternativas
if st.session_state.alternativas:
    alternativas = st.session_state.alternativas
    tabs = st.tabs([f"Opción {i+1}" for i in range(len(alternativas))])
    for i, tab in enumerate(tabs):
        with tab:
            df_alt = alternativas[i]['df']
            # Traducción de "Offsets iniciales"
            st.markdown(f"**Patrón inicial:** {alternativas[i]['offsets']}")
            mostrar_calendario_html(df_alt, st.session_state.año, st.session_state.mes)

            # Botón para guardar esta alternativa como oficial
            if st.button(f"Guardar esta versión", key=f"guardar_alt_{i}"):
                with database.get_connection() as conn:
                    fecha_like = f"{st.session_state.año}-{st.session_state.mes:02d}%"
                    conn.execute("DELETE FROM calendario WHERE fecha LIKE ?", (fecha_like,))
                    df_to_save = df_alt.drop(columns=['nombre', 'grupo'], errors='ignore')
                    df_to_save.to_sql('calendario', conn, if_exists='append', index=False)
                    ciclos.guardar_offsets(alternativas[i]['final_offsets'], st.session_state.año, st.session_state.mes, st.session_state.ciclo)
                    conn.commit()
                st.success(f"Alternativa {i+1} guardada como calendario oficial.")
                st.session_state.alternativas = None
                # Recargar el calendario desde BD para tener todas las columnas (incluyendo 'nombre')
                df_recargado = cargar_datos_mes(st.session_state.año, st.session_state.mes)
                st.session_state.calendario_actual = df_recargado
                st.rerun()
else:
    if st.session_state.calendario_actual is None:
        # Si no hay calendario generado, intentar cargar de BD
        df = cargar_datos_mes(st.session_state.año, st.session_state.mes)
        if not df.empty:
            st.session_state.calendario_actual = df
        else:
            st.warning("No hay calendario para este mes. Usa el botón 'Generar calendario' en la barra lateral.")
            st.stop()
    else:
        df = st.session_state.calendario_actual

    mostrar_calendario_html(df, st.session_state.año, st.session_state.mes)
    
    # Estadísticas rápidas (con texto más claro)
    st.subheader("Resumen de cobertura")
    # Asegurar que df tenga la columna 'nombre'
    if 'nombre' not in df.columns:
        personas = database.obtener_personas()
        df_nombres = pd.DataFrame(personas)[['id', 'nombre']]
        df = df.merge(df_nombres, left_on='persona_id', right_on='id', how='left')
        df = df.drop(columns=['id'], errors='ignore')

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total personas", len(df['nombre'].unique()))
    with col2:
        df_a = df[df['grupo'] == 'A']
        dias = sorted(df['fecha'].unique())
        completos = sum(1 for dia in dias 
                if len(df_a.loc[(df_a['fecha'] == dia) & (df_a['turno'] == 'M')]) == 2 
                and len(df_a.loc[(df_a['fecha'] == dia) & (df_a['turno'] == 'N')]) == 2)
        st.metric("Días con cobertura completa (Grupo A)", f"{completos}/{len(dias)}")
    with col3:
        st.metric("Personas en Grupo B", len(df[df['grupo'] == 'B']['persona_id'].unique()))

    # Botones de exportación (prominentes)
    st.markdown("---")
    col_export1, col_export2 = st.columns(2)
    with col_export1:
        if st.button("📥 Exportar a Excel", use_container_width=True):
            excel_path = os.path.join(OUTPUT_DIR, f"calendario_{st.session_state.año}_{st.session_state.mes:02d}.xlsx")
            generar_excel_con_formato(df, st.session_state.año, st.session_state.mes, st.session_state.ciclo, excel_path)
            with open(excel_path, "rb") as f:
                st.download_button("Descargar Excel", data=f, file_name=f"calendario_{st.session_state.año}_{st.session_state.mes:02d}.xlsx",
                                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="excel_download")
    with col_export2:
        if st.button("📄 Exportar a PDF", use_container_width=True):
            pdf_path = os.path.join(OUTPUT_DIR, f"calendario_{st.session_state.año}_{st.session_state.mes:02d}.pdf")
            generar_pdf_calendario(df, st.session_state.año, st.session_state.mes, st.session_state.ciclo, pdf_path)
            with open(pdf_path, "rb") as f:
                st.download_button("Descargar PDF", data=f, file_name=f"calendario_{st.session_state.año}_{st.session_state.mes:02d}.pdf",
                                   mime="application/pdf", key="pdf_download")

st.markdown("---")
st.markdown(
    "<div style='text-align: left;'> © 2026 Dairo García. Licencia MIT. Desarrollado para Tennis S.A.</div>",
    unsafe_allow_html=True
)