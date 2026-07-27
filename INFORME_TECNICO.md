# INFORME TÉCNICO: Tennis Scheduling Solutions

## 1. DESCRIPCIÓN DEL PROYECTO

**Tennis Scheduling Solutions** es una aplicación web desarrollada para automatizar la generación y gestión de calendarios de turnos en instalaciones deportivas (específicamente para Tennis S.A.). La solución permite crear calendarios rotativos complejos para personal que trabaja en múltiples turnos (mañana, tarde, noche), considerando festivos, ausencias del personal y reglas de descanso obligatorio. Es un proyecto de prácticas profesionales completado en marzo de 2026, bajo la licencia MIT.

---

## 2. ¿QUÉ HACE?

La aplicación automatiza los siguientes procesos:

### 2.1 Generación de Calendarios de Turnos
- **Grupo A**: Rota automáticamente 6 empleados entre turnos Mañana (M), Tarde (T), Noche (N) y Libre (L) usando dos ciclos:
  - **Ciclo 2x2x2**: Patrón de 2 días de mañana, 2 de noche, 2 libres
  - **Ciclo 4x2**: Patrón de 4 días de mañana, 2 libres, 4 de noche, 2 libres
- **Grupo B**: Asigna dos personas (B1 y B2) con turnos de tarde (T) en días laborales y libres (L) en festivos/domingos

### 2.2 Gestión de Ausencias
- Registro de ausencias tipificadas: Vacaciones (V), Permiso No Remunerado (PNR), Incapacidad Médica (IM), Comisión Directiva (CD)
- Reasignación automática de turnos: Cuando alguien falta, el Grupo B asume su carga
- Balanceo inteligente: Redistribuye días especiales (domingos/festivos) equitativamente

### 2.3 Manejo de Restricciones
- Respeta festivos nacionales por país (ej: Colombia)
- Valida regla de descanso: No permite Noche → Mañana consecutivos sin día libre intermedio
- Gestiona configuración de descansos en fin de semana por subgrupo

### 2.4 Exportación de Datos
- **Excel**: Calendario con formato profesional, colores por turno, bordes y estructura editable
- **PDF**: Reporte compacto en orientación horizontal, ideal para impresión

---

## 3. ¿CÓMO FUNCIONA?

### 3.1 Arquitectura y Flujo General

```
┌─────────────────────────────────────────────────────────────┐
│                   app.py (Frontend)                          │
│     Interfaz interactiva con Streamlit (Web responsive)     │
└────────────┬────────────────────────────────────────────────┘
             │
             ├──→ ciclos.py → Genera turnos Grupo A (patrones rotativos)
             │
             ├──→ grupo_b.py → Genera turnos Grupo B (fijos/contingencia)
             │
             ├──→ ausencias.py → Gestiona ausencias y reasignación
             │
             ├──→ balanceo.py → Equilibra carga de domingos/festivos
             │
             ├──→ database.py → Acceso a datos (SQLite)
             │
             └──→ exportar.py → Genera Excel y PDF
```

### 3.2 Proceso Paso a Paso

**1. Generación Inicial:**
- El usuario selecciona año, mes, ciclo (2x2x2 o 4x2) y país
- `ciclos.generar_calendario_grupoA()` crea turnos para el Grupo A:
  - Carga offsets del mes anterior (para continuidad)
  - Aplica patrón de ciclo a cada persona con su offset
  - Genera lista de fechas del mes y marca festivos
- `grupo_b.generar_calendario_grupoB()` asigna tardes al Grupo B, respetando config

**2. Almacenamiento:**
- El calendario se guarda en SQLite (`tabla calendario`)
- Los offsets finales se persisten en `tabla estado_ciclo` para el próximo mes

**3. Modo Contingencia (Ausencias):**
- Usuario registra ausencias en el sidebar
- `ausencias.aplicar_contingencia()` ejecuta:
  1. Marca los turnos del ausente con su código (V/PNR/IM/CD)
  2. Reasigna: Grupo B asume turnos del ausente si hay déficit de cobertura
  3. Si aún falta cobertura, personas del Grupo A con día libre son movidas a tarde
  4. Aplica balanceo para redistribuir carga de especiales

**4. Balanceo de Equidad:**
- Calcula cuántos domingos/festivos trabaja cada persona del Grupo A
- Intercambia turnos entre quien más trabaja (en especiales) y quien menos
- Respeta regla N→M sin violar seguridad

**5. Exportación:**
- Usuario descarga Excel o PDF desde botones del frontend
- Ambos formatos incluyen leyenda de colores y metadatos (año, mes, ciclo)

---

## 4. STACK TECNOLÓGICO

### 4.1 Lenguaje
- **Python 3.x** (100% del código)

### 4.2 Framework Web
- **Streamlit 1.54.0**: Framework para crear interfaces web interactivas sin JavaScript
  - Simplifica construcción de dashboards
  - Gestión de estado de sesión integrada
  - Renderizado automático ante cambios

### 4.3 Procesamiento de Datos
- **Pandas 2.3.3**: Manipulación de DataFrames, lectura/escritura SQL
- **NumPy 2.4.2**: Operaciones numéricas subyacentes

### 4.4 Base de Datos
- **SQLite 3** (nativo en Python): BD ligera, sin servidor
- **Tablas principales:**
  - `personas`: ID, nombre, grupo (A/B), subgrupo (B1/B2)
  - `calendario`: turnos diarios por persona
  - `ausencias`: registro de faltas tipificadas
  - `estado_ciclo`: offsets por mes/persona (continuidad)
  - `configuracion`: parámetros globales

### 4.5 Exportación
- **Openpyxl 3.1.5**: Generación de archivos Excel con estilos (colores, bordes, fuentes)
- **ReportLab 4.4.10**: Generación de PDF con tablas formateadas
- **Pillow 12.1.1**: Procesamiento de imágenes (logo, assets)

### 4.6 Utilidades
- **holidays 0.91**: Cálculo automático de festivos por país (ej: Colombia)
- **python-dateutil 2.9.0**: Manejo de fechas y períodos
- **PyInstaller 6.19.0**: Empaquetamiento a ejecutable standalone

### 4.7 Control de Versiones y Desarrollo
- **Git / GitPython 3.1.46**: Versionado y acceso a repositorio
- **Altair 6.0.0**: Libería de visualización (aunque no se usa en versión actual)

---

## 5. ORGANIZACIÓN DEL CÓDIGO

```
tennis-scheduling/
├── app.py                      # Entrada principal, interfaz Streamlit
├── requirements.txt            # Dependencias Python
├── LICENSE.txt                 # Licencia MIT
├── README.MD                   # Documentación básica
├── data/                       # Directorio de datos
│   └── schedules.db           # Base de datos SQLite
├── output/                     # Directorio de exportaciones
│   ├── calendario_2026_01.xlsx
│   └── calendario_2026_01.pdf
├── assets/                     # Recursos
│   └── logo.png               # Logo de la aplicación
└── src/                        # Módulos de lógica
    ├── __init__.py
    ├── database.py            # CRUD y conexión SQLite
    ├── ciclos.py              # Generación de turnos Grupo A
    ├── grupo_b.py             # Calendario fijo Grupo B
    ├── ausencias.py           # Gestión de ausencias y contingencia
    ├── balanceo.py            # Equilibrio de carga especiales
    └── exportar.py            # Generación Excel/PDF
```

### Responsabilidades por Módulo

| Módulo | Responsabilidad |
|--------|-----------------|
| **app.py** | UI interactiva, manejo de sesiones, orquestación |
| **database.py** | Abstraer conexiones SQLite, CRUD de entidades |
| **ciclos.py** | Lógica matemática de rotación, offsets, patrones |
| **grupo_b.py** | Reglas fijas del Grupo B, configuración de descansos |
| **ausencias.py** | Aplicación de ausencias, reasignación de Grupo B, contingencia |
| **balanceo.py** | Algoritmo greedy de intercambios para equidad |
| **exportar.py** | Formatos profesionales (Excel, PDF) con estilos |

---

## 6. CARACTERÍSTICAS PRINCIPALES

### 6.1 Interfaz de Usuario
- **Sidebar compacto**: Formulario de configuración, gestión de personas, registro de ausencias
- **Panel principal**: Visualización HTML del calendario con colores dinámicos
- **Estadísticas**: Cobertura por grupo, resumen de personas
- **Leyenda interactiva**: M (Mañana)=Verde, T (Tarde)=Naranja, N (Noche)=Gris, Festivo/Ausencia=Rojo

### 6.2 Generación de Alternativas
- Botón "Ver otras opciones (7 variantes)" genera 7 calendarios con offsets permutados
- Usuario puede comparar y seleccionar la mejor opción
- Cada alternativa es una pestaña independiente en la interfaz

### 6.3 Validaciones y Restricciones
- Impide N → M sin descanso intermedio
- Verifica cobertura mínima (2M, 2N diarios; 1 o 2T según día)
- Considera festivos nacionales automáticamente

### 6.4 Escalabilidad
- Número de personas configurable (actualmente 8: 6 Grupo A, 2 Grupo B)
- Soporta ciclos 2x2x2 y 4x2 (extensible)
- Países configurables vía librería `holidays`

---

## 7. FLUJO DE USUARIO TÍPICO

1. **Inicio**: Cargar app desde navegador
2. **Configuración**: Seleccionar año, mes, ciclo (2x2x2/4x2), modo (normal/contingencia)
3. **Generar**: Pulsar "📅 Generar calendario"
4. **Visualización**: Ver calendario en HTML con colores
5. **Alternativas** (opcional): Explorar 7 variantes antes de decidir
6. **Ausencias** (si aplica): Registrar vacaciones/incapacidades
7. **Exportar**: Descargar Excel o PDF del calendario final

---

## 8. INSTALACIÓN Y EJECUCIÓN

### Requisitos
- Python 3.8+
- pip o conda

### Pasos
```bash
# 1. Clonar repositorio
git clone https://github.com/Garcia-3097/tennis-scheduling.git
cd tennis-scheduling

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Ejecutar aplicación
streamlit run app.py

# 4. Abrir navegador
# → http://localhost:8501
```

### Empaquetamiento (Ejecutable Standalone)
```bash
pyinstaller --onefile --windowed app.py
# Genera: dist/app.exe (Windows)
```

---

## 9. VENTAJAS DEL SISTEMA

✅ **Automatización total**: Elimina cálculo manual de turnos  
✅ **Equidad garantizada**: Balanceo automático de cargas especiales  
✅ **Flexibilidad**: Soporta múltiples ciclos y países  
✅ **Contingencia integrada**: Reasignación inteligente ante ausencias  
✅ **Exportación profesional**: Excel y PDF listos para presentar  
✅ **Interfaz intuitiva**: No requiere conocimientos técnicos  
✅ **Persistencia**: Historial completo en base de datos  
✅ **Continuidad**: Offsets guardados garantizan rotación fluida entre meses  

---

## 10. LIMITACIONES Y MEJORAS FUTURAS

**Limitaciones actuales:**
- Grupo A fijo a 6 personas (requiere modificar constantes para escalabilidad)
- No hay gestión de permisos/roles de usuario
- Interfaz solo en español

**Mejoras potenciales:**
- API REST para integración con otros sistemas
- Interfaz multiidioma
- Algoritmo de balanceo más sofisticado (con pesos para ausencias)
- Predicción de impacto de ausencias antes de registrar
- Integración con calendario Google/Outlook

---

## CONCLUSIÓN

**Tennis Scheduling Solutions** es una solución integral para la gestión de calendarios de turnos rotativos en servicios continuos. Combina lógica matemática robusta con interfaz moderna para lograr automatización, equidad y cumplimiento normativo sin requerir intervención manual. Su arquitectura modular facilita mantenimiento y extensión futura.

---

**Proyecto**: Tennis Scheduling Solutions  
**Autor**: Dairo García  
**Licencia**: MIT  
**Año**: 2026  
**Desarrollado para**: Tennis S.A.
