# Laboratorio, ronda 2, parte A: hipótesis de métodos del Investigador B (solo diseño)

Fecha: 2026-10-16, de 01:08 a 01:18 (hora local). Todo en DISEÑO (pruebas walk-forward 2024-01..2025-06, BTC/ETH/SOL/DOGE). El *holdout* no se tocó y no se descargó nada.

## Resumen

- **Ninguna de las 10 hipótesis pasa el tamiz**, ni con la base X5 ni con la base H 384. El tamiz es el del laboratorio, con *bootstrap* por episodio, más la condición de que el azar condicionado no explique más de la mitad de la mejora.
- **No se forma la combinación final** (regla 4): ninguna pieza de selección (H1, H4, H6 o H7) ni de salida (H2 o H3) pasó por separado.
- **La pila v3 sigue siendo la pila + H 384** (E7). Re-medida con la estadística de esta ronda: **131 operaciones · WR 87.8 % [Wilson 81.1, 92.3] · WR beta-binomial por episodio 87.8 % [81.6, 93.0] · E +2.02 %**.
  - Frente a la pila: +2.3 pt / +0.12 %, con *bootstrap* por episodio P(ΔWR ≤ 0) = 0.04 y P(ΔE ≤ 0) = 0.00.
  - **Ojo con el tamiz nuevo:** E7 **no pasa la condición del azar condicionado.** El azar con la misma salida sube 1.7 de los 2.3 pt (74 %) en ENS13, el 56 % en ENS12 y el 85 % en ENS12U.
  - Es lo esperado en una regla de geometría: la mejora es estructural (de la salida), no de selección. Sigue como candidata **con reserva**. El coordinador decide si el tamiz nuevo aplica a reglas de salida.
- **Lo que se aprendió del mecanismo:**
  - **H1 (rezagados):** no recorta 60 operaciones, como se esperaba, sino 14 (131 → 117). La regla **posterga** la entrada en lugar de saltarla, porque la moneda vuelve a dar señal cuando L baja.
    - En ENS13: +0.8 pt y −0.04 %. Con el control al revés: −2.6 pt.
    - La dirección se sostiene, pero el efecto es menor que el umbral.
  - **H2 (TP anclado):** es **pura redistribución**, sin anclaje Ornstein-Uhlenbeck:
    - en el tercil bajo de la brecha g, el WR sube de 89 a 98 % y la E baja de +1.83 a +1.11 %;
    - en el tercil alto, el WR baja de 82 a 75 % y la E sube de +1.77 a +2.97 %.
    - Neto: ΔE de −0.26 a −0.37 % en los 3 ensambles. El azar con la misma salida explica más del 100 % de la ΔWR.
  - **H3 (TP2 por estado):** se dispara en el **68–72 %** de las operaciones. Es una toma parcial disfrazada: WR 94 %, pero E −1.0 %. Con D2, el disparador por tiempo, se dispara en el 16–20 %.
  - **H5 (prioridad bajo cupo):** **no se puede medir con 4 monedas.** El orden cambia qué moneda se compra en unas pocas velas, pero el WR y la E salen idénticos en las 200 permutaciones al azar. Queda para el *holdout* de 20 monedas.
  - **H8 y H9 (calibración y umbral):** cambian mucho la selectividad (de 160 a 460 operaciones) y pierden entre 8 y 13 pt. Muestran que la cola calibrada con Platt y la regla v2 son frágiles a cualquier cambio de procedimiento.
- **Configuraciones registradas en `log_trials("bleeding_edge_r2")` antes de correr:** 33 (10 + 8 + 3 + 6 + 6). En toda la ronda 2 van 165.

## Método

- **Código común:** `scripts/be2b_common.py`, sobre `be2_common`. Las dos bases (pila X5 y pila con H 384) se reproducen exactamente.
- ***Bootstrap* por episodio:** los episodios son los días con operaciones de ambos conjuntos, unidos si distan ≤ 2 días; 5 000 réplicas.
- **IC beta-binomial:** WR con efectos aleatorios por episodio, por máxima verosimilitud de (μ, ρ) y verosimilitud perfilada al 95 %.
- **Tamiz:**
  - ΔWR ≥ +1 pt y ΔE ≥ 0 en ENS13;
  - mejora en ≥ 4 de 6 pliegues;
  - P(ΔWR ≤ 0) ≤ 0.20 con *bootstrap* por episodio;
  - réplica en ≥ 2 de 3 ensambles;
  - además, el azar condicionado a la regla (en las reglas de salida, el azar con la misma salida) no debe explicar más del 50 % de la ΔWR.
- **Comparaciones adicionales:** complemento simulado (en H1, H6 y H7); geometría fija con el *a* medio (en H2); D2 (en H3); orden por p̂ y 200 órdenes al azar (en H5).
- **Pre-registro:** las reglas están copiadas de `investigador_B.md` en el *docstring* de cada script, que se registró antes de calcular.

## Tabla resumen

La fila principal es ENS13. Las columnas de réplica dan ΔWR / ΔE frente a la base de cada ensamble. "Tipo" separa las reglas **de episodio** (qué pánico comprar; solo se confirman con 2022 o con la prospectiva) de las reglas **dentro del episodio** (qué moneda o qué salida; las confirma el *holdout* de 20 monedas).

| Regla | Base | Tipo | n | WR % [Wilson] | WR beta-bin. [IC 95] | E % | E_R | t día | Azar WR/E | Azar cond. (regla) WR/E | ΔWR / ΔE vs base | P(ΔWR≤0) / P(ΔE≤0) boot. episodio | pliegues mejor (=) | episodios | réplica ENS12 ; ENS12U (ΔWR / ΔE) | azar explica % de ΔWR | tamiz |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| H1 rezagados: L < 1 (exploratoria, contaminada) | X5 | episodio | 117 | 86.3 [78.9, 91.4] | 86.3 [79.6, 91.8] | +1.86 | +0.189 | 5.40 | 61.1 / -0.46 | 73.3 / +0.75 | +0.8 / -0.04 | 0.27 / 0.61 | 2/6 (=0) | 21 | +1.1 / +0.18 ; +0.5 / +0.06 | -23 % | no |
| H1 control al revés: L > 0 | X5 | episodio | 117 | 82.9 [75.1, 88.7] | 82.8 [75.1, 89.3] | +1.81 | +0.165 | 4.58 | 60.5 / -0.45 | 71.6 / +0.47 | -2.6 / -0.10 | 1.00 / 0.84 | 1/6 (=0) | 22 | -0.6 / +0.02 ; +0.5 / +0.04 | – | no |
| H6 funding 24 h antes ≥ tercil inferior de val. | X5 | episodio | 71 | 83.1 [72.7, 90.1] | 80.6 [62.2, 90.5] | +1.80 | +0.186 | 4.55 | 64.2 / -0.13 | 74.9 / +0.76 | -2.4 / -0.11 | 0.77 / 0.67 | 1/6 (=0) | 15 | +0.4 / +0.09 ; +1.6 / -0.10 | – | no |
| H7 divergencia OI/taker ≤ p80 de val. | X5 | dentro | 126 | 84.1 [76.8, 89.5] | 84.1 [73.9, 90.8] | +1.83 | +0.178 | 4.46 | 61.4 / -0.42 | 73.6 / +0.75 | -1.4 / -0.07 | 1.00 / 0.97 | 0/6 (=0) | 23 | +0.6 / +0.02 ; +0.9 / +0.08 | – | no |
| H10 co-firma G5 | X5 | dentro | 79 | 86.1 [76.8, 92.0] | 87.6 [76.6, 95.0] | +1.90 | +0.187 | 3.50 | 59.8 / -0.54 | 72.1 / +0.63 | +0.6 / +0.00 | 0.40 / 0.48 | 3/6 (=0) | 19 | +0.9 / -0.08 ; +4.0 / +0.41 | -245 % | no |
| H1 rezagados: L < 1 (exploratoria, contaminada) | H384 | episodio | 117 | 88.0 [80.9, 92.7] | 88.0 [81.6, 93.0] | +1.95 | +0.203 | 5.70 | 62.8 / -0.46 | 74.9 / +0.86 | +0.2 / -0.06 | 0.43 / 0.66 | 2/6 (=0) | 21 | +1.5 / +0.12 ; +0.6 / +0.10 | -117 % | no |
| H1 control al revés: L > 0 | H384 | episodio | 117 | 85.5 [78.0, 90.7] | 85.6 [78.6, 91.3] | +1.90 | +0.181 | 5.00 | 62.4 / -0.44 | 73.6 / +0.59 | -2.3 / -0.12 | 1.00 / 0.91 | 1/6 (=0) | 22 | -1.3 / -0.03 ; +0.9 / +0.07 | – | no |
| H6 funding 24 h antes ≥ tercil inferior de val. | H384 | episodio | 71 | 88.7 [79.3, 94.2] | 88.8 [78.3, 94.5] | +2.04 | +0.222 | 5.69 | 66.2 / -0.11 | 77.4 / +0.92 | +0.9 / +0.02 | 0.38 / 0.49 | 2/6 (=0) | 15 | +1.4 / +0.11 ; -0.0 / -0.14 | 229 % | no |
| H7 divergencia OI/taker ≤ p80 de val. | H384 | dentro | 126 | 87.3 [80.4, 92.0] | 87.3 [80.6, 92.8] | +1.96 | +0.200 | 4.82 | 63.3 / -0.41 | 75.4 / +0.86 | -0.5 / -0.05 | 0.99 / 0.94 | 0/6 (=0) | 23 | -0.1 / -0.04 ; +0.8 / +0.08 | – | no |
| H10 co-firma G5 | H384 | dentro | 79 | 87.3 [78.2, 93.0] | 88.8 [78.8, 95.3] | +1.98 | +0.200 | 3.73 | 61.7 / -0.54 | 73.8 / +0.73 | -0.4 / -0.04 | 0.56 / 0.55 | 3/6 (=0) | 19 | -1.1 / -0.21 ; +1.9 / +0.43 | – | no |
| H2 principal (f = 0.5) | X5 | dentro | 134 | 86.6 [79.8, 91.3] | 86.3 [75.6, 92.5] | +1.64 | +0.159 | 3.78 | 72.4 / -0.40 | 78.7 / +0.42 | +1.1 / -0.26 | 0.32 / 0.95 | 0/6 (=0) | 24 | +1.7 / -0.29 ; +5.6 / -0.27 | 483 % | no |
| H2 con θ re-elegido en validación | X5 | dentro | 134 | 86.6 [79.8, 91.3] | 86.3 [75.6, 92.5] | +1.64 | +0.159 | 3.78 | 72.4 / -0.40 | 78.7 / +0.42 | +1.1 / -0.26 | 0.32 / 0.95 | 0/6 (=0) | 24 | +1.7 / -0.29 ; +4.6 / -0.41 | 483 % | no |
| H2 sensibilidad (f = 0.6) | X5 | dentro | 127 | 83.5 [76.0, 88.9] | 82.3 [70.4, 89.8] | +1.65 | +0.152 | 3.55 | 70.9 / -0.38 | 77.5 / +0.51 | -2.0 / -0.25 | 0.79 / 0.97 | 2/6 (=0) | 24 | +0.1 / -0.20 ; +4.6 / -0.25 | – | no |
| geometría fija con el a medio (control de 'TP más chico') | X5 | dentro (control) | 128 | 84.4 [77.1, 89.7] | 84.6 [75.1, 91.0] | +2.01 | +0.196 | 5.38 | 60.1 / -0.44 | 72.1 / +0.72 | -1.1 / +0.11 | 1.00 / 0.02 | 0/6 (=0) | 24 | +0.7 / -0.08 ; +1.8 / -0.01 | – | no |
| H2 principal (f = 0.5) | H384 | dentro | 134 | 88.1 [81.5, 92.5] | 88.3 [80.8, 93.3] | +1.73 | +0.173 | 3.98 | 73.8 / -0.38 | 80.2 / +0.52 | +0.3 / -0.29 | 0.43 / 0.95 | 1/6 (=0) | 24 | +0.9 / -0.37 ; +4.3 / -0.27 | 1803 % | no |
| H2 con θ re-elegido en validación | H384 | dentro | 132 | 88.6 [82.1, 93.0] | 89.0 [81.8, 94.0] | +1.75 | +0.175 | 3.96 | 73.8 / -0.38 | 80.2 / +0.52 | +0.9 / -0.27 | 0.28 / 0.93 | 1/6 (=0) | 22 | +0.9 / -0.37 ; +2.8 / -0.44 | 585 % | no |
| H2 sensibilidad (f = 0.6) | H384 | dentro | 127 | 85.0 [77.8, 90.2] | 85.1 [75.6, 91.0] | +1.87 | +0.175 | 3.84 | 72.1 / -0.39 | 79.1 / +0.63 | -2.7 / -0.15 | 0.94 / 0.80 | 1/6 (=0) | 24 | -0.6 / -0.16 ; +3.2 / -0.23 | – | no |
| geometría fija con el a medio (control de 'TP más chico') | H384 | dentro (control) | 128 | 87.5 [80.7, 92.2] | 87.6 [81.1, 92.8] | +2.14 | +0.218 | 5.84 | 62.0 / -0.44 | 73.9 / +0.83 | -0.3 / +0.12 | 1.00 / 0.00 | 0/6 (=0) | 24 | +0.6 / -0.07 ; +1.4 / -0.03 | – | no |
| H3 TP2 por estado | X5 | dentro | 198 | 93.9 [89.7, 96.5] | 94.3 [90.3, 97.3] | +0.89 | +0.092 | 4.48 | 60.3 / -0.47 | 84.5 / +0.10 | +8.4 / -1.01 | 0.00 / 1.00 | 0/6 (=0) | 24 | +9.7 / -0.87 ; +11.1 / -0.56 | 140 % | no |
| D2 TP2 por tiempo (36 h) | X5 | dentro | 133 | 90.2 [84.0, 94.2] | 91.0 [84.3, 95.5] | +1.86 | +0.193 | 5.45 | 61.2 / -0.43 | 77.7 / +0.29 | +4.7 / -0.05 | 0.00 / 0.75 | 2/6 (=1) | 24 | +4.7 / -0.07 ; +4.4 / -0.04 | 105 % | no |
| H3 TP2 por estado | H384 | dentro | 197 | 94.4 [90.3, 96.9] | 94.8 [90.8, 97.8] | +0.90 | +0.094 | 4.49 | 60.3 / -0.47 | 85.4 / +0.12 | +6.6 / -1.12 | 0.00 / 1.00 | 0/6 (=0) | 24 | +6.9 / -1.07 ; +8.7 / -0.65 | 158 % | no |
| D2 TP2 por tiempo (36 h) | H384 | dentro | 133 | 90.2 [84.0, 94.2] | 91.0 [84.3, 95.5] | +1.86 | +0.193 | 5.45 | 61.2 / -0.43 | 78.9 / +0.32 | +2.4 / -0.16 | 0.01 / 0.99 | 1/6 (=1) | 24 | +2.9 / -0.23 ; +2.9 / -0.11 | 162 % | no |
| H4 meta-etiquetado bayesiano (q20) | X5 | selección (mixta) | 121 | 84.3 [76.8, 89.7] | 84.3 [77.1, 90.3] | +1.85 | +0.175 | 4.76 | 61.2 / -0.44 | 74.2 / +0.76 | -1.2 / -0.05 | 1.00 / 0.95 | 0/6 (=3) | 22 | -1.1 / -0.04 ; +0.4 / +0.07 | – | no |
| H5 MAX2 prioridad por antigüedad | X5 | dentro | 113 | 84.1 [76.2, 89.7] | 84.1 [75.1, 90.5] | +1.87 | +0.184 | 4.53 | 60.2 / -0.52 | 72.6 / +0.66 | -1.4 / -0.03 | 0.83 / 0.60 | 1/6 (=1) | 25 | +0.1 / +0.06 ; +2.1 / +0.18 | – | no |
| H5 MAX3 prioridad por antigüedad | X5 | dentro | 128 | 85.2 [78.0, 90.3] | 85.3 [76.6, 91.3] | +1.85 | +0.186 | 4.93 | 60.9 / -0.48 | 73.4 / +0.69 | -0.3 / -0.05 | 1.00 / 0.76 | 0/6 (=2) | 24 | +0.0 / -0.01 ; +0.1 / -0.04 | – | no |
| H4 meta-etiquetado bayesiano (q20) | H384 | selección (mixta) | 123 | 87.0 [79.9, 91.8] | 87.1 [80.3, 92.3] | +1.98 | +0.196 | 5.31 | 63.1 / -0.42 | 75.7 / +0.87 | -0.8 / -0.04 | 1.00 / 0.89 | 0/6 (=3) | 22 | -0.9 / -0.03 ; +1.0 / +0.14 | – | no |
| H5 MAX2 prioridad por antigüedad | H384 | dentro | 112 | 86.6 [79.1, 91.7] | 86.6 [79.6, 92.3] | +1.98 | +0.201 | 4.84 | 62.0 / -0.53 | 74.2 / +0.78 | -1.2 / -0.04 | 0.76 / 0.62 | 1/6 (=1) | 24 | -0.4 / +0.05 ; +1.9 / +0.14 | – | no |
| H5 MAX3 prioridad por antigüedad | H384 | dentro | 128 | 87.5 [80.7, 92.2] | 87.6 [81.1, 92.8] | +1.96 | +0.202 | 5.28 | 62.7 / -0.47 | 75.1 / +0.80 | -0.3 / -0.06 | 1.00 / 0.96 | 0/6 (=2) | 24 | +0.2 / +0.00 ; -0.0 / -0.05 | – | no |
| H8a calibración beta | X5 | dentro | 160 | 73.8 [66.4, 80.0] | 72.6 [61.4, 80.8] | +0.64 | +0.033 | 1.44 | 60.5 / -0.51 | 69.5 / +0.11 | -11.7 / -1.26 | 1.00 / 1.00 | 0/6 (=0) | 25 | -8.3 / -0.83 ; +1.4 / +0.06 | – | no |
| H8a calibración beta | H384 | dentro | 159 | 74.2 [66.9, 80.4] | 72.6 [60.2, 81.8] | +0.70 | +0.042 | 1.56 | 62.2 / -0.54 | 72.1 / +0.28 | -13.6 / -1.31 | 1.00 / 1.00 | 0/6 (=0) | 25 | -11.9 / -0.95 ; -0.5 / +0.03 | – | no |
| H8b θ con pesos por episodio | X5 | dentro | 459 | 73.2 [69.0, 77.0] | 74.9 [68.4, 80.6] | +0.50 | +0.036 | 1.94 | 63.7 / -0.23 | 68.3 / +0.13 | -12.3 / -1.40 | 1.00 / 1.00 | 0/6 (=1) | 34 | -9.3 / -1.17 ; -4.0 / -0.59 | – | no |
| H8b θ con pesos por episodio | H384 | dentro | 452 | 75.0 [70.8, 78.8] | 76.8 [69.6, 82.8] | +0.56 | +0.037 | 2.05 | 66.0 / -0.23 | 70.3 / +0.16 | -12.8 / -1.46 | 1.00 / 1.00 | 0/6 (=1) | 34 | -10.7 / -1.32 ; -5.9 / -0.67 | – | no |
| H9 Platt mensual | X5 | dentro | 455 | 72.7 [68.5, 76.6] | 73.9 [64.1, 81.6] | +0.50 | +0.039 | 1.87 | 64.5 / -0.08 | 67.1 / +0.11 | -12.7 / -1.40 | 1.00 / 1.00 | 0/6 (=1) | 24 | -10.9 / -1.20 ; -2.0 / -0.20 | – | no |
| H9 Platt mensual | H384 | dentro | 439 | 74.9 [70.7, 78.8] | 73.6 [64.6, 81.1] | +0.56 | +0.046 | 2.00 | 67.1 / -0.05 | 69.4 / +0.17 | -12.8 / -1.46 | 1.00 / 1.00 | 0/6 (=1) | 26 | -12.2 / -1.36 ; -2.3 / -0.21 | – | no |

### Pila v3 re-medida (salida del script)

| Ens. | Base | Regla | n | WR % [Wilson] | WR beta-bin. por episodio [IC] | E % | E_R | t día | Azar WR/E | Azar cond. WR/E | ΔWR / ΔE vs base | P(ΔWR≤0) / P(ΔE≤0) (boot. episodio) | pliegues mejor (=) | episodios |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ENS13 | X5 | pila X5 | 131 | 85.5 [78.5, 90.5] | 85.6 [77.8, 91.5] | +1.90 | +0.189 | 5.30 | 61.3 / -0.43 | 73.5 / +0.71 | – | – | – | 24 (83 %) |
| ENS13 | H384 | pila v3 = pila + H 384 | 131 | 87.8 [81.1, 92.3] | 87.8 [81.6, 93.0] | +2.02 | +0.206 | 5.75 | 63.2 / -0.42 | 75.2 / +0.83 | +2.3 / +0.12 | 0.04 / 0.00 | 3/6 (=2) | 24 (92 %) |
| ENS12 | X5 | pila X5 | 110 | 83.6 [75.6, 89.4] | 83.8 [73.1, 90.8] | +1.69 | +0.180 | 4.42 | 61.8 / -0.37 | 74.7 / +0.82 | – | – | – | 19 (84 %) |
| ENS12 | H384 | pila v3 = pila + H 384 | 108 | 87.0 [79.4, 92.1] | 87.3 [79.1, 93.0] | +1.90 | +0.208 | 4.99 | 63.6 / -0.37 | 76.6 / +0.92 | +3.4 / +0.21 | 0.04 / 0.00 | 3/6 (=2) | 19 (89 %) |
| ENS12U | X5 | pila X5 | 341 | 78.6 [73.9, 82.6] | 76.6 [68.9, 82.1] | +0.99 | +0.111 | 3.82 | 64.7 / -0.24 | 72.1 / +0.30 | – | – | – | 33 (73 %) |
| ENS12U | H384 | pila v3 = pila + H 384 | 336 | 81.8 [77.4, 85.6] | 78.8 [70.1, 84.8] | +1.09 | +0.124 | 4.21 | 67.0 / -0.21 | 74.9 / +0.41 | +3.3 / +0.11 | 0.00 / 0.00 | 3/6 (=0) | 33 (76 %) |

Notas sobre la tabla:

- Las filas H5 se comparan con la pila **sin** cupo. Frente al orden por p̂ con el mismo cupo, la diferencia es exactamente 0.0 / 0.00 en los 3 ensambles y en las 2 bases.
- "Azar explica" negativo significa que el azar condicionado bajó mientras el modelo subió.

## Notas por hipótesis

| Hipótesis | Tipo | Resultado (ENS13, base X5 → base H 384) | Diagnóstico | Veredicto |
|---|---|---|---|---|
| **H1** rezagados (L < 1), contaminada | Episodio | +0.8 / −0.04 → +0.2 / −0.06 | Quita 14 operaciones, no 60: en el 33 % de las velas-señal de la pila L = 1, pero la entrada se posterga. El complemento simulado (entrar solo con L = 1) da 87 op · 81.6 % · +1.66 %. Control al revés: −2.6 / −0.10. ENS12 +1.1 / +0.18 y +1.5 / +0.12; ENS12U +0.5 / +0.06 | No pasa (2/6 pliegues, P 0.27). La dirección es coherente, pero el efecto queda bajo el umbral. Solo se puede confirmar con 2022 o con la prospectiva |
| **H6** *funding* 24 h antes | Episodio | −2.4 / −0.11 → +0.9 / +0.02 | Quita un tercio de las operaciones (71). El complemento gana 83.5 % | Rechazada |
| **H4** meta-etiquetado bayesiano | Selección (mixta) | −1.2 / −0.05 → −0.8 / −0.04 | En ENS13, el *funding* previo sale siempre con signo contrario al declarado y g casi siempre (sobrevive con +0.006 a +0.01 en 1–2 pliegues); ambos se eliminan, y queda casi solo la dispersión de los miembros (coeficiente +0.03 a +0.14). Con pesos por (episodio, moneda) hay 11–52 grupos por pliegue | Rechazada |
| **H7** divergencia de OI y *taker* | Dentro | −1.4 / −0.07 → −0.5 / −0.05 | Ninguno de los 6 pliegues mejora | Rechazada |
| **H10** co-firma del ensamble G5 | Dentro | +0.6 / 0.00 → −0.4 / −0.04 | θ_G5 existe en los 6 pliegues; quedan 79 operaciones. ENS12U +4.0 / +0.41, ENS12 +0.9 / −0.08 | Rechazada |
| **H2** TP anclado (f = 0.5) | Dentro | +1.1 / −0.26 → +0.3 / −0.29 | Ver el diagnóstico por tercil abajo. θ re-elegido en validación: casi igual (+1.1 / −0.26 → +0.9 / −0.27). Sensibilidad f = 0.6: −2.0 / −0.25. Geometría fija con el *a* medio (0.73): −1.1 / +0.11 | Rechazada: no hay anclaje en el máximo de 24 h |
| **H3** TP2 por estado | Dentro | +8.4 / −1.01 → +6.6 / −1.12 | Se dispara en el 70 % de las operaciones. D2 (por tiempo): +4.7 / −0.05 → +2.4 / −0.16 | Rechazada (toma parcial disfrazada) |
| **H5** antigüedad bajo cupo | Dentro | 0.0 / 0.00 frente al orden por p̂ (MAX2 y MAX3) | Con 4 monedas hay 2 velas con 3 entradas simultáneas; el orden cambia la moneda, pero no el resultado (200 permutaciones idénticas) | No medible en diseño. Probar en el *holdout* de 20 monedas |
| **H8a** calibración beta | Dentro | −11.7 / −1.26 → −13.6 / −1.31 | θ distinto; 160 operaciones | Rechazada |
| **H8b** θ con pesos por episodio | Dentro | −12.3 / −1.40 → −12.8 / −1.46 | θ más bajo; 459 operaciones | Rechazada |
| **H9** Platt mensual | Dentro | −12.7 / −1.40 → −12.8 / −1.46 | Con θ fijo y la calibración desplazada se pasa a 455 operaciones | Rechazada |

**Diagnóstico de H2 por tercil de g** (mismas 131 entradas de la pila; WR / E con X5 → con el TP anclado):

| Tercil de g | Cortes | n | WR / E con X5 | WR / E con el TP anclado |
|---|---|---|---|---|
| Bajo | < 0.89 | 44 | 89 % / +1.83 | **98 %** / +1.11 |
| Medio | 0.89–1.89 | 43 | 86 % / +2.10 | 86 % / +2.13 |
| Alto | > 1.89 | 44 | 82 % / +1.77 | 75 % / **+2.97** |

- Es la "redistribución" que el propio Investigador B anticipó para el caso sin anclaje.
- Con anclaje, el tercil bajo debería haber ganado WR **y** E a la vez; aquí pierde E.
- Igual patrón en ENS12 y ENS12U.

## Candidatas

- **Pasan el tamiz completo: ninguna.**
- **Siguen como hipótesis, sin evidencia suficiente en diseño:**
  - H1, regla de episodio: solo con 2022 o con la prospectiva, como brazo pre-registrado. Su efecto real en diseño es pequeño porque posterga, no salta.
  - H5, regla dentro del episodio: solo es medible con más monedas (*holdout* de 20 monedas).

## Combinación pre-especificada (regla 4)

**No se forma:** ninguna regla de selección ni de salida pasó su tamiz por separado.

## Pila v3 actualizada (medida una sola vez; mismas piezas que en la ronda 1)

**Pila v3** = v2 ENS13 + co-señal A ≥ 1 (W = 48) + salida X5 con **H = 384**.

| Ensamble | Pila | n | WR % [Wilson] | WR beta-binomial por episodio [IC 95] | E % | E_R | t día | Azar / azar condicionado (WR, E) | ΔWR / ΔE frente a la pila | P(Δ ≤ 0), *bootstrap* por episodio | Pliegues que mejoran (empates) | Episodios (WR) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ENS13 | Pila X5 | 131 | 85.5 [78.5, 90.5] | 85.6 [77.8, 91.5] | +1.90 | +0.189 | 5.30 | 61.3 / −0.43 · 73.5 / +0.71 | — | — | — | 24 (83 %) |
| ENS13 | **v3** | **131** | **87.8 [81.1, 92.3]** | **87.8 [81.6, 93.0]** | **+2.02** | **+0.206** | **5.75** | 63.2 / −0.42 · 75.2 / +0.83 | **+2.3 / +0.12** | 0.04 / 0.00 | 3/6 (2) | 24 (92 %) |
| ENS12 | v3 | 108 | 87.0 [79.4, 92.1] | 87.3 [79.1, 93.0] | +1.90 | +0.208 | 4.99 | 63.6 / −0.37 · 76.6 / +0.92 | +3.4 / +0.21 | 0.04 / 0.00 | 3/6 (2) | 19 (89 %) |
| ENS12U | v3 | 336 | 81.8 [77.4, 85.6] | 78.8 [70.1, 84.8] | +1.09 | +0.124 | 4.21 | 67.0 / −0.21 · 74.9 / +0.41 | +3.3 / +0.11 | 0.00 / 0.00 | 3/6 (0) | 33 (76 %) |

- **Con BNB (0.19 %),** ENS13: E +2.07 % (ronda 1).
- **Tamiz nuevo:** el azar condicionado con la misma salida explica el 74 %, el 56 % y el 85 % de la ΔWR (en ENS13, ENS12 y ENS12U). E7 es geometría, no selección. Por eso sigue siendo candidata **con reserva**, no candidata plena.

## Estimación honesta fuera de muestra

- **Pila actual:** el Juez estima un WR de 72–78 % y una E de +0.6 a +1.1 %. Viene de que la v2 retuvo ≈ 48 % de su ventaja sobre el azar (de +19.7 pt a +9.4 pt) y de que la co-señal se estimó en un 50–75 %.
- **E7 (H 384):** de los +2.3 pt de diseño (la versión con H elegido en WF da +1.5 pt):
  - ≈ +1.7 pt son **estructurales**, porque el azar sube igual. Esa parte se transfiere en un **70–100 %** si la deriva fuera de muestra no es negativa: una operación lenta que sigue abierta toca antes el TP con probabilidad m/(a+m) ≈ 71 %, frente al 37.5 % de WR de las salidas por tiempo.
  - ≈ +0.6 pt son del modelo y se encogen como la v2, al **≈ 50 %**.
  - **Resultado: +1 a +1.5 pt de WR y de 0 a +0.1 % de E.** En un mercado bajista (deriva negativa) la ganancia de E puede desaparecer.
- **Esta parte A no añade nada:** todas las piezas fallaron, así que no hay más encogimiento que aplicar.
- **Pila v3 fuera de muestra: WR ≈ 73–79 %, E ≈ +0.6 a +1.2 % por operación.** Igual que en la ronda 1.
  - El IC beta-binomial por episodio en diseño (81.6–93.0 %) es el límite superior honesto. Con 24 episodios, el límite inferior de diseño ya está cerca de lo que se espera fuera de muestra.

## Archivos

- **Scripts** (`scripts/`): `be2b_common.py`, `be2b_sel.py` (H1, H6, H7, H10), `be2b_h2.py`, `be2b_h3.py`, `be2b_h4h5.py`, `be2b_h8h9.py` y `be2b_final.py`.
- **Salidas** (`output/bleeding_edge_r2/`): `be2b_*.md`, `be2b_*.json`, `be2b_*.log` y `be2b_final_tables.md`.
- **Caché de etiquetas de la salida anclada:** `tmp/be2_geom/*_h2f*.npz`.
