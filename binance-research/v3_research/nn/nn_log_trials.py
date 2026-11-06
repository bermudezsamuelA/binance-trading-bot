"""Registro de TODAS las configuraciones probadas por el Constructor en la fase 1 (harness.log_trials)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nn_common as C
H = C.H
E = [
    (5, "fase1 geometrias triple barrera G1(0.5,1.0,96) G2(0.4,1.2,96) G3(0.75,1.5,192) G4(0.4,1.2,192) G5(0.6,1.5,192) en sd diaria; estadisticas del azar (sin modelo)"),
    (4, "fase1 v1 LightGBM meta-etiquetado todas las velas, G3/G4 x con/sin futuros, parada por logloss, WF trimestral 2024Q1-2025Q2"),
    (4, "fase1 v2 LightGBM parada por AUC, umbral val WR>=0.70 y >=15 dias, G3/G4 x con/sin futuros"),
    (4, "fase1 v2 MLP G3 futuros (2 corridas, una abortada), ensamble LGB+MLP G3, CNN G3 abortada"),
    (12, "fase1 v3 (retardo metrics T<=t_i+5m) LGB y MLP x G3/G4 x con/sin futuros + 4 ensambles LGB+MLP"),
    (6, "fase1 v3 semillas extra LGB/MLP G3 futuros (4) y CNN v3 G3 con/sin futuros abortadas (2)"),
    (15, "fase1 v4 (regla huecos del Verificador) G3 fut: LGB, MLP, LGBx3, MLPx3, ENS6, ENS s0; G3 sin fut: LGB, MLP, ENS; G5 fut: LGB, MLP, ENS; G5 sin fut: ENS (+2 modelos)"),
    (3, "fase1 v4 CNN 1D dilatada G3 con/sin futuros y ENS6+CNN"),
    (1, "fase1 placebo: futuros retrasados 1 h, ENS6 G3"),
]
for n, d in E:
    H.log_trials("constructor", n, d)
print("registradas", sum(n for n, _ in E), "configuraciones")
