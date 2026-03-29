from src import balanceo, ciclos
from datetime import date

def test_especiales(mes):
    especiales = balanceo.obtener_dias_especiales(2026, mes)
    festivos = ciclos.obtener_festivos(2026)
    print(f"Mes {mes}: {len(especiales)} días especiales")
    for f in especiales:
        d = date.fromisoformat(f)
        print(f"  {f} ({d.strftime('%A')}) - festivo: {d in festivos}")
    return especiales

if __name__ == "__main__":
    marzo = test_especiales(3)
    abril = test_especiales(4)
    # Verificación manual: domingos de marzo 2026: 1,8,15,22,29 (5 domingos)
    # Festivos en marzo: 23 (lunes) - Día de San José? Realmente en Colombia el 23 de marzo es festivo? Depende del año; confirmar con holidays.
    # Para abril: domingos 5,12,19,26 (4 domingos). Festivo: 1 de mayo (no en abril) y 9 de abril? Jueves Santo? No es festivo oficial. Solo domingos.
    # Se espera que el set incluya los domingos más algún festivo si lo hay.