# Laboratorio, ronda 1: iteraciones sobre la pila v2 + co-señal (solo diseño)

Fecha: 2026-10-16. Reloj: 00:43–01:05 (hora local). Todo en DISEÑO (pruebas walk-forward 2024-01..2025-06, BTC/ETH/SOL/DOGE); el *holdout* no se tocó. Nada se descargó.

## Resumen

- **Ninguna pieza cumple el criterio estricto** (ΔWR ≥ +1 pt y ΔE ≥ 0 sobre la pila, ≥ 4/6 pliegues que mejoran, réplica en ≥ 2/3 ensambles, P(Δ ≤ 0) ≤ 0.20, sin elegir con la prueba).
- **Una pieza pasa "con reserva": E7, alargar la barrera de tiempo de 288 a 384 velas (72 h → 96 h)** con el mismo TP 0.7·s_d y SL 1.75·s_d.
  - Con H = 384 fijo: **131 op., WR 87.8 % [81.1, 92.3], E +2.02 %** (pila: 85.5 %, +1.90 %). ΔWR **+2.3 pt**, ΔE **+0.12 %**, P(ΔWR ≤ 0) = 0.04 y P(ΔE ≤ 0) = 0.00.
  - Se replica en los 3 ensambles: ENS12 +3.4 pt / +0.21 %; ENS12U +3.3 pt / +0.11 %.
  - **Ningún pliegue empeora el WR**, pero solo 3 de 6 mejoran (los otros empatan, porque la regla solo toca las ~6 % de operaciones que salen por tiempo). Por eso **no** llega a 4/6.
  - La versión honesta, con H elegido en *walk-forward* con los pliegues anteriores, da **+1.5 pt / +0.07 %** (P 0.13 / 0.10). La idea se inspiró en que 288 > 192 en la rejilla de E1, o sea, en la prueba.
  - El efecto es sobre todo **estructural**: el azar condicionado sube 1.7 pt, y el efecto también aparece en la v2 sin compuerta (+1.6 a +2.9 pt). En ENS13 descansa en **3 operaciones**: de las 8 salidas por tiempo, 5 pasan a TP y ninguna a SL.
- **Casi candidatas** (≥ +2 pt con E ≥ 0 en ENS13 y réplica de signo en 3/3, pero inestables por pliegue y con n muy reducido): co-señal de BTC o ETH (G_BE), moneda que inicia el episodio (F_rank1), episodio aislado ≥ 3 días (E13) y régimen BTC > SMA de 30 días (E11; ENS12U no replica). Quedan como **hipótesis para datos nuevos**, no como piezas.
- **Frontera WR–E (*post hoc*, no candidata):** con un TP más corto o un TP decreciente para las operaciones lentas se compran **+3 a +6 pt de WR por ≈ −0.05 % de E**. Ejemplos: (0.6, 1.75, 384) da 89.5 % y +1.82 %; H 384 + TP2 = +0.6 % desde 36 h da 90.2 % y +1.86 %. Esta palanca existe si se acepta ΔE ligeramente negativo.
- **Se rechazan con claridad:**
  - re-entrada tras TP: −1 a −5 pt;
  - θ elegido en validación con la compuerta: −8 pt;
  - esperar la 2.ª señal o exigir que otra moneda haya señalado antes: ≤ 0;
  - segunda etapa logística, con o sin el rebote de las 18 monedas: ≈ 0;
  - cortacircuitos tras SL y tope de posiciones: ≈ 0 o negativo;
  - co-firma del ensamble con unicidad: ≈ 0.
- **Configuraciones registradas en `log_trials("bleeding_edge_r2")`: 132.**

## Método

- Común: `scripts/be2_common.py`, construido sobre `be_common.load_ens` y `be_common.simulate_entries` (alineación corregida), con los 3 ensambles: ENS13, ENS12 y ENS12U (ENS12 con pesos de unicidad).
- La pila se reproduce exactamente:
  - ENS13: 131 op. · 85.5 % · +1.90 %;
  - ENS12: 110 · 83.6 % · +1.69 %;
  - ENS12U: 341 · 78.6 % · +0.99 %.
  - El simulador conjunto por eventos (`be2_joint.py`, con `harness.resolve_exit`) y el de `be2_tpdecay.py` también la reproducen al 0.001 %.
- Δ incremental: (regla nueva) − (pila), con *bootstrap* de días (5 000 réplicas sobre la unión de días con operaciones de ambos conjuntos).
- Pliegue que "mejora": ΔWR > 0 y ΔE ≥ 0 en ese pliegue; "=" cuenta los empates exactos.
- Azar: misma moneda, mes y geometría. Azar condicionado: velas donde se cumplen A ≥ 1 y la parte de mercado de la regla.
- Episodios: días con operaciones, unidos si distan ≤ 2 días.
- Cada script lleva el pre-registro en su cabecera, escrito antes de correrlo.

## Tabla por experimento

Fila principal: ENS13. Las dos columnas de réplica dan ΔWR / ΔE frente a la pila de cada ensamble. Se compara siempre con la pila v2 + A ≥ 1, W = 48, X5 (n = 131, 85.5 %, +1.90 %).

| Exp. | Regla | n | WR % [Wilson] | E % | E_R | t día | Azar WR / E | Azar cond. WR / E | ΔWR / ΔE vs pila | P(ΔWR≤0) / P(ΔE≤0) | pliegues mejor (=empates) | episodios | ENS12 ΔWR / ΔE | ENS12U ΔWR / ΔE | candidata |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| E2/E3 | F_rank1 (primera moneda del episodio) | 49 | 89.8 [78.2, 95.6] | +2.12 | +0.221 | 4.16 | 60.2 / -0.61 | 77.3 / +0.82 | +4.3 / +0.22 | 0.11 / 0.24 | 3/6 (=0) | 21 | +4.9 / +0.37 | +2.6 / +0.24 | no |
| E2/E3 | F_rank2 (otra moneda dio señal antes) | 82 | 82.9 [73.4, 89.5] | +1.77 | +0.170 | 4.69 | 61.9 / -0.33 | 71.2 / +0.65 | -2.6 / -0.13 | 0.90 / 0.76 | 0/6 (=0) | 24 | -2.3 / -0.17 | -2.1 / -0.19 | no |
| E2/E3 | F_rank23 (2.ª o 3.ª moneda) | 70 | 84.3 [74.0, 91.0] | +1.88 | +0.188 | 5.04 | 61.1 / -0.35 | 69.2 / +0.42 | -1.2 / -0.02 | 0.72 / 0.54 | 3/6 (=0) | 24 | -0.8 / +0.02 | -2.5 / -0.15 | no |
| E2/E3 | F_tsf_le48 (≤ 12 h desde la 1.ª señal) | 59 | 88.1 [77.5, 94.1] | +1.95 | +0.224 | 3.33 | 61.7 / -0.45 | 73.5 / +0.52 | +2.6 / +0.04 | 0.26 / 0.45 | 4/6 (=0) | 19 | +4.7 / +0.11 | -6.4 / -0.89 | no |
| E2/E3 | F_tsf_gt48 (> 12 h desde la 1.ª señal) | 93 | 83.9 [75.1, 90.0] | +1.76 | +0.160 | 4.97 | 60.9 / -0.44 | 76.4 / +1.15 | -1.6 / -0.14 | 0.74 / 0.71 | 2/6 (=0) | 15 | -1.5 / -0.08 | +3.5 / +0.48 | no |
| E2/E3 | F_nprev0 (1.ª señal propia del episodio) | 47 | 76.6 [62.8, 86.4] | +1.01 | +0.109 | 1.82 | 63.8 / -0.26 | 73.2 / +0.58 | -8.9 / -0.89 | 0.98 / 0.99 | 1/6 (=0) | 24 | -6.1 / -0.90 | -10.5 / -1.21 | no |
| E2/E3 | F_nprev1 (señales propias previas ≥ 1) | 122 | 85.2 [77.9, 90.5] | +1.84 | +0.172 | 4.38 | 60.1 / -0.52 | 73.2 / +0.66 | -0.3 / -0.06 | 0.57 / 0.65 | 1/6 (=0) | 22 | -2.1 / -0.08 | +1.2 / +0.10 | no |
| E2/E3 | G_exc (suma de excesos ≥ mediana val.) | 64 | 87.5 [77.2, 93.5] | +1.69 | +0.189 | 5.71 | 63.6 / -0.17 | 79.8 / +1.29 | +2.0 / -0.22 | 0.24 / 0.74 | 2/6 (=0) | 10 | -1.3 / -0.12 | +6.0 / +0.55 | no |
| E2/E3 | G_BE (co-señal de BTC o ETH) | 99 | 87.9 [80.0, 92.9] | +2.16 | +0.221 | 7.31 | 62.7 / -0.33 | 83.0 / +1.82 | +2.4 / +0.26 | 0.14 / 0.18 | 3/6 (=0) | 21 | +1.6 / +0.19 | +2.4 / +0.08 | no |
| E2/E3 | G_prev (co-señal estrictamente anterior) | 130 | 85.4 [78.3, 90.4] | +1.87 | +0.188 | 5.26 | 60.6 / -0.49 | 72.7 / +0.65 | -0.1 / -0.03 | 0.65 / 0.64 | 1/6 (=0) | 24 | +0.0 / +0.01 | -0.3 / -0.01 | no |
| E2/E3 | G_p25 (p ≥ q25 val. con compuerta) | 107 | 86.0 [78.2, 91.3] | +2.08 | +0.188 | 4.82 | 60.6 / -0.42 | 73.9 / +0.80 | +0.5 / +0.18 | 0.40 / 0.19 | 1/6 (=0) | 19 | -0.3 / +0.20 | +1.6 / +0.10 | no |
| E2/E3 | G_p50 (p ≥ q50 val. con compuerta) | 83 | 84.3 [75.0, 90.6] | +2.04 | +0.183 | 4.19 | 60.2 / -0.44 | 72.1 / +0.64 | -1.2 / +0.14 | 0.64 / 0.33 | 2/6 (=0) | 17 | -1.8 / +0.09 | +3.6 / +0.25 | no |
| E1 | geometría WF (wr_guard) | 138 | 85.5 [78.7, 90.4] | +1.81 | +0.171 | 4.83 | 62.2 / -0.43 | 73.8 / +0.63 | +0.0 / -0.09 | 0.49 / 0.71 | 1/6 (=3) | 24 | -6.0 / -0.29 | +0.2 / -0.09 | no |
| E1 | geometría WF (maxE) | 118 | 78.8 [70.6, 85.2] | +1.95 | +0.197 | 4.21 | 55.4 / -0.46 | 66.2 / +0.66 | -6.7 / +0.05 | 1.00 / 0.40 | 1/6 (=1) | 24 | -6.9 / +0.02 | -2.6 / -0.03 | no |
| E4 | Re-entrada tras TP, señal activa L=48 | 175 | 80.6 [74.1, 85.8] | +1.24 | +0.134 | 3.32 | 62.3 / -0.37 | 74.4 / +0.79 | -4.9 / -0.66 | 0.97 / 1.00 | 1/6 (=0) | 24 | -4.3 / -0.60 | -2.3 / -0.26 | no |
| E4 | Re-entrada tras TP, señal activa L=16 | 153 | 82.4 [75.5, 87.6] | +1.41 | +0.155 | 3.43 | 61.4 / -0.45 | 73.8 / +0.70 | -3.1 / -0.50 | 0.90 / 0.97 | 2/6 (=0) | 24 | -3.0 / -0.49 | -1.3 / -0.12 | no |
| E5/E6 | LR5 q25 | 116 | 85.3 [77.8, 90.6] | +1.91 | +0.189 | 4.85 | 62.1 / -0.34 | 73.9 / +0.78 | -0.2 / +0.01 | 0.56 / 0.49 | 1/6 (=1) | 23 | -0.2 / -0.03 | +0.3 / +0.05 | no |
| E5/E6 | LR5 q50 | 100 | 83.0 [74.5, 89.1] | +1.71 | +0.154 | 4.07 | 61.4 / -0.39 | 73.2 / +0.73 | -2.5 / -0.20 | 0.93 / 0.84 | 1/6 (=1) | 21 | -1.0 / -0.05 | +1.8 / +0.17 | no |
| E5/E6 | LR6 (+rebote 18 monedas) q25 | 120 | 85.0 [77.5, 90.3] | +1.81 | +0.184 | 4.99 | 62.0 / -0.36 | 73.8 / +0.77 | -0.5 / -0.09 | 0.72 / 0.78 | 1/6 (=1) | 23 | -0.2 / +0.00 | +0.7 / +0.06 | no |
| E5/E6 | LR6 (+rebote 18 monedas) q50 | 96 | 84.4 [75.8, 90.3] | +1.87 | +0.174 | 4.29 | 61.9 / -0.33 | 73.3 / +0.77 | -1.1 / -0.03 | 0.71 / 0.54 | 1/6 (=1) | 21 | -0.6 / -0.02 | +1.0 / +0.12 | no |
| E7–E9 | CB_coin96 (sin la misma moneda 24 h tras SL) | 107 | 84.1 [76.0, 89.8] | +1.73 | +0.174 | 3.94 | 62.9 / -0.32 | 74.9 / +0.79 | -1.4 / -0.17 | 0.89 / 0.82 | 0/6 (=1) | 24 | +0.2 / -0.10 | -1.5 / -0.28 | no |
| E7–E9 | CB_mkt48 (sin entradas 12 h tras cualquier SL) | 117 | 85.5 [78.0, 90.7] | +1.91 | +0.192 | 4.73 | 62.4 / -0.35 | 74.6 / +0.77 | -0.0 / +0.00 | 0.51 / 0.47 | 1/6 (=2) | 24 | +3.0 / +0.26 | -2.0 / -0.23 | no |
| E7–E9 | MAX2 posiciones simultáneas | 113 | 84.1 [76.2, 89.7] | +1.87 | +0.184 | 4.53 | 60.2 / -0.52 | 72.6 / +0.66 | -1.4 / -0.03 | 0.79 / 0.54 | 1/6 (=1) | 25 | +0.1 / +0.06 | +2.1 / +0.18 | no |
| E7–E9 | MAX3 posiciones simultáneas | 127 | 85.0 [77.8, 90.2] | +1.81 | +0.183 | 4.91 | 60.9 / -0.47 | 73.3 / +0.68 | -0.5 / -0.09 | 1.00 / 0.98 | 0/6 (=2) | 24 | +0.0 / -0.01 | +0.1 / -0.04 | no |
| E7–E9 | E7 WF | 131 | 87.0 [80.2, 91.7] | +1.97 | +0.197 | 5.51 | 63.4 / -0.45 | 75.9 / +0.82 | +1.5 / +0.07 | 0.13 / 0.10 | 2/6 (=3) | 24 | +2.5 / +0.19 | +1.8 / +0.11 | no |
| E10/E11 | E10 co-firma de ENS12U (misma selectividad) | 75 | 85.3 [75.6, 91.6] | +2.05 | +0.176 | 5.66 | 58.1 / -0.68 | 70.2 / +0.42 | -0.2 / +0.15 | 0.53 / 0.31 | 3/6 (=1) | 13 | +1.5 / +0.14 | +2.7 / +0.49 | no |
| E10/E11 | E11 BTC > SMA 30 d | 61 | 90.2 [80.2, 95.4] | +2.24 | +0.256 | 5.57 | 67.8 / +0.07 | 77.7 / +1.12 | +4.7 / +0.34 | 0.09 / 0.17 | 2/6 (=0) | 13 | +9.1 / +0.60 | +0.4 / -0.01 | no |
| E12 | D1 TP2 = 0.35 s_d desde 36 h | 133 | 88.7 [82.2, 93.0] | +1.86 | +0.187 | 5.40 | 61.2 / -0.43 | – | +3.2 / -0.05 | 0.00 / 0.79 | 2/6 (=1) | 24 | +2.7 / -0.04 | +1.5 / -0.12 | no |
| E12 | D2 TP2 = +0.6 % desde 36 h | 133 | 90.2 [84.0, 94.2] | +1.86 | +0.193 | 5.45 | 61.2 / -0.43 | – | +4.7 / -0.05 | 0.00 / 0.69 | 2/6 (=1) | 24 | +4.7 / -0.07 | +4.4 / -0.04 | no |
| E12 | E7 control H=384 | 131 | 87.8 [81.1, 92.3] | +2.02 | +0.206 | 5.75 | 61.3 / -0.43 | – | +2.3 / +0.12 | 0.04 / 0.00 | 3/6 (=2) | 24 | +3.4 / +0.21 | +3.3 / +0.11 | no |
| E12 | E7 control H=576 | 131 | 87.8 [81.1, 92.3] | +1.99 | +0.201 | 5.62 | 61.3 / -0.43 | – | +2.3 / +0.09 | 0.04 / 0.06 | 3/6 (=2) | 24 | +3.4 / +0.12 | +4.1 / +0.17 | no |
| E13/E14 | E13 episodio ≥ 3 días después del anterior | 60 | 88.3 [77.8, 94.2] | +2.28 | +0.240 | 4.85 | 64.7 / -0.14 | 78.7 / +1.01 | +2.8 / +0.38 | 0.23 / 0.16 | 3/6 (=0) | 16 | +5.6 / +0.32 | +1.6 / +0.17 | no |
| E13/E14 | E14 θ elegido en validación con compuerta (WR_val ≥ 0.75) | 297 | 77.1 [72.0, 81.5] | +1.08 | +0.102 | 3.66 | 62.8 / -0.35 | 71.2 / +0.43 | -8.4 / -0.82 | 1.00 / 1.00 | 0/6 (=0) | 44 | -4.3 / -0.57 | -4.8 / -0.63 | no |
| E13/E14 | E14 θ elegido en validación con compuerta (WR_val ≥ 0.80) | 236 | 77.5 [71.8, 82.4] | +1.08 | +0.102 | 3.17 | 61.6 / -0.46 | 71.1 / +0.42 | -8.0 / -0.82 | 1.00 / 1.00 | 0/6 (=2) | 38 | -4.9 / -0.61 | -1.2 / -0.21 | no |
| E15 | E15 S1 pliegues anteriores | 133 | 87.2 [80.5, 91.9] | +1.86 | +0.169 | 5.29 | 66.2 / -0.46 | 78.3 / +0.87 | +1.7 / -0.04 | 0.11 / 0.60 | 2/6 (=2) | 24 | +2.9 / +0.07 | +4.2 / +0.02 | no |
| E15 | E15 S2 validación | 131 | 87.0 [80.2, 91.7] | +1.86 | +0.158 | 4.66 | 64.1 / -0.55 | 76.8 / +0.87 | +1.5 / -0.04 | 0.12 / 0.65 | 2/6 (=1) | 24 | +4.2 / +0.05 | +6.3 / +0.09 | no |

Detalle por pliegue, moneda y episodio de cada fila: `be2_*.md` en esta carpeta.

## Notas por experimento

### E1. Geometría condicionada a la compuerta (`be2_geom.py`, 30 geometrías × 2 selectores)

Rejilla en ENS13, **descriptiva**: elegir mirando esta tabla sería usar la prueba.

| (a, m, H) | n | WR % | E % | Azar condicionado WR / E | ν modelo / azar cond. / azar (s_d por día) |
|---|---|---|---|---|---|
| 0.4, 1.75, 288 | 191 | 93.2 | +1.17 | 82.2 / +0.32 | 0.51 / 0.18 / 0.05 |
| 0.5, 1.75, 288 | 168 | 91.1 | +1.46 | 78.7 / +0.46 | 0.49 / 0.18 / 0.06 |
| 0.6, 1.75, 288 | 153 | 88.9 | +1.78 | 75.5 / +0.57 | 0.47 / 0.18 / 0.06 |
| **0.7, 1.75, 288 (X5)** | **131** | **85.5** | **+1.90** | 73.5 / +0.71 | **0.43 / 0.18 / 0.06** |
| 0.7, 1.75, 192 | 135 | 82.2 | +1.84 | 70.0 / +0.57 | 0.51 / 0.19 / 0.11 |
| 0.7, 2.25, 288 | 132 | 85.6 | +1.76 | 75.4 / +0.71 | 0.33 / 0.19 / 0.08 |
| 0.9, 1.75, 288 | 119 | 80.7 | +2.26 | 67.9 / +0.89 | 0.37 / 0.16 / 0.06 |
| 0.9, 2.25, 288 | 120 | 82.5 | +2.30 | 70.5 / +0.95 | 0.34 / 0.19 / 0.08 |

**Qué muestra:**

- **Deriva implícita:** $\nu$ se obtiene invirtiendo $P(\text{TP antes que SL}) = (1-e^{2\nu m})/(e^{-2\nu a}-e^{2\nu m})$ con la fracción TP/(TP+SL).
  - Las operaciones del modelo con compuerta tienen ν ≈ **0.43 s_d/día** (ENS12: 0.45; ENS12U: 0.29).
  - El azar con compuerta tiene ≈ 0.18 y el azar sin compuerta ≈ 0.06.
  - La compuerta triplica la deriva del azar y el modelo la vuelve a duplicar.
- **Ninguna geometría de la rejilla domina a X5 en WR y E a la vez.** Bajar *a* sube el WR y baja la E de forma monótona.
- La elección en *walk-forward* no mejora:
  - el selector "WR con guarda de E" da +0.0 pt / −0.09 %;
  - el selector "máx. E" da −6.7 pt / +0.05 %.
  - Se replica en ENS12 y ENS12U.
- **Veredicto:** rechazada como pieza. Es una palanca de preferencias (WR frente a E), no una mejora.

### E2/E3. Orden en el episodio y variantes de compuerta (`be2_gatevar.py`, 12 reglas)

Descriptivo de las 131 operaciones de la pila (ENS13):

- **Por orden de la moneda en el episodio:** rank 1 → 90 % / +2.12 %; rank 2 → 80 % / +1.57 %; rank 3 → 92 % / +2.41 %; rank 4 → 75 % / +1.13 %.
- **Por señales propias previas en el episodio:** 0 → 77 % / +1.01 %; 1–3 → 86 %; ≥ 4 → 90–100 %.

**Lectura:**

- Filtrar por "no es la primera señal propia" (F_nprev1) **no sirve**: la entrada solo se retrasa una vela y el resultado es casi el mismo (−0.3 pt).
- El buen WR de las operaciones tardías es el de las **segundas operaciones del episodio**, tras cerrar la primera.
- Pero la re-entrada explícita **empeora** (E4).
- **F_rank1** (la moneda que inicia el pánico): +4.3 pt / +0.22 % con réplica 3/3. Pero deja 49 operaciones (−63 %), solo 3/6 pliegues mejoran y no hay operaciones de ETH.
- **G_BE** (la co-señal viene de BTC o ETH): +2.4 pt / +0.26 %, réplica 3/3, P 0.14 / 0.18, 3/6 pliegues.
- Ninguna de las dos pasa. Son las mejores hipótesis para datos nuevos.

### E4. Re-entrada tras TP (`be2_reentry.py`)

Las re-entradas, con la señal activa en las últimas L velas, ganan solo 77 % con E +0.05 a +0.43 %, y bajan la pila 3–5 pt. **Rechazada.**

### E5/E6. Segunda etapa logística (`be2_stage2.py`)

- **Variables:** A, p̂ − θ, máx. p̂ de las otras − θ, BTC 4 h, hora y, en LR6, la fracción de las 18 monedas *spot* rebotadas ≥ 1 σ de 4 h desde su mínimo de 4 h.
- Se entrena en WF solo con velas de la pila de los pliegues anteriores, con purga de 288 velas.
- **Resultado: Δ ≈ 0 en los tres ensambles.** Los coeficientes cambian de signo entre pliegues: p̂ − θ es positivo en los pliegues 1–2 y negativo en los 3–5.
- El rebote de las 18 monedas tiene un coeficiente negativo estable: comprar cuando aún no rebotó el mercado. En el descriptivo de ENS13, rebote < 0.1 da 97 % y +2.64 % frente a 79 % y +1.49 % con rebote ≥ 0.5. **Pero ENS12U lo invierte** (69 % con rebote < 0.1).
- **Rechazada como pieza.** El rebote del mercado queda como hipótesis.

### E7. Barrera de tiempo más larga (`be2_joint.py`, `be2_tpdecay.py` y `be2_v3.py`)

- Con H = 384, de las 8 salidas por tiempo de ENS13 (WR 37.5 %, E −0.16 %), 5 pasan a TP y 0 a SL; el resto sigue saliendo por tiempo.
- En conjunto, en los tres ensambles: **18 TP frente a 2 SL** entre las operaciones lentas que se resuelven entre 72 y 96 h.
- **Coherente con la deriva positiva** medida en E1.
- **Peor operación sin cambio** (−10.5 %). Tenencia media: 71 → 74 velas.
- En validación (resultado por vela de las señales con compuerta), H = 384 da un WR ≥ H = 288 en 16 de 17 pliegues × ensambles, casi siempre empatando.

### E8/E9. Cortacircuitos tras SL y tope de posiciones

| Regla | ENS13: ΔWR / ΔE | ENS12: ΔWR / ΔE | ENS12U: ΔWR / ΔE |
|---|---|---|---|
| Sin la misma moneda 24 h tras un SL | −1.4 / −0.17 | +0.2 / −0.10 | −1.5 / −0.28 |
| Sin entradas 12 h tras cualquier SL | 0.0 / 0.00 | +3.0 / +0.26 | −2.0 / −0.23 |
| MAX2 | −1.4 / −0.03 | +0.1 / +0.06 | +2.1 / +0.18 |
| MAX3 | −0.5 / −0.09 | 0.0 / −0.01 | +0.1 / −0.04 |

- MAX3 sigue siendo la **regla de riesgo** recomendada (sección 3.3 del documento): cuesta ≈ 0.1 % de E en diseño.
- **Ninguna sube el WR.**

### E10/E11. Co-firma de otro ensamble y régimen de BTC

- **Co-firma de ENS12U** con la misma selectividad: −0.2 pt en ENS13. Rechazada.
- **BTC > SMA de 30 días:** +4.7 pt / +0.34 % en ENS13 y +9.1 pt / +0.60 % en ENS12, pero +0.4 pt / −0.01 % en ENS12U. Solo 2/6 pliegues en ENS13 y la mitad de las operaciones.
  - Además, el *holdout* fue bajista: el filtro habría apagado la estrategia, lo que sí reduce el riesgo, pero no es una mejora del WR demostrable aquí.
  - **No candidata.**

### E12. TP decreciente para operaciones lentas (desde 36 h)

- D1 (TP2 = 0.35 s_d) y D2 (TP2 = +0.6 %) suben el WR **+3 a +5 pt en los tres ensambles** (P(ΔWR ≤ 0) ≈ 0.00), con **ΔE de −0.04 a −0.12 %**.
- Es la palanca de WR más barata encontrada, pero **incumple ΔE ≥ 0**.
- No es "stop a equilibrio" (el SL no se mueve) ni toma parcial.

### E13/E14

- **E13 (episodio que empieza ≥ 3 días después del anterior):** +2.8 pt / +0.38 % en ENS13; réplica +5.6 y +1.6 pt. Pero P 0.23 / 0.16, 3/6 pliegues y n = 60. No candidata.
- **E14 (θ elegido en validación con la compuerta):** baja θ y pierde −8 pt. **Rechazada:** confirma que no se debe relajar θ con la compuerta.

### E15. Geometría con H largo elegida fuera de la prueba (18 geometrías × 2 selectores)

- En ENS13: +1.7 y +1.5 pt de WR, pero **ΔE −0.04 %**.
- En ENS12 y ENS12U: +2.9 a +6.3 pt con ΔE de +0.02 a +0.09 %.
- No candidata: E < 0 en ENS13 y 2/6 pliegues. Ampliar la rejilla no supera a cambiar solo H.

## Mejoras candidatas

| Pieza | Estado | Motivo |
|---|---|---|
| — | **Ninguna cumple el criterio estricto** | — |
| E7, H 288 → 384 | **Candidata con reserva** | Cumple ΔWR ≥ +1, ΔE ≥ 0, P ≤ 0.20 y réplica 3/3; ningún pliegue empeora el WR, pero solo 3/6 mejoran (2–3 empates). La versión WF da +1.5 pt / +0.07 % con P 0.13 / 0.10. La idea surgió de la rejilla E1, o sea, de la prueba. El efecto en ENS13 descansa en 3 operaciones. |

## Pila v3 (medida una vez, sin re-optimizar)

**Definición:** pila v2 + A ≥ 1 (W = 48) con barrera de tiempo **H = 384**. Ese H es el que elige el selector WF "WR con guarda de E" con los 6 pliegues de ENS13: 384 y 576 empatan en WR y 384 tiene más E.

| Ensamble | Pila | n | WR % [Wilson] | E % | E_R | t día | Azar / azar cond. (WR, E) | ΔWR / ΔE vs pila | P(Δ ≤ 0) | Pliegues: mejoran / empatan / otros | Episodios (WR) | Meses + |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ENS13 | Actual (X5) | 131 | 85.5 [78.5, 90.5] | +1.90 | +0.189 | 5.30 | 61.3 / −0.43 · 73.5 / +0.71 | — | — | — | 24 (83 %) | 15/15 |
| ENS13 | **v3 (H 384)** | **131** | **87.8 [81.1, 92.3]** | **+2.02** | **+0.206** | **5.75** | 63.2 / −0.42 · 75.2 / +0.83 | **+2.3 / +0.12** | 0.04 / 0.00 | 3 / 2 / 1 (WR igual, E +0.05) | 24 (92 %) | 15/15 |
| ENS13 | v3 con BNB (0.19 %) | 131 | 87.8 | +2.07 | +0.213 | 5.90 | — | +2.3 / +0.17 | 0.04 / 0.00 | — | 24 | 15/15 |
| ENS13 | v3 en WF (H elegido con pliegues anteriores) | 131 | 87.0 [80.2, 91.7] | +1.97 | +0.197 | 5.51 | 63.4 / −0.45 · 75.9 / +0.82 | +1.5 / +0.07 | 0.13 / 0.10 | 2 / 3 / 1 (WR igual, E −0.12) | 24 (88 %) | — |
| ENS12 | v3 (H 384) | 108 | 87.0 [79.4, 92.1] | +1.90 | +0.208 | 4.99 | 63.6 / −0.37 · 76.6 / +0.92 | +3.4 / +0.21 | 0.01 / 0.00 | 3 / 2 / 1 (WR igual, E +0.06) | 19 (89 %) | 12/13 |
| ENS12U | v3 (H 384) | 336 | 81.8 [77.4, 85.6] | +1.09 | +0.124 | 4.21 | 67.0 / −0.21 · 74.9 / +0.41 | +3.3 / +0.11 | 0.00 / 0.01 | 3 / 0 / 2 (uno con WR +1 y E −0.03; otro con WR igual y E +0.12); el pliegue 6 no tiene operaciones | 33 (76 %) | 14/15 |

- **Por moneda, ENS13 v3:** BTC 29 · 93 % · +1.32; ETH 25 · 92 % · +1.96; SOL 39 · 85 % · +1.93; DOGE 38 · 84 % · +2.68. Las 4 monedas son iguales o mejores que con X5.
- **Δ por pliegue, ENS13 (WR pt / E %):** +8/+0.14, 0/0, +3/+0.18, +4/+0.24, 0/0, 0/+0.05.
- **Comprobación de que es estructural:** en la v2 sin compuerta, H 384 da +1.6 / +2.6 / +2.9 pt; en las señales aisladas, 0 / +1.1 / +1.9 pt.
- **Costo:** se mantiene la posición hasta 4 días en lugar de 3, y el capital queda inmovilizado un ≈ 5 % más de tiempo.

## Estimación honesta fuera de muestra

- **Base:** la pila actual se estima fuera de muestra en **72–78 % y +0.6 a +1.1 %** (estimación del Juez).
- **Factores de encogimiento observados antes:**
  - la ventaja de la v2 sobre el azar pasó de +19.7 pt en diseño a +9.4 pt en monedas nuevas, es decir, se retuvo **≈ 48 %**;
  - para la co-señal se supuso una retención del 50–75 %.
- **Dos partes del efecto de E7:**
  - **La parte estructural** (≈ +1.7 de los +2.3 pt; el azar condicionado sube lo mismo) viene de la geometría: una operación lenta que sigue abierta tiene P(TP primero) ≈ m/(a+m) = 71 % aun con deriva nula, frente al 37.5 % de WR de las salidas por tiempo. Debería transferirse en un **70–100 %** mientras la deriva fuera de muestra no sea negativa. En el *holdout* bajista, el azar X5 ganaba ≈ 60 %, como en diseño (61.7 %).
  - **La parte propia del modelo** (≈ +0.6 pt) se encoge como la v2: **≈ 50 %**.
- **Cálculo, combinando ambas partes:**
  - con la versión WF (+1.5 pt): +0.9 a +1.4 pt;
  - con la regla fija (+2.3 pt): +1.2 a +1.9 pt.
  - **Estimación: +1 a +1.5 pt de WR.**
- **E: de 0 a +0.1 %.** En el azar, alargar H no cambió la E (−0.43 → −0.42 %). Con deriva negativa, en un mercado bajista, el beneficio en E puede desaparecer.
- **Pila v3 esperada fuera de muestra: WR ≈ 73–79 %, E ≈ +0.6 a +1.2 % por operación.** No alcanza el 80 % demostrable. Su base es frágil: unas pocas operaciones lentas por año.

## Para la ronda 2: qué haría falta

1. **Más episodios, no más reglas.** Hay 24 episodios en diseño, y casi todas las ideas fallan por inestabilidad entre pliegues con n de 50–100.
   - Con datos de otra fuente (futuros y *spot* de 2021–2022 de un *exchange* distinto de Binance) se podrían re-probar G_BE, F_rank1, E13, el rebote del mercado y E7, y hacer la prueba de estrés de LUNA y FTX.
   - Advertencia: el modelo usa variables de futuros de Binance. Las de otra fuente cambian la distribución, así que habría que re-calibrar.
2. **E7 en régimen bajista:** verificar si las operaciones lentas también terminan en TP cuando la deriva del mercado es negativa (2022).
3. **Decisión de preferencias:** la frontera WR–E (H 384 + TP decreciente, o (0.6, 1.75, 384)) da +5 a +6 pt de WR por ≈ −0.05 % de E. Si el usuario prioriza el WR, se puede pre-registrar como brazo secundario. Es *post hoc*: necesita una prueba prospectiva propia.

## Archivos

- **Scripts** (`scripts/`): `be2_common.py`, `be2_geom.py`, `be2_gatevar.py`, `be2_reentry.py`, `be2_stage2.py`, `be2_joint.py`, `be2_extra.py`, `be2_tpdecay.py`, `be2_extra2.py`, `be2_geom2.py`, `be2_v3.py` y `be2_report.py`.
- **Salidas** (`output/bleeding_edge_r2/`): `be2_*.md`, `be2_*.json`, `be2_*.log` y `be2_report_table.md`.
- **Caché de geometrías:** `tmp/be2_geom/`.
