# Laboratorio, ronda 2, parte B: fuentes nuevas del Investigador A (DVOL y otras), solo diseño

- **Cuándo:** 2026-10-16, de 01:40 a 01:43 y de 05:33 a 05:40 (hora local). Un corte por límite de uso interrumpió la sesión entre ambos tramos.
- **Datos usados:**
  - DVOL de Deribit (`E:/tmp/r2_data/deribit/`), leído como JSON con `python -I`;
  - USDT-USD de Coinbase, historial completo (`E:/tmp/r2_data/coinbase_full/`, 5.5 MB). Lo descargué yo, en una carpeta nueva y desde un dominio que no es de Binance;
  - ventanas de margen de Bitfinex.
- **Lo que no se hizo:** no se tocó el *holdout*, no se ejecutó nada de las carpetas de datos y no se probaron otra vez las opciones de Deribit ni GDELT.
- **Registros previos a correr:**
  - `bleeding_edge_r2_A_peek`: 30 configuraciones (el vistazo del Investigador A);
  - `bleeding_edge_r2`: 13 configuraciones (D1, D1-ETH, D2, C1 y B1 en dos colas, × 2 bases, más la combinación).
- Scripts: `scripts/be2c_dvol.py` (pre-registro en el *docstring*) y `scripts/be2c_report.py`. Salidas: `be2c_dvol.json`, `be2c_dvol.log` y `be2c_tables.md`.

## Resumen

- **D1 (no comprar si z30 del DVOL de BTC < −1) es el efecto más consistente de todo el laboratorio.**
  - Funciona en los **4 ensambles** y con las **2 bases**: ΔWR de **+2.1 a +4.7 pt** y ΔE de **+0.20 a +0.43 %**, con P_ep(ΔWR ≤ 0) entre 0.01 y 0.05.
  - **Por pliegue:** todos los pliegues con vetos mejoran (4/4, 4/4, 4/4 y 3/3), y ninguno empeora.
  - **Operaciones vetadas:** ganan entre el 54 y el 69 %, con E negativa.
  - **Frente al azar:** quitar al azar el mismo número de operaciones queda en el percentil 98–100.
  - **Volatilidad:** el gradiente se mantiene dentro de los terciles de s_d del modelo en 11 de 12 celdas (la excepción: s_d alta en ENS12U). El modelo apenas baja p̂ en las vetadas (p̂ − θ de +0.004 frente a +0.010): **no lo ve**.
  - **Señales aisladas (A = 0):** se replica en 7 de las 8 combinaciones de ensamble y base.
- **Pero D1 NO pasa el tamiz formal.** El azar condicionado a la regla (A ≥ 1 y z30 ≥ −1) sube casi lo mismo que el modelo: explica **entre el 63 y el 129 %** de la ΔWR.
  - Es decir, D1 aparta **días o episodios malos para cualquier compra** (salidas de GBTC en enero de 2024, abril de 2024, el hack de Bybit del 2025-02-21, abril y junio de 2025), no malas elecciones del modelo.
  - Según la regla que fijaste (el tamiz del azar se aplica a las reglas de selección), **la combinación pre-especificada v3 + D1 no se forma**.
  - Además, es una **regla de episodio**. Los ensambles "no contaminados" dan operaciones distintas, pero vetan **los mismos 7–9 días**. La evidencia real son unos **5–7 episodios**, y solo 2022 o la prospectiva pueden confirmarla. El *holdout* de 20 monedas no sirve: son los mismos días.
- **Secundarias:**
  - **D1-ETH:** igual que D1.
  - **D2** (tercil calculado con entrenamiento y validación; corte de −0.81 a −1.03, casi el mismo): algo más fuerte. Holm de 0.02 a 0.16, pero tampoco pasa la condición del azar.
  - **C1** (USDT-USD): mixta. En ENS13 da −0.6 pt, y en los demás de +1.4 a +2.1 pt con ΔE ≈ 0. **No pasa.**
  - **B1** (Bitfinex, dos colas): negativa en ENS13 y ENS12 (de −0.1 a −3.2 pt). En ENS12U y ENS6 no se ejecutó, porque las ventanas cubren solo el 55 % y el 94 % de las velas de la pila.
- **Recomendación:**
  - D1 no entra en la pila principal.
  - **Pre-registrar D1 como brazo S3 (v3 + D1)** de la prueba prospectiva y **probarlo en el estrés de 2022**: el DVOL existe desde 2021-03, así que 2022 aporta episodios nuevos.
  - **Grabar el DVOL cada hora desde ya.**

## Tablas
### D1 (z30 del DVOL de BTC ≥ −1): todas las muestras

| Ensamble | Base | n | WR % [Wilson] | WR beta-bin. [IC] | E % | E_R | t día | Azar WR/E | Azar cond. WR/E | ΔWR / ΔE | P_ep(ΔWR≤0) / P_ep(ΔE≤0) | pliegues que cambian: mejoran | vetadas: n · WR · E | azar que quita el mismo n: WR medio (percentil de D1) | aisladas A=0: ΔWR / ΔE | azar explica % de ΔWR | tamiz |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ENS13 (contaminado) | X5 | 123 | 89.4 [82.8, 93.7] | 90.5 [82.8, 95.8] | +2.25 | +0.234 | 6.97 | 61.7 / -0.39 | 77.5 / +1.13 | +3.9 / +0.35 | 0.02 / 0.01 | 4: 4 | 14 · 57 % · -0.72 | 85.4 % (p100) | +1.3 / +0.22 | 101 % | no |
| ENS13 (contaminado) | H384 | 123 | 91.1 [84.7, 94.9] | 92.0 [85.6, 96.3] | +2.35 | +0.247 | 7.49 | 63.6 / -0.37 | 79.1 / +1.23 | +3.3 / +0.33 | 0.02 / 0.01 | 4: 4 | 14 · 64 % · -0.50 | 87.7 % (p100) | +2.7 / +0.27 | 118 % | no |
| ENS13 | pila X5 / v3 | 131 / 131 | 85.5 / 87.8 | | +1.90 / +2.02 | | | | 73.5 / 75.2 (WR) | — | — | — | — | — | aisladas base: 87 · 75.9 % · +0.88 | — | — |
| ENS12 (no contaminado) | X5 | 103 | 88.3 [80.7, 93.2] | 90.0 [78.6, 96.0] | +2.12 | +0.235 | 6.44 | 62.1 / -0.33 | 78.4 / +1.22 | +4.7 / +0.43 | 0.01 / 0.01 | 4: 4 | 13 · 54 % · -1.07 | 83.7 % (p100) | +2.2 / +0.43 | 78 % | no |
| ENS12 (no contaminado) | H384 | 101 | 91.1 [83.9, 95.2] | 92.3 [83.6, 96.8] | +2.32 | +0.259 | 7.11 | 64.0 / -0.33 | 80.2 / +1.31 | +4.1 / +0.41 | 0.01 / 0.00 | 4: 4 | 13 · 62 % · -0.79 | 87.0 % (p100) | +3.9 / +0.50 | 91 % | no |
| ENS12 | pila X5 / v3 | 110 / 108 | 83.6 / 87.0 | | +1.69 / +1.90 | | | | 74.7 / 76.6 (WR) | — | — | — | — | — | aisladas base: 88 · 73.9 % · +0.72 | — | — |
| ENS12U (no contaminado) | X5 | 296 | 81.4 [76.6, 85.4] | 79.1 [71.1, 84.6] | +1.19 | +0.137 | 4.35 | 65.4 / -0.18 | 74.6 / +0.53 | +2.8 / +0.21 | 0.02 / 0.04 | 4: 4 | 55 · 64 % · -0.18 | 78.6 % (p100) | +3.5 / +0.26 | 91 % | no |
| ENS12U (no contaminado) | H384 | 293 | 84.0 [79.3, 87.7] | 80.8 [72.6, 86.8] | +1.30 | +0.149 | 4.72 | 67.7 / -0.14 | 77.7 / +0.64 | +2.1 / +0.20 | 0.05 / 0.05 | 4: 4 | 54 · 69 % · -0.13 | 81.8 % (p98) | +4.3 / +0.30 | 129 % | no |
| ENS12U | pila X5 / v3 | 341 / 336 | 78.6 / 81.8 | | +0.99 / +1.09 | | | | 72.1 / 74.9 (WR) | — | — | — | — | — | aisladas base: 91 · 68.1 % · -0.33 | — | — |
| ENS6 (no contaminado (v1)) | X5 | 132 | 84.1 [76.9, 89.4] | 87.6 [78.1, 94.0] | +1.56 | +0.168 | 3.47 | 63.4 / -0.25 | 77.2 / +0.99 | +2.5 / +0.26 | 0.04 / 0.03 | 3: 3 | 11 · 55 % · -1.45 | 81.6 % (p99) | -1.0 / +0.01 | 76 % | no |
| ENS6 (no contaminado (v1)) | H384 | 130 | 86.2 [79.2, 91.1] | 89.0 [80.6, 94.8] | +1.66 | +0.178 | 3.52 | 65.3 / -0.22 | 78.6 / +1.06 | +2.7 / +0.26 | 0.04 / 0.03 | 3: 3 | 11 · 55 % · -1.32 | 83.5 % (p100) | +1.6 / +0.08 | 63 % | no |
| ENS6 | pila X5 / v3 | 141 / 139 | 81.6 / 83.5 | | +1.30 / +1.40 | | | | 75.2 / 76.9 (WR) | — | — | — | — | — | aisladas base: 67 · 80.6 % · +1.18 | — | — |

### Control de volatilidad y de p̂ (D1, base X5; operaciones de la pila: conservadas frente a vetadas)

| Ensamble | s_d baja: conserv. n · WR · E / vetadas | s_d media | s_d alta | p̂ − θ medio: conservadas / vetadas | días de las vetadas |
|---|---|---|---|---|---|
| ENS13 | 39 · 87 % · +1.09 / 5 · 40 % · -1.00 | 37 · 84 % · +1.25 / 6 · 67 % · -0.47 | 41 · 95 % · +4.16 / 3 · 67 % · -0.74 | +0.010 / +0.004 | 2024-01-22, 2024-01-23, 2024-04-12, 2024-04-13, 2024-06-18, 2025-02-21, 2025-04-25, 2025-06-02, 2025-06-23 |
| ENS12 | 32 · 88 % · +1.03 / 5 · 40 % · -1.11 | 31 · 87 % · +1.65 / 5 · 60 % · -1.24 | 34 · 88 % · +3.41 / 3 · 67 % · -0.74 | +0.010 / +0.004 | 2024-01-22, 2024-01-23, 2024-01-24, 2024-04-12, 2024-04-13, 2025-02-21, 2025-04-25, 2025-06-02, 2025-06-23 |
| ENS12U | 91 · 81 % · +0.52 / 23 · 57 % · -0.23 | 97 · 82 % · +0.96 / 16 · 50 % · -1.99 | 98 · 81 % · +2.11 / 16 · 88 % · +1.71 | +0.024 / +0.015 | 2024-01-22, 2024-01-23, 2024-01-24, 2024-01-25, 2024-01-26, 2024-01-28, 2024-01-29, 2024-01-30, 2024-02-01, 2024-04-12, 2024-04-13, 2024-04-30, 2024-05-01, 2024-06-18, 2024-09-14, 2024-09-19, 2024-09-21, 2024-09-22, 2025-02-21 |
| ENS6 | 42 · 86 % · +0.79 / 5 · 60 % · -0.74 | 42 · 74 % · +0.31 / 5 · 60 % · -0.34 | 46 · 91 % · +3.34 / 1 · 0 % · -10.54 | +0.013 / +0.002 | 2024-01-22, 2024-01-23, 2024-04-12, 2024-04-13, 2025-04-25, 2025-06-02, 2025-06-23 |

### Consistencia por pliegue (D1, base X5): WR de las conservadas − WR de las vetadas, en los pliegues con vetadas

- ENS13: pliegue 0 (vetadas 4): +39 pt; pliegue 1 (vetadas 6): +33 pt; pliegue 4 (vetadas 1): +95 pt; pliegue 5 (vetadas 3): +33 pt → mismo signo (+) en 4/4
- ENS12: pliegue 0 (vetadas 5): +29 pt; pliegue 1 (vetadas 4): +50 pt; pliegue 4 (vetadas 1): +100 pt; pliegue 5 (vetadas 3): +33 pt → mismo signo (+) en 4/4
- ENS12U: pliegue 0 (vetadas 28): +14 pt; pliegue 1 (vetadas 18): +16 pt; pliegue 2 (vetadas 6): +32 pt; pliegue 4 (vetadas 3): +76 pt → mismo signo (+) en 4/4
- ENS6: pliegue 0 (vetadas 4): +39 pt; pliegue 1 (vetadas 3): +67 pt; pliegue 5 (vetadas 4): +25 pt → mismo signo (+) en 3/3

### Todas las reglas de la parte B (ΔWR pt / ΔE %, P_ep(ΔWR≤0), Holm sobre las 6 reglas por ensamble y base)

| Regla | ENS13 X5 | ENS13 H384 | ENS12 X5 | ENS12 H384 | ENS12U X5 | ENS12U H384 | ENS6 X5 | ENS6 H384 |
|---|---|---|---|---|---|---|---|---|
| D1 z30(BTC) ≥ −1 | +3.9 / +0.35 · p 0.02 → Holm 0.10 | +3.3 / +0.33 · p 0.02 → Holm 0.09 | +4.7 / +0.43 · p 0.01 → Holm 0.05 | +4.1 / +0.41 · p 0.01 → Holm 0.05 | +2.8 / +0.21 · p 0.02 → Holm 0.04 | +2.1 / +0.20 · p 0.05 → Holm 0.13 | +2.5 / +0.26 · p 0.04 → Holm 0.16 | +2.7 / +0.26 · p 0.04 → Holm 0.15 |
| D1-ETH (ETH usa su DVOL) | +3.9 / +0.34 · p 0.02 → Holm 0.10 | +3.3 / +0.33 · p 0.02 → Holm 0.09 | +4.7 / +0.41 · p 0.01 → Holm 0.05 | +4.1 / +0.41 · p 0.01 → Holm 0.05 | +2.9 / +0.20 · p 0.01 → Holm 0.04 | +2.2 / +0.21 · p 0.04 → Holm 0.13 | +2.5 / +0.26 · p 0.04 → Holm 0.16 | +2.7 / +0.26 · p 0.04 → Holm 0.15 |
| D2 z30 ≥ tercil de train+val | +4.6 / +0.37 · p 0.01 → Holm 0.05 | +3.9 / +0.35 · p 0.01 → Holm 0.04 | +5.5 / +0.44 · p 0.00 → Holm 0.02 | +4.9 / +0.43 · p 0.00 → Holm 0.02 | +3.1 / +0.27 · p 0.01 → Holm 0.03 | +2.4 / +0.27 · p 0.03 → Holm 0.10 | +2.4 / +0.25 · p 0.04 → Holm 0.16 | +2.6 / +0.25 · p 0.04 → Holm 0.15 |
| C1 z30(USDT-USD) ≥ −1 | -0.6 / -0.07 · p 0.63 → Holm 1.00 | -1.0 / -0.11 · p 0.77 → Holm 1.00 | +1.8 / -0.02 · p 0.25 → Holm 0.74 | -0.6 / -0.18 · p 0.68 → Holm 1.00 | +1.9 / +0.12 · p 0.05 → Holm 0.05 | +1.4 / +0.11 · p 0.05 → Holm 0.13 | +2.1 / +0.15 · p 0.08 → Holm 0.16 | +2.0 / +0.10 · p 0.06 → Holm 0.15 |
| B1-bajo: longs Bitfinex 4 h no en tercil bajo | -2.5 / -0.13 · p 0.91 → Holm 1.00 | -2.9 / -0.14 · p 1.00 → Holm 1.00 | -3.2 / -0.07 · p 0.92 → Holm 0.92 | -2.0 / -0.09 · p 0.80 → Holm 1.00 | – | – | – | – |
| B1-alto: longs Bitfinex 4 h no en tercil alto | -0.6 / -0.13 · p 0.65 → Holm 1.00 | -1.0 / -0.12 · p 0.82 → Holm 1.00 | +0.4 / +0.01 · p 0.41 → Holm 0.82 | -0.1 / +0.03 · p 0.52 → Holm 1.00 | – | – | – | – |

Información: {'cuts_D2': [-0.8856827726898148, -0.8558478405923331, -1.0322433328675156, -0.9406620802231519, -0.805562947695154, -0.8730127986168127], 'bfx_cov': {'ENS13': 1.0, 'ENS12': 1.0, 'ENS12U': 0.550978607191625, 'ENS6': 0.9436813186813187}, 'usdt': {'n': 91392, 'frac_finite': 0.9780943627450981}, 'bfx_cuts': [-0.014070024901928031, 0.05494807122088385]}

**Notas sobre las tablas:**

- "Pliegues que cambian: mejoran" cuenta los pliegues en los que la regla cambia operaciones y, entre ellos, los que mejoran en WR y en E. Δ por pliegue en ENS13 con base X5 (WR pt / E %): +15/+0.72, +15/+2.06, 0/0, 0/0, +5/+0.54 y +4/+0.22.
- Episodios en ENS13 con base X5: 22, con 91 % positivos (la pila: 24, con 83 %).
- Complemento simulado (comprar solo con z30 < −1): 23 operaciones, 73.9 % y +0.52 % en ENS13; 23, 73.9 % y +0.45 % en ENS12.

## Tamiz y combinación

| Criterio (base H 384) | ENS12 | ENS12U | ENS6 |
|---|---|---|---|
| ΔWR ≥ +1 y ΔE ≥ 0 | sí (+4.1 / +0.41) | sí (+2.1 / +0.20) | sí (+2.7 / +0.26) |
| P_ep(ΔWR ≤ 0) ≤ 0.20 | sí (0.01) | sí (0.05) | sí (0.04) |
| ≥ 2/3 de los pliegues que cambian mejoran | sí (4/4) | sí (4/4) | sí (3/3) |
| El azar condicionado explica ≤ 1/2 de ΔWR | **no (91 %)** | **no (129 %)** | **no (63 %)** |
| **Pasa** | no | no | no |

**Combinación v3 + D1: no se forma.** Pasa en 0 de 3 ensambles no contaminados.

Como referencia, sin adoptarla: la fila "D1 [H384]" de la tabla es exactamente v3 + D1. Da:

| Ensamble | n | WR [Wilson] | E | Δ frente a v3 |
|---|---|---|---|---|
| ENS13 | 123 | 91.1 % [84.7, 94.9] | +2.35 % | +3.3 pt / +0.33 % |
| ENS12 | 101 | 91.1 % | +2.32 % | +4.1 pt / +0.41 % |
| ENS12U | 293 | 84.0 % | +1.30 % | +2.1 pt / +0.20 % |
| ENS6 | 130 | 86.2 % | +1.66 % | +2.7 pt / +0.26 % |

## Estimación fuera de muestra para D1, si se confirmara

- **Diseño:** +2 a +5 pt (mediana ≈ +3.3) y +0.2 a +0.4 % de E sobre la pila.
- **Por qué hay que encogerlo:**
  - **Selección del corte:** salió de mirar 4 cortes y unas 30 variables en ENS13. Que la réplica en los ensambles no contaminados dé lo mismo mitiga el sesgo de selección de **operaciones**, pero **no** el de **episodios**: son los mismos 5–7 episodios.
  - **Tamaño efectivo:** con n ≈ 6 episodios, es habitual que el efecto se reduzca a la mitad, o más.
- **Estimación:** encogimiento de 0.3–0.6 ⇒ **+0.5 a +2 pt de WR y +0.05 a +0.2 % de E**, con una probabilidad de ≈ 35–45 % de que el efecto real sea ≈ 0.
- **Cómo se confirma:** solo con 2022 (episodios nuevos, como LUNA o FTX, en los que el DVOL se disparó o no) o con la prospectiva. El *holdout* de 20 monedas no la confirma.
