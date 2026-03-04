"""
exportar.py
Módulo para exportar el calendario a PDF y Excel con formato profesional.
Ahora con dos filas de encabezado: día de la semana (1 letra) y número de día.
"""

import os
from datetime import datetime
import pandas as pd
import calendar

# Librerías para PDF
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm

# Librerías para Excel
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment
from openpyxl.utils.dataframe import dataframe_to_rows

# Colores de la paleta
COLOR_M = "#27AE60"      # Mañana
COLOR_T = "#F39C12"      # Tarde
COLOR_N = "#34495E"      # Noche
COLOR_FESTIVO = "#E74C3C" # Festivos/Domingos/Ausencias
COLOR_TEXTO = "#2C3E50"
COLOR_FONDO = "#ECF0F1"

def dia_abreviatura(fecha):
    """Devuelve la abreviatura de una letra para el día de la semana."""
    dias = ['L', 'M', 'X', 'J', 'V', 'S', 'D']
    return dias[fecha.weekday()]

# ------------------------------------------------------------
# Exportar a PDF
# ------------------------------------------------------------

def generar_pdf_calendario(df, año, mes, ciclo, output_path):
    """
    Genera un PDF con el calendario de turnos.
    Formato: dos filas de cabecera (día de la semana y número), luego los datos.
    """
    # Crear el documento PDF en orientación horizontal
    doc = SimpleDocTemplate(output_path, pagesize=landscape(A4),
                           rightMargin=1*cm, leftMargin=1*cm,
                           topMargin=1*cm, bottomMargin=1*cm)

    elementos = []
    styles = getSampleStyleSheet()
    titulo_style = styles['Title']
    titulo_style.textColor = colors.HexColor(COLOR_TEXTO)

    # Título
    titulo = Paragraph(f"PROGRAMACIÓN MES DE {calendar.month_name[mes].upper()} {año} (Ciclo {ciclo})", titulo_style)
    elementos.append(titulo)
    elementos.append(Spacer(1, 0.5*cm))

    # Preparar datos
    personas = df[['persona_id', 'nombre']].drop_duplicates().sort_values('persona_id')
    fechas = sorted(df['fecha'].unique())
    fechas_obj = [datetime.strptime(f, "%Y-%m-%d").date() for f in fechas]

    # Construir datos para la tabla
    data = []

    # Primera fila de cabecera: días de la semana
    fila1 = [""]  # primera celda vacía
    for f in fechas_obj:
        fila1.append(dia_abreviatura(f))
    data.append(fila1)

    # Segunda fila de cabecera: números de día
    fila2 = ["NOMBRE"]
    for f in fechas_obj:
        fila2.append(str(f.day))
    data.append(fila2)

    # Filas de personas
    for _, persona in personas.iterrows():
        pid = persona['persona_id']
        nombre = persona['nombre']
        fila = [nombre]
        for fecha in fechas:
            turno_df = df[(df['persona_id'] == pid) & (df['fecha'] == fecha)]
            if not turno_df.empty:
                turno = turno_df['turno'].values[0]
                fila.append(turno)
            else:
                fila.append("")
        data.append(fila)

    # Crear tabla
    ancho_columna = 1.2*cm  # ajustable
    col_widths = [3*cm] + [ancho_columna] * len(fechas)
    tabla = Table(data, colWidths=col_widths)

    # Estilo de la tabla
    style = []

    # Fondo de la primera columna (nombres)
    for i in range(2, len(data)):
        style.append(('BACKGROUND', (0,i), (0,i), colors.HexColor(COLOR_TEXTO)))
        style.append(('TEXTCOLOR', (0,i), (0,i), colors.white))

    # Fondo de las filas de cabecera
    style.append(('BACKGROUND', (0,0), (-1,0), colors.HexColor(COLOR_TEXTO)))
    style.append(('TEXTCOLOR', (0,0), (-1,0), colors.white))
    style.append(('BACKGROUND', (0,1), (-1,1), colors.HexColor(COLOR_TEXTO)))
    style.append(('TEXTCOLOR', (0,1), (-1,1), colors.white))

    # Alineación
    style.append(('ALIGN', (0,0), (-1,-1), 'CENTER'))
    style.append(('VALIGN', (0,0), (-1,-1), 'MIDDLE'))
    style.append(('FONTNAME', (0,0), (-1,1), 'Helvetica-Bold'))
    style.append(('FONTSIZE', (0,0), (-1,-1), 8))
    style.append(('GRID', (0,0), (-1,-1), 0.5, colors.grey))

    # Colores por turno en celdas de datos (desde fila 2 en adelante)
    for i, fila in enumerate(data[2:], start=2):
        for j, fecha in enumerate(fechas, start=1):
            turno = data[i][j]
            if turno in ['V', 'PNR', 'IM', 'CD']:
                style.append(('BACKGROUND', (j,i), (j,i), colors.HexColor(COLOR_FESTIVO)))
                style.append(('TEXTCOLOR', (j,i), (j,i), colors.white))
            elif turno == 'M':
                style.append(('BACKGROUND', (j,i), (j,i), colors.HexColor(COLOR_M)))
                style.append(('TEXTCOLOR', (j,i), (j,i), colors.white))
            elif turno == 'T':
                style.append(('BACKGROUND', (j,i), (j,i), colors.HexColor(COLOR_T)))
                style.append(('TEXTCOLOR', (j,i), (j,i), colors.white))
            elif turno == 'N':
                style.append(('BACKGROUND', (j,i), (j,i), colors.HexColor(COLOR_N)))
                style.append(('TEXTCOLOR', (j,i), (j,i), colors.white))

    # Resaltar días festivos en la cabecera (fila 0 y 1)
    for j, fecha in enumerate(fechas, start=1):
        es_festivo = df[df['fecha'] == fecha]['es_festivo'].max()
        if es_festivo:
            style.append(('BACKGROUND', (j,0), (j,0), colors.HexColor(COLOR_FESTIVO)))
            style.append(('BACKGROUND', (j,1), (j,1), colors.HexColor(COLOR_FESTIVO)))
            style.append(('TEXTCOLOR', (j,0), (j,1), colors.white))

    tabla.setStyle(TableStyle(style))
    elementos.append(tabla)
    elementos.append(Spacer(1, 0.5*cm))

    # Leyenda
    leyenda_style = ParagraphStyle('Leyenda', parent=styles['Normal'], fontSize=8)
    leyenda = Paragraph(
        "🟢 M = Mañana   🟡 T = Tarde   🔵 N = Noche   🔴 Festivo/Domingo/Ausencia",
        leyenda_style
    )
    elementos.append(leyenda)

    doc.build(elementos)
    print(f"✅ PDF generado: {output_path}")

# ------------------------------------------------------------
# Exportar a Excel con formato
# ------------------------------------------------------------

def generar_excel_con_formato(df, año, mes, ciclo, output_path):
    """
    Genera un archivo Excel con el calendario de turnos.
    Formato: dos filas de encabezado (día de la semana y número), luego datos.
    """
    # Preparar datos
    personas = df[['persona_id', 'nombre']].drop_duplicates().sort_values('persona_id')
    fechas = sorted(df['fecha'].unique())
    fechas_obj = [datetime.strptime(f, "%Y-%m-%d").date() for f in fechas]

    # Crear libro
    wb = Workbook()
    ws = wb.active
    ws.title = f"Calendario {mes}-{año}"

    # Escribir título en A1 (opcional, pero lo dejamos como comentario)
    # ws['A1'] = f"PROGRAMACIÓN MES DE {calendar.month_name[mes].upper()} {año}"

    # Primera fila de encabezado: días de la semana
    ws.cell(row=1, column=1, value="")  # celda vacía
    for idx, f in enumerate(fechas_obj, start=2):
        ws.cell(row=1, column=idx, value=dia_abreviatura(f))

    # Segunda fila de encabezado: números y "NOMBRE"
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

    # Aplicar estilos
    # Estilo para encabezados (filas 1 y 2)
    header_fill = PatternFill(start_color="2C3E50", end_color="2C3E50", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)
    for col in range(1, len(fechas)+2):
        for row in [1,2]:
            cell = ws.cell(row=row, column=col)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal='center', vertical='center')

    # Estilo para columna de nombres (columna 1 desde fila 3)
    nombre_fill = PatternFill(start_color="2C3E50", end_color="2C3E50", fill_type="solid")
    nombre_font = Font(color="FFFFFF")
    for row in range(3, 3 + len(personas)):
        cell = ws.cell(row=row, column=1)
        cell.fill = nombre_fill
        cell.font = nombre_font
        cell.alignment = Alignment(horizontal='center', vertical='center')

    # Colores por turno en las celdas de datos
    for row in range(3, 3 + len(personas)):
        for col in range(2, len(fechas)+2):
            cell = ws.cell(row=row, column=col)
            valor = cell.value
            fecha_str = fechas[col-2]
            es_festivo = df[df['fecha'] == fecha_str]['es_festivo'].max()
            if es_festivo:
                cell.fill = PatternFill(start_color="E74C3C", end_color="E74C3C", fill_type="solid")
                cell.font = Font(color="FFFFFF", bold=True)
            elif valor in ['V', 'PNR', 'IM', 'CD']:
                cell.fill = PatternFill(start_color="E74C3C", end_color="E74C3C", fill_type="solid")
                cell.font = Font(color="FFFFFF", bold=True)
            elif valor == 'M':
                cell.fill = PatternFill(start_color="27AE60", end_color="27AE60", fill_type="solid")
                cell.font = Font(color="FFFFFF")
            elif valor == 'T':
                cell.fill = PatternFill(start_color="F39C12", end_color="F39C12", fill_type="solid")
                cell.font = Font(color="FFFFFF")
            elif valor == 'N':
                cell.fill = PatternFill(start_color="34495E", end_color="34495E", fill_type="solid")
                cell.font = Font(color="FFFFFF")
            # Si es L, sin color
            cell.alignment = Alignment(horizontal='center', vertical='center')

    # Ajustar ancho de columnas
    for col in ws.columns:
        max_length = 0
        col_letter = col[0].column_letter
        for cell in col:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        adjusted_width = min(max_length + 2, 12)
        ws.column_dimensions[col_letter].width = adjusted_width

    # Guardar
    wb.save(output_path)
    print(f"✅ Excel con formato generado: {output_path}")