"""
run_tests.py
════════════
Runner autónomo de pruebas — no requiere pytest ni holidays.
Usa unittest (stdlib) + mock de holidays inyectado antes de importar src.

Ejecución:
    cd /ruta/del/proyecto
    python3 tests/run_tests.py
"""

import sys
import os
import sqlite3
import unittest
import tempfile
import shutil
import pandas as pd
from datetime import date, timedelta
from unittest.mock import patch, MagicMock
from typing import Dict, List

# ──────────────────────────────────────────────────────────────
# 0. Bootstrap: rutas y mock de holidays
# ──────────────────────────────────────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# Festivos Colombia 2026
_CO_2026 = {
    date(2026, 1, 1), date(2026, 1, 12), date(2026, 3, 23),
    date(2026, 4, 2), date(2026, 4, 3), date(2026, 5, 1),
    date(2026, 5, 18), date(2026, 6, 8), date(2026, 6, 15),
    date(2026, 6, 29), date(2026, 7, 20), date(2026, 8, 7),
    date(2026, 8, 17), date(2026, 10, 12), date(2026, 11, 2),
    date(2026, 11, 16), date(2026, 12, 8), date(2026, 12, 25),
}

class _MockCountryHoliday:
    def __init__(self, country, years):
        self._dias = _CO_2026 if (country == 'CO' and years == 2026) else set()
    def keys(self): return iter(self._dias)
    def __contains__(self, i): return i in self._dias
    def __iter__(self): return iter(self._dias)

_mock_holidays_mod = type(sys)('holidays')
_mock_holidays_mod.CountryHoliday = _MockCountryHoliday
sys.modules['holidays'] = _mock_holidays_mod

# Ahora importar src
import src.database as db_mod

# ──────────────────────────────────────────────────────────────
# Constantes compartidas
# ──────────────────────────────────────────────────────────────
AÑO  = 2026
MES  = 3
GRUPO_A_IDS = list(range(1, 7))
NO_TRABAJADOS = {'L', 'V', 'PNR', 'IM', 'CD'}


# ──────────────────────────────────────────────────────────────
# Base test case: BD aislada por test
# ──────────────────────────────────────────────────────────────
class BaseTestCase(unittest.TestCase):
    """Crea una BD temporal por test, la destruye al finalizar."""

    def setUp(self):
        self._tmp_dir = tempfile.mkdtemp()
        self._db_path = os.path.join(self._tmp_dir, "test.db")
        # Parchear la ruta de BD en el módulo
        self._original_path = db_mod.DB_PATH
        db_mod.DB_PATH = self._db_path
        db_mod.init_db()

    def tearDown(self):
        db_mod.DB_PATH = self._original_path
        shutil.rmtree(self._tmp_dir, ignore_errors=True)

    # ── helpers ──────────────────────────────────────────────

    def _generar_calendario_en_bd(self):
        from src import ciclos, grupo_b
        dfA, offsets = ciclos.generar_calendario_grupoA(AÑO, MES, ciclo='2x2x2')
        ciclos.guardar_calendario_en_bd(dfA, AÑO, MES)
        ciclos.guardar_offsets(offsets, AÑO, MES, '2x2x2')
        dfB = grupo_b.generar_calendario_grupoB(AÑO, MES)
        grupo_b.guardar_calendario_grupoB_en_bd(dfB, AÑO, MES)
        from src.ausencias import obtener_calendario_mes
        return obtener_calendario_mes(AÑO, MES)

    def _generar_calendario_df(self):
        from src import ciclos, grupo_b
        dfA, _ = ciclos.generar_calendario_grupoA(AÑO, MES, ciclo='2x2x2')
        dfA['grupo'] = 'A'; dfA['subgrupo'] = None
        dfB = grupo_b.generar_calendario_grupoB(AÑO, MES)
        dfB['grupo'] = 'B'
        dfB['subgrupo'] = dfB['persona_id'].map({7: 'B1', 8: 'B2'})
        return pd.concat([dfA, dfB], ignore_index=True)

    def _calcular_carga(self, df, dias_especiales):
        carga = {pid: 0 for pid in GRUPO_A_IDS}
        for fecha in dias_especiales:
            for pid in GRUPO_A_IDS:
                s = df[(df['persona_id'] == pid) & (df['fecha'] == fecha)]['turno']
                if not s.empty and s.iloc[0] not in NO_TRABAJADOS:
                    carga[pid] += 1
        return carga

    def _diferencia_carga(self, carga):
        return max(carga.values()) - min(carga.values())

    def _df_sintetico(self, asignaciones: Dict[int, str]):
        from src import balanceo, ciclos
        dias_especiales = balanceo.obtener_dias_especiales(AÑO, MES)
        dias_mes = [d.isoformat() for d in ciclos.generar_rango_fechas(AÑO, MES)]
        filas = []
        for pid in GRUPO_A_IDS:
            for fecha in dias_mes:
                turno = asignaciones.get(pid, 'L') if fecha in dias_especiales else 'M'
                filas.append({'persona_id': pid, 'fecha': fecha, 'turno': turno,
                               'es_festivo': 0, 'grupo': 'A', 'subgrupo': None})
        return pd.DataFrame(filas)

    def _registrar_ausencia_p1(self):
        from src import ausencias
        ausencias.registrar_ausencia(1, f"{AÑO}-{MES:02d}-10",
                                     f"{AÑO}-{MES:02d}-12", 'V', 'Test')


# ══════════════════════════════════════════════════════════════
# PASO 1 – Importaciones y generar_alternativas
# ══════════════════════════════════════════════════════════════

def generar_alternativas_pura(año, mes, ciclo, pais, num_alternativas=7, modo='normal'):
    from src import ciclos, grupo_b, database, ausencias
    variantes = ciclos.generar_variantes_offsets(ciclo, num_alternativas)
    personas   = database.obtener_personas()
    grupo_map  = {p['id']: p['grupo']    for p in personas}
    nombre_map = {p['id']: p['nombre']   for p in personas}
    sub_map    = {p['id']: p['subgrupo'] for p in personas}
    alternativas = []
    for offsets in variantes:
        dfA, offs_fin = ciclos.generar_calendario_grupoA(
            año, mes, ciclo=ciclo, pais=pais, offsets_iniciales=offsets)
        dfB = grupo_b.generar_calendario_grupoB(año, mes, pais=pais)
        df = pd.concat([dfA, dfB], ignore_index=True)
        df['grupo'] = df['persona_id'].map(grupo_map)
        df['nombre'] = df['persona_id'].map(nombre_map)
        df['subgrupo'] = df['persona_id'].map(sub_map)
        if modo == 'contingencia':
            df, _ = ausencias.aplicar_contingencia_a_df(df, año, mes, pais)
        alternativas.append({'df': df, 'offsets': offsets, 'final_offsets': offs_fin})
    return alternativas


class Paso1_Importaciones(BaseTestCase):

    def test_01_importar_todos_los_modulos_src(self):
        from src import database, ciclos, grupo_b, ausencias, balanceo
        for mod in [database, ciclos, grupo_b, ausencias, balanceo]:
            self.assertIsNotNone(mod)

    def test_02_alternativas_numero_correcto(self):
        alts = generar_alternativas_pura(AÑO, MES, '2x2x2', 'CO', num_alternativas=5)
        self.assertEqual(len(alts), 5)

    def test_03_estructura_alternativa(self):
        alts = generar_alternativas_pura(AÑO, MES, '2x2x2', 'CO', num_alternativas=2)
        for a in alts:
            self.assertIn('df', a)
            self.assertIn('offsets', a)
            self.assertIn('final_offsets', a)

    def test_04_df_contiene_columnas_esperadas(self):
        alts = generar_alternativas_pura(AÑO, MES, '2x2x2', 'CO', num_alternativas=1)
        for col in ['persona_id', 'fecha', 'turno', 'grupo', 'nombre']:
            self.assertIn(col, alts[0]['df'].columns, f"Columna faltante: {col}")

    def test_05_alternativas_con_offsets_distintos(self):
        alts = generar_alternativas_pura(AÑO, MES, '2x2x2', 'CO', num_alternativas=7)
        offsets_set = {tuple(a['offsets']) for a in alts}
        self.assertEqual(len(offsets_set), 7, "Todas deben tener offsets distintos")

    def test_06_modo_contingencia_no_falla(self):
        alts = generar_alternativas_pura(AÑO, MES, '2x2x2', 'CO',
                                         num_alternativas=2, modo='contingencia')
        self.assertEqual(len(alts), 2)

    def test_07_turnos_dentro_del_dominio(self):
        alts = generar_alternativas_pura(AÑO, MES, '2x2x2', 'CO', num_alternativas=1)
        validos = {'M', 'T', 'N', 'L', 'V', 'PNR', 'IM', 'CD'}
        reales = set(alts[0]['df']['turno'].unique())
        self.assertTrue(reales.issubset(validos),
                        f"Turnos inválidos: {reales - validos}")

    def test_08_ciclo_4x2_funciona(self):
        alts = generar_alternativas_pura(AÑO, MES, '4x2', 'CO', num_alternativas=2)
        self.assertEqual(len(alts), 2)
        self.assertFalse(alts[0]['df'].empty)


# ══════════════════════════════════════════════════════════════
# PASO 3 – Integración ausencias + balanceo
# ══════════════════════════════════════════════════════════════

class Paso3_IntegracionAusencias(BaseTestCase):

    def test_01_aplicar_contingencia_retorna_df(self):
        from src import ausencias
        self._generar_calendario_en_bd()
        self._registrar_ausencia_p1()
        df, acciones = ausencias.aplicar_contingencia(AÑO, MES)
        self.assertIsNotNone(df)
        self.assertIsInstance(df, pd.DataFrame)
        self.assertIsInstance(acciones, list)

    def test_02_ausencia_en_df_como_turno_V(self):
        from src import ausencias
        self._generar_calendario_en_bd()
        self._registrar_ausencia_p1()
        df, _ = ausencias.aplicar_contingencia(AÑO, MES)
        for dia in ['10', '11', '12']:
            fecha = f"{AÑO}-{MES:02d}-{dia}"
            t = df[(df['persona_id'] == 1) & (df['fecha'] == fecha)]['turno'].values
            self.assertTrue(len(t) > 0, f"No hay turno para persona 1 en {fecha}")
            self.assertEqual(t[0], 'V', f"Esperado V en {fecha}, obtenido {t[0]}")

    def test_03_ausencia_persiste_en_bd(self):
        from src import ausencias, database
        self._generar_calendario_en_bd()
        self._registrar_ausencia_p1()
        ausencias.aplicar_contingencia(AÑO, MES)
        with database.get_connection() as conn:
            cur = conn.execute(
                "SELECT turno FROM calendario WHERE persona_id=1 AND fecha=?",
                (f"{AÑO}-{MES:02d}-10",))
            row = cur.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], 'V')

    def test_04_sin_ausencias_acciones_vacias(self):
        from src import ausencias
        self._generar_calendario_en_bd()
        df, acciones = ausencias.aplicar_contingencia(AÑO, MES)
        self.assertEqual(acciones, [])

    def test_05_sin_calendario_retorna_none(self):
        from src import ausencias
        df, acciones = ausencias.aplicar_contingencia(AÑO, MES)
        self.assertIsNone(df)

    def test_06_a_df_no_modifica_bd(self):
        from src import ausencias, database
        df_base = self._generar_calendario_en_bd()
        self._registrar_ausencia_p1()
        with database.get_connection() as conn:
            cur = conn.execute(
                "SELECT turno FROM calendario WHERE persona_id=1 AND fecha=?",
                (f"{AÑO}-{MES:02d}-10",))
            turno_original = cur.fetchone()[0]
        ausencias.aplicar_contingencia_a_df(
            self._generar_calendario_df(), AÑO, MES)
        with database.get_connection() as conn:
            cur = conn.execute(
                "SELECT turno FROM calendario WHERE persona_id=1 AND fecha=?",
                (f"{AÑO}-{MES:02d}-10",))
            turno_bd = cur.fetchone()[0]
        self.assertEqual(turno_bd, turno_original,
                         "aplicar_contingencia_a_df NO debe alterar la BD")

    def test_07_balanceo_invocado_en_a_df(self):
        from src import ausencias, balanceo
        df_base = self._generar_calendario_df()
        llamadas = []
        original = balanceo.aplicar_balanceo

        def spy(df, a, m):
            llamadas.append((a, m))
            return original(df, a, m)

        with patch.object(balanceo, 'aplicar_balanceo', side_effect=spy):
            ausencias.aplicar_contingencia_a_df(df_base, AÑO, MES)

        self.assertEqual(len(llamadas), 1,
                         "aplicar_balanceo debe invocarse 1 vez")
        self.assertEqual(llamadas[0], (AÑO, MES))

    def test_08_balanceo_invocado_en_contingencia_bd(self):
        from src import ausencias, balanceo
        self._generar_calendario_en_bd()
        llamadas = []
        original = balanceo.aplicar_balanceo

        def spy(df, a, m):
            llamadas.append(1)
            return original(df, a, m)

        with patch.object(balanceo, 'aplicar_balanceo', side_effect=spy):
            ausencias.aplicar_contingencia(AÑO, MES)

        self.assertGreaterEqual(len(llamadas), 1,
                                "aplicar_balanceo debe invocarse en aplicar_contingencia")

    def test_09_fallo_balanceo_no_propaga_excepcion(self):
        """
        Si balanceo falla, ausencias.py debe absorberlo (requiere try/except).
        Si este test FALLA → agregar try/except alrededor del balanceo en ausencias.py.
        """
        from src import ausencias, balanceo

        def balanceo_roto(df, a, m):
            raise RuntimeError("Error simulado")

        with patch.object(balanceo, 'aplicar_balanceo', side_effect=balanceo_roto):
            try:
                df, _ = ausencias.aplicar_contingencia_a_df(
                    self._generar_calendario_df(), AÑO, MES)
                # ✓ try/except ya implementado
                self.assertIsInstance(df, pd.DataFrame)
            except RuntimeError:
                self.fail(
                    "❌ ausencias.py no protege el balanceo con try/except. "
                    "Añadir:\n"
                    "  try:\n"
                    "      df = balanceo.aplicar_balanceo(df, año, mes)\n"
                    "  except Exception as e:\n"
                    "      logging.warning(f'[balanceo] No crítico: {e}')"
                )

    def test_10_fallo_guardar_balanceo_bd_no_propaga(self):
        from src import ausencias, balanceo
        self._generar_calendario_en_bd()

        def guardar_roto(df, a, m):
            raise Exception("Error simulado al guardar")

        with patch.object(balanceo, 'guardar_balanceo_en_bd', side_effect=guardar_roto):
            try:
                df, _ = ausencias.aplicar_contingencia(AÑO, MES)
                self.assertIsNotNone(df)
            except Exception as e:
                self.fail(
                    f"❌ ausencias.py no protege guardar_balanceo_en_bd. "
                    f"Error: {e}\nAñadir try/except alrededor de la llamada."
                )


# ══════════════════════════════════════════════════════════════
# PASO 4 – Equidad matemática (diferencia ≤ 1)
# ══════════════════════════════════════════════════════════════

class Paso4_EquidadBalanceo(BaseTestCase):

    def _dias_especiales(self):
        from src import balanceo
        return balanceo.obtener_dias_especiales(AÑO, MES)

    # ── Suite A: calendario real ──────────────────────────────

    def test_01_diferencia_le_1_tras_balanceo(self):
        from src import balanceo
        dias = self._dias_especiales()
        if not dias: self.skipTest("Sin días especiales")
        df = self._generar_calendario_df()
        df_bal = balanceo.aplicar_balanceo(df.copy(), AÑO, MES)
        diff = self._diferencia_carga(self._calcular_carga(df_bal, dias))
        self.assertLessEqual(diff, 1,
            f"Diferencia tras balanceo = {diff}. Cargas: "
            f"{self._calcular_carga(df_bal, dias)}")

    def test_02_total_turnos_trabajados_conservado(self):
        from src import balanceo
        dias = self._dias_especiales()
        if not dias: self.skipTest("Sin días especiales")
        df = self._generar_calendario_df()
        total_antes  = sum(self._calcular_carga(df, dias).values())
        df_bal = balanceo.aplicar_balanceo(df.copy(), AÑO, MES)
        total_despues = sum(self._calcular_carga(df_bal, dias).values())
        self.assertEqual(total_antes, total_despues,
            f"Se perdieron/ganaron turnos: {total_antes} → {total_despues}")

    # ── Suite B: casos sintéticos ─────────────────────────────

    def test_03_toda_carga_en_persona_1(self):
        from src import balanceo
        dias = self._dias_especiales()
        if not dias: self.skipTest("Sin días especiales")
        asig = {1: 'M', 2: 'L', 3: 'L', 4: 'L', 5: 'L', 6: 'L'}
        df = self._df_sintetico(asig)
        df_bal = balanceo.aplicar_balanceo(df, AÑO, MES)
        diff = self._diferencia_carga(self._calcular_carga(df_bal, dias))
        self.assertLessEqual(diff, 1,
            f"Balanceo no resolvió carga extrema. Diff={diff}")

    def test_04_desequilibrio_moderado_M_vs_libre(self):
        """
        Personas 1,2,3 trabajan turno M en días especiales;
        personas 4,5,6 están libres. Turno M no genera conflicto N→M,
        así que todos los intercambios son válidos y el balanceo
        debe alcanzar diferencia ≤ 1.
        """
        from src import balanceo
        dias = self._dias_especiales()
        if len(dias) < 2: self.skipTest("Se necesitan ≥ 2 días especiales")
        asig = {1: 'M', 2: 'M', 3: 'M', 4: 'L', 5: 'L', 6: 'L'}
        df = self._df_sintetico(asig)
        df_bal = balanceo.aplicar_balanceo(df, AÑO, MES)
        diff = self._diferencia_carga(self._calcular_carga(df_bal, dias))
        self.assertLessEqual(diff, 1,
            f"Diferencia tras balanceo = {diff}")

    def test_04b_turno_N_bloqueado_por_restriccion_documentado(self):
        """
        LIMITACIÓN CONOCIDA: cuando los días especiales son todos N y los días
        adyacentes son M (en el DataFrame sintético), la restricción N→M bloquea
        casi todos los intercambios. El algoritmo hace lo que puede dentro de
        las reglas del dominio: reduce la diferencia pero no siempre llega a ≤ 1.

        Este test documenta y verifica ese comportamiento esperado:
        la diferencia DEBE reducirse respecto al estado inicial.
        """
        from src import balanceo
        dias = self._dias_especiales()
        if len(dias) < 2: self.skipTest("Se necesitan ≥ 2 días especiales")
        asig = {1: 'N', 2: 'N', 3: 'N', 4: 'L', 5: 'L', 6: 'L'}
        df = self._df_sintetico(asig)

        diff_antes = self._diferencia_carga(self._calcular_carga(df, dias))
        df_bal = balanceo.aplicar_balanceo(df.copy(), AÑO, MES)
        diff_despues = self._diferencia_carga(self._calcular_carga(df_bal, dias))

        self.assertLess(diff_despues, diff_antes,
            f"El balanceo debería reducir la diferencia aunque no pueda "
            f"llegar a ≤ 1 por restricción N→M. "
            f"Antes={diff_antes}, Después={diff_despues}")

    def test_05_ya_balanceado_no_modifica(self):
        from src import balanceo
        dias = self._dias_especiales()
        if not dias: self.skipTest("Sin días especiales")
        asig = {pid: 'L' for pid in GRUPO_A_IDS}  # todos libres = equilibrado
        df = self._df_sintetico(asig)
        df_antes = df.copy()
        df_bal = balanceo.aplicar_balanceo(df, AÑO, MES)
        pd.testing.assert_frame_equal(
            df_bal[['persona_id','fecha','turno']].sort_values(['persona_id','fecha']).reset_index(drop=True),
            df_antes[['persona_id','fecha','turno']].sort_values(['persona_id','fecha']).reset_index(drop=True),
        )

    def test_06_balanceo_idempotente(self):
        from src import balanceo
        dias = self._dias_especiales()
        if not dias: self.skipTest("Sin días especiales")
        df = self._generar_calendario_df()
        df1 = balanceo.aplicar_balanceo(df.copy(), AÑO, MES)
        df2 = balanceo.aplicar_balanceo(df1.copy(), AÑO, MES)
        c1 = self._calcular_carga(df1, dias)
        c2 = self._calcular_carga(df2, dias)
        self.assertEqual(c1, c2,
            f"No idempotente.\n1ra: {c1}\n2da: {c2}")

    # ── Suite C: invariantes ──────────────────────────────────

    def test_07_no_viola_regla_N_seguido_M(self):
        from src import balanceo
        df = self._generar_calendario_df()
        df_bal = balanceo.aplicar_balanceo(df.copy(), AÑO, MES)
        for pid in GRUPO_A_IDS:
            sub = df_bal[df_bal['persona_id'] == pid].sort_values('fecha')
            turnos = list(sub['turno'])
            fechas = list(sub['fecha'])
            for i in range(len(turnos) - 1):
                self.assertFalse(turnos[i] == 'N' and turnos[i+1] == 'M',
                    f"Violación N→M: persona {pid} en {fechas[i]}→{fechas[i+1]}")

    def test_08_solo_modifica_grupo_a(self):
        from src import balanceo
        dias = self._dias_especiales()
        df = self._generar_calendario_df()
        df_antes = df.copy()
        df_bal = balanceo.aplicar_balanceo(df.copy(), AÑO, MES)
        for pid in [7, 8]:
            for fecha in dias:
                t_ant = df_antes[(df_antes['persona_id']==pid)&(df_antes['fecha']==fecha)]['turno']
                t_dep = df_bal [(df_bal ['persona_id']==pid)&(df_bal ['fecha']==fecha)]['turno']
                if not t_ant.empty and not t_dep.empty:
                    self.assertEqual(t_ant.iloc[0], t_dep.iloc[0],
                        f"Balanceo modificó Grupo B (persona {pid}) en {fecha}")

    def test_09_no_introduce_turnos_invalidos(self):
        from src import balanceo
        validos = {'M', 'T', 'N', 'L', 'V', 'PNR', 'IM', 'CD'}
        df = self._generar_calendario_df()
        df_bal = balanceo.aplicar_balanceo(df.copy(), AÑO, MES)
        invalidos = set(df_bal['turno'].unique()) - validos
        self.assertFalse(invalidos,
            f"Turnos inválidos introducidos: {invalidos}")

    def test_10_dias_normales_no_cambian(self):
        from src import balanceo, ciclos
        dias_especiales = set(balanceo.obtener_dias_especiales(AÑO, MES))
        dias_normales = {
            d.isoformat() for d in ciclos.generar_rango_fechas(AÑO, MES)
        } - dias_especiales
        df = self._generar_calendario_df()
        df_antes = df.copy()
        df_bal = balanceo.aplicar_balanceo(df.copy(), AÑO, MES)
        for fecha in dias_normales:
            for pid in GRUPO_A_IDS:
                ta = df_antes[(df_antes['persona_id']==pid)&(df_antes['fecha']==fecha)]['turno']
                td = df_bal  [(df_bal  ['persona_id']==pid)&(df_bal  ['fecha']==fecha)]['turno']
                if not ta.empty and not td.empty:
                    self.assertEqual(ta.iloc[0], td.iloc[0],
                        f"Día normal {fecha} persona {pid} fue modificado: "
                        f"{ta.iloc[0]} → {td.iloc[0]}")

    def test_11_guardar_balanceo_en_bd(self):
        from src import balanceo, database
        self._generar_calendario_en_bd()
        dias = self._dias_especiales()
        if not dias: self.skipTest("Sin días especiales")
        df_bd = self._generar_calendario_en_bd()
        df_bal = balanceo.aplicar_balanceo(df_bd.copy(), AÑO, MES)
        balanceo.guardar_balanceo_en_bd(df_bal, AÑO, MES)
        fecha_ref = dias[0]
        with database.get_connection() as conn:
            cur = conn.execute(
                "SELECT persona_id, turno FROM calendario "
                "WHERE fecha=? AND persona_id BETWEEN 1 AND 6",
                (fecha_ref,))
            bd_map = {r[0]: r[1] for r in cur.fetchall()}
        for pid in GRUPO_A_IDS:
            t_df = df_bal[(df_bal['persona_id']==pid)&(df_bal['fecha']==fecha_ref)]['turno']
            if not t_df.empty and pid in bd_map:
                self.assertEqual(bd_map[pid], t_df.iloc[0],
                    f"Desincronización BD/DF persona {pid} en {fecha_ref}: "
                    f"BD='{bd_map[pid]}' DF='{t_df.iloc[0]}'")

    # ── Reporte final ─────────────────────────────────────────

    def test_12_reporte_equidad(self):
        from src import balanceo
        dias = self._dias_especiales()
        if not dias: self.skipTest("Sin días especiales")
        df = self._generar_calendario_df()
        carga_antes  = self._calcular_carga(df, dias)
        df_bal = balanceo.aplicar_balanceo(df.copy(), AÑO, MES)
        carga_despues = self._calcular_carga(df_bal, dias)

        sep = "═" * 55
        print(f"\n{sep}")
        print(f"  REPORTE DE EQUIDAD — {MES:02d}/{AÑO}")
        print(f"  Días especiales del mes: {len(dias)}")
        print(f"  Fechas: {', '.join(dias)}")
        print(sep)
        print(f"  {'Persona':<12} {'Antes':>6} {'Después':>8} {'Δ':>5}")
        print(f"  {'-'*35}")
        for pid in GRUPO_A_IDS:
            d = carga_despues[pid] - carga_antes[pid]
            s = '+' if d > 0 else ''
            print(f"  A{pid:<11} {carga_antes[pid]:>6} {carga_despues[pid]:>8} {s}{d:>4}")
        print(f"  {'-'*35}")
        print(f"  Diferencia antes:   {self._diferencia_carga(carga_antes)}")
        print(f"  Diferencia después: {self._diferencia_carga(carga_despues)}")
        print(sep)

        self.assertLessEqual(self._diferencia_carga(carga_despues), 1)


# ══════════════════════════════════════════════════════════════
# Runner principal
# ══════════════════════════════════════════════════════════════

if __name__ == '__main__':
    loader = unittest.TestLoader()
    suite  = unittest.TestSuite()

    for cls in [Paso1_Importaciones, Paso3_IntegracionAusencias, Paso4_EquidadBalanceo]:
        suite.addTests(loader.loadTestsFromTestCase(cls))

    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
    result = runner.run(suite)

    # Resumen legible
    total   = result.testsRun
    errores = len(result.errors)
    fallos  = len(result.failures)
    saltos  = len(result.skipped)
    ok      = total - errores - fallos - saltos

    print("\n" + "═"*55)
    print(f"  RESUMEN FINAL")
    print("═"*55)
    print(f"  Total tests:  {total}")
    print(f"  ✅ Pasados:   {ok}")
    print(f"  ⚠️  Saltados: {saltos}")
    print(f"  ❌ Fallos:    {fallos}")
    print(f"  💥 Errores:   {errores}")
    print("═"*55)

    if result.failures or result.errors:
        print("\n  DETALLE DE FALLOS/ERRORES:")
        for test, msg in result.failures + result.errors:
            print(f"\n  [{test}]\n  {msg.strip()}")

    sys.exit(0 if result.wasSuccessful() else 1)