"""
exportar.py
Exportación del calendario a Excel y PDF con formato profesional.
"""

import pandas as pd
import calendar
from datetime import datetime
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm

# ------------------------------------------------------------
# Constantes de colores (sin '#', para compatibilidad con openpyxl)
# ------------------------------------------------------------
COLOR_MORNING = "27AE60"
COLOR_AFTERNOON = "F39C12"
COLOR_NIGHT = "34495E"
COLOR_HOLIDAY = "E74C3C"
COLOR_TEXT = "2C3E50"
COLOR_BACKGROUND = "ECF0F1"

def _dia_abreviatura(fecha: datetime) -> str:
    """Retorna la abreviatura de una letra para el día de la semana."""
    dias = ['L', 'M', 'X', 'J', 'V', 'S', 'D']
    return dias[fecha.weekday()]

# ------------------------------------------------------------
# PDF
# ------------------------------------------------------------
def generar_pdf_calendario(df: pd.DataFrame, año: int, mes: int, ciclo: str, output_path: str) -> None:
    """Genera un PDF con el calendario de turnos."""
    doc = SimpleDocTemplate(output_path, pagesize=landscape(A4),
                           rightMargin=1*cm, leftMargin=1*cm,
                           topMargin=1*cm, bottomMargin=1*cm)

    elementos = []
    styles = getSampleStyleSheet()
    titulo_style = styles['Title']
    titulo_style.textColor = colors.HexColor("#" + COLOR_TEXT)

    titulo = Paragraph(f"PROGRAMACIÓN MES DE {calendar.month_name[mes].upper()} {año} (Ciclo {ciclo})", titulo_style)
    elementos.append(titulo)
    elementos.append(Spacer(1, 0.5*cm))

    # Preparar datos
    personas = df[['persona_id', 'nombre']].drop_duplicates().sort_values('persona_id')
    fechas = sorted(df['fecha'].unique())
    fechas_obj = [datetime.strptime(f, "%Y-%m-%d").date() for f in fechas]

    # Construir tabla
    data = []
    # Fila 1: día de la semana
    fila1 = [""] + [_dia_abreviatura(f) for f in fechas_obj]
    data.append(fila1)
    # Fila 2: número del día
    fila2 = ["NOMBRE"] + [str(f.day) for f in fechas_obj]
    data.append(fila2)

    for _, persona in personas.iterrows():
        pid = persona['persona_id']
        nombre = persona['nombre']
        fila = [nombre]
        for fecha in fechas:
            turno_df = df[(df['persona_id'] == pid) & (df['fecha'] == fecha)]
            fila.append(turno_df['turno'].values[0] if not turno_df.empty else "")
        data.append(fila)

    ancho_columna = 1.2 * cm
    col_widths = [3*cm] + [ancho_columna] * len(fechas)
    tabla = Table(data, colWidths=col_widths)

    style = []

    # Fondo de la primera columna (nombres)
    for i in range(2, len(data)):
        style.append(('BACKGROUND', (0,i), (0,i), colors.HexColor("#" + COLOR_TEXT)))
        style.append(('TEXTCOLOR', (0,i), (0,i), colors.white))

    # Cabeceras
    style.append(('BACKGROUND', (0,0), (-1,0), colors.HexColor("#" + COLOR_TEXT)))
    style.append(('TEXTCOLOR', (0,0), (-1,0), colors.white))
    style.append(('BACKGROUND', (0,1), (-1,1), colors.HexColor("#" + COLOR_TEXT)))
    style.append(('TEXTCOLOR', (0,1), (-1,1), colors.white))

    style.append(('ALIGN', (0,0), (-1,-1), 'CENTER'))
    style.append(('VALIGN', (0,0), (-1,-1), 'MIDDLE'))
    style.append(('FONTNAME', (0,0), (-1,1), 'Helvetica-Bold'))
    style.append(('FONTSIZE', (0,0), (-1,-1), 8))
    style.append(('GRID', (0,0), (-1,-1), 0.5, colors.grey))

    # Colores por turno en celdas de datos
    for i, fila in enumerate(data[2:], start=2):
        for j, fecha in enumerate(fechas, start=1):
            turno = data[i][j]
            if turno in ['V', 'PNR', 'IM', 'CD']:
                style.append(('BACKGROUND', (j,i), (j,i), colors.HexColor("#" + COLOR_HOLIDAY)))
                style.append(('TEXTCOLOR', (j,i), (j,i), colors.white))
            elif turno == 'M':
                style.append(('BACKGROUND', (j,i), (j,i), colors.HexColor("#" + COLOR_MORNING)))
                style.append(('TEXTCOLOR', (j,i), (j,i), colors.white))
            elif turno == 'T':
                style.append(('BACKGROUND', (j,i), (j,i), colors.HexColor("#" + COLOR_AFTERNOON)))
                style.append(('TEXTCOLOR', (j,i), (j,i), colors.white))
            elif turno == 'N':
                style.append(('BACKGROUND', (j,i), (j,i), colors.HexColor("#" + COLOR_NIGHT)))
                style.append(('TEXTCOLOR', (j,i), (j,i), colors.white))

    # Resaltar días festivos en cabecera
    for j, fecha in enumerate(fechas, start=1):
        es_festivo = df[df['fecha'] == fecha]['es_festivo'].max()
        if es_festivo:
            style.append(('BACKGROUND', (j,0), (j,0), colors.HexColor("#" + COLOR_HOLIDAY)))
            style.append(('BACKGROUND', (j,1), (j,1), colors.HexColor("#" + COLOR_HOLIDAY)))
            style.append(('TEXTCOLOR', (j,0), (j,1), colors.white))

    tabla.setStyle(TableStyle(style))
    elementos.append(tabla)
    elementos.append(Spacer(1, 0.5*cm))

    leyenda_style = ParagraphStyle('Leyenda', parent=styles['Normal'], fontSize=8)
    leyenda = Paragraph(
        "🟢 M = Mañana   🟡 T = Tarde   🔵 N = Noche   🔴 Festivo/Domingo/Ausencia",
        leyenda_style
    )
    elementos.append(leyenda)

    doc.build(elementos)

# ------------------------------------------------------------
# Excel
# ------------------------------------------------------------
def generar_excel_con_formato(df: pd.DataFrame, año: int, mes: int, ciclo: str, output_path: str) -> None:
    """Genera un archivo Excel con formato profesional."""
    personas = df[['persona_id', 'nombre']].drop_duplicates().sort_values('persona_id')
    fechas = sorted(df['fecha'].unique())
    fechas_obj = [datetime.strptime(f, "%Y-%m-%d").date() for f in fechas]

    wb = Workbook()
    ws = wb.active
    ws.title = f"Calendario {mes}-{año}"

    # Cabecera: fila 1 días de la semana, fila 2 números
    ws.cell(row=1, column=1, value="")
    for idx, f in enumerate(fechas_obj, start=2):
        ws.cell(row=1, column=idx, value=_dia_abreviatura(f))
    ws.cell(row=2, column=1, value="NOMBRE")
    for idx, f in enumerate(fechas_obj, start=2):
        ws.cell(row=2, column=idx, value=f.day)

    # Datos
    for row_idx, (_, persona) in enumerate(personas.iterrows(), start=3):
        pid = persona['persona_id']
        nombre = persona['nombre']
        ws.cell(row=row_idx, column=1, value=nombre)
        for col_idx, fecha in enumerate(fechas, start=2):
            turno_df = df[(df['persona_id'] == pid) & (df['fecha'] == fecha)]
            turno = turno_df['turno'].values[0] if not turno_df.empty else ""
            ws.cell(row=row_idx, column=col_idx, value=turno)

    # Estilos
    header_fill = PatternFill(start_color=COLOR_TEXT, end_color=COLOR_TEXT, fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)
    for col in range(1, len(fechas)+2):
        for row in [1,2]:
            cell = ws.cell(row=row, column=col)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal='center', vertical='center')

    nombre_fill = PatternFill(start_color=COLOR_TEXT, end_color=COLOR_TEXT, fill_type="solid")
    nombre_font = Font(color="FFFFFF")
    for row in range(3, 3 + len(personas)):
        cell = ws.cell(row=row, column=1)
        cell.fill = nombre_fill
        cell.font = nombre_font
        cell.alignment = Alignment(horizontal='center', vertical='center')

    for row in range(3, 3 + len(personas)):
        for col in range(2, len(fechas)+2):
            cell = ws.cell(row=row, column=col)
            valor = cell.value
            fecha_str = fechas[col-2]
            es_festivo = df[df['fecha'] == fecha_str]['es_festivo'].max()
            if es_festivo:
                cell.fill = PatternFill(start_color=COLOR_HOLIDAY, end_color=COLOR_HOLIDAY, fill_type="solid")
                cell.font = Font(color="FFFFFF", bold=True)
            elif valor in ['V', 'PNR', 'IM', 'CD']:
                cell.fill = PatternFill(start_color=COLOR_HOLIDAY, end_color=COLOR_HOLIDAY, fill_type="solid")
                cell.font = Font(color="FFFFFF", bold=True)
            elif valor == 'M':
                cell.fill = PatternFill(start_color=COLOR_MORNING, end_color=COLOR_MORNING, fill_type="solid")
                cell.font = Font(color="FFFFFF")
            elif valor == 'T':
                cell.fill = PatternFill(start_color=COLOR_AFTERNOON, end_color=COLOR_AFTERNOON, fill_type="solid")
                cell.font = Font(color="FFFFFF")
            elif valor == 'N':
                cell.fill = PatternFill(start_color=COLOR_NIGHT, end_color=COLOR_NIGHT, fill_type="solid")
                cell.font = Font(color="FFFFFF")
            cell.alignment = Alignment(horizontal='center', vertical='center')

    # Ajustar ancho de columnas
    for col in ws.columns:
        max_len = 0
        col_letter = col[0].column_letter
        for cell in col:
            try:
                max_len = max(max_len, len(str(cell.value)))
            except:
                pass
        ws.column_dimensions[col_letter].width = min(max_len + 2, 12)

    wb.save(output_path)