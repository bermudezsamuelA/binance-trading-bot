"""Registro de las configuraciones nuevas de la fase 3 (v2) con harness.log_trials."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nn_common as C
H = C.H
E = [
    (5, "fase3 v2 geometrias de salida X1(0.6,1.5,192) X2(0.8,2.0,288) X3(0.75,1.5,288) X4(1.0,2.0,288) X5(0.7,1.75,288): estadisticas del azar"),
    (4, "fase3 v2 ENS6 (etiqueta G3) con umbral WR_val>=0.75 y salida G3, X1, X3, X5"),
    (5, "fase3 v2 ENS6 salida X2 y X4 (wr>=.75); X5 wr>=.80; X5 wr>=.80 max n; X5 con filtro BTC>SMA30d"),
    (1, "fase3 v2 re-ejecucion con purga de la geometria de salida corregida (X1-X5, X5 max n)"),
    (3, "fase3 v2 ENS12 (6 LGB + 6 MLP) X5; ENS6+CNN X5; ENS12+CNN X5"),
    (2, "fase3 v2 ablacion sin futuros (LGB+MLP+CNN) X5; placebo futuros +1 h ENS6 X5"),
]
for n, d in E:
    H.log_trials("constructor", n, d)
print("registradas", sum(n for n, _ in E))
