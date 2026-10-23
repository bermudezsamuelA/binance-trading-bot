"""Corrige duplicados en el conteo del equipo: las 6 894 configs de R1 ya las registro el Validador (00:06:34)
y la variante C48 quedo registrada dos veces (re-ejecucion de riesgo_r2_c1 al importarlo)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H
H.log_trials("riesgo", -6895, "CORRECCION: anula duplicados (R1 6894 ya registrado por el Validador 00:06:34; C48 duplicada). Total riesgo = 6894 + 294 control + 1 (C48) = 7189", "design")
