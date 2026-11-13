"""Registra en el conteo del equipo (harness.log_trials) las configuraciones del Gestor de Riesgo de la ronda 1."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H
H.log_trials("riesgo", 3447, "R1 frontera 15m: entradas MR/BO (n 20/48/96 x k 1.5/2/2.5) x salidas ATR/PATH/MEAN/CHAN/PART/BOT (riesgo_frontera.py 1)", "design")
H.log_trials("riesgo", 3447, "R1 frontera 1h (agregada de 15m): misma rejilla (riesgo_frontera.py 4); R2 walk-forward 12/3/3 reutiliza estas 3447", "design")
H.log_trials("riesgo", 0, "R1 controles RND (294 geometrias con entradas aleatorias; no son hipotesis) y R2 nota: la fila 'R2 C1 variante C48' se duplico por re-ejecucion, cuenta 1", "design")
