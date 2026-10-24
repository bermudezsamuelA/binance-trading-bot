# Canal sombra v3: prueba prospectiva

Periodo evaluado: **2025-07-01 a 2026-10-01 00:00 UTC** (hasta donde todas las series estan completas). Generado 2026-10-24T08:15:29Z. Umbral θ = 0.7143. No es la decisión final: el pre-registro termina el 2027-12-31 o 400 operaciones de P1, lo que llegue primero.

| Brazo | Costo | n | Abiertas | WR | Wilson 95 % | E % | t/día | ΔWR azar | ΔE azar % | Episodios + | Meses + |
|---|---|---|---|---|---|---|---|---|---|---|---|
| P1 | 0.24 % | 169 | 0 | 75.7 % | [68.8, 81.6] | +0.170 | 0.37 | +12.9 pt | +0.882 | 72 % de 18 | 10/12 |
| C0 | 0.24 % | 200 | 0 | 75.5 % | [69.1, 80.9] | +0.234 | 0.60 | +12.7 pt | +0.939 | 76 % de 29 | 10/14 |
| S3 | 0.24 % | 164 | 0 | 76.8 % | [69.8, 82.6] | +0.285 | 0.61 | +14.0 pt | +1.001 | 76 % de 17 | 10/12 |
| S1 | 0.24 % | 1051 | 0 | 72.1 % | [69.3, 74.7] | +0.216 | 0.60 | +11.1 pt | +1.004 | 66 % de 29 | 8/14 |
| P1 | 0.30 % | 169 | 0 | 75.7 % | [68.8, 81.6] | +0.110 | 0.24 | +13.0 pt | +0.882 | 72 % de 18 | 8/12 |
| C0 | 0.30 % | 200 | 0 | 75.5 % | [69.1, 80.9] | +0.174 | 0.45 | +12.8 pt | +0.939 | 76 % de 29 | 9/14 |
| S3 | 0.30 % | 164 | 0 | 76.8 % | [69.8, 82.6] | +0.225 | 0.48 | +14.2 pt | +1.001 | 76 % de 17 | 9/12 |
| S1 | 0.30 % | 1051 | 0 | 72.0 % | [69.2, 74.7] | +0.156 | 0.43 | +11.1 pt | +1.004 | 66 % de 29 | 8/14 |
| P1 | 0.19 % (BNB) | 169 | 0 | 75.7 % | [68.8, 81.6] | +0.220 | 0.48 | +12.8 pt | +0.882 | 72 % de 18 | 10/12 |
| C0 | 0.19 % (BNB) | 200 | 0 | 75.5 % | [69.1, 80.9] | +0.284 | 0.73 | +12.6 pt | +0.939 | 76 % de 29 | 10/14 |
| S3 | 0.19 % (BNB) | 164 | 0 | 76.8 % | [69.8, 82.6] | +0.335 | 0.71 | +13.9 pt | +1.001 | 76 % de 17 | 10/12 |
| S1 | 0.19 % (BNB) | 1051 | 0 | 72.1 % | [69.3, 74.7] | +0.267 | 0.74 | +11.0 pt | +1.005 | 66 % de 29 | 8/14 |
| P1 | 0.17 % (BNB + TP límite) | 169 | 0 | 75.7 % | [68.8, 81.6] | +0.235 | 0.51 | +12.8 pt | +0.885 | 72 % de 18 | 10/12 |
| C0 | 0.17 % (BNB + TP límite) | 200 | 0 | 75.5 % | [69.1, 80.9] | +0.299 | 0.77 | +12.6 pt | +0.942 | 76 % de 29 | 10/14 |
| S3 | 0.17 % (BNB + TP límite) | 164 | 0 | 76.8 % | [69.8, 82.6] | +0.350 | 0.75 | +13.9 pt | +1.004 | 76 % de 17 | 10/12 |
| S1 | 0.17 % (BNB + TP límite) | 1051 | 0 | 72.1 % | [69.3, 74.7] | +0.281 | 0.78 | +11.0 pt | +1.007 | 66 % de 29 | 8/14 |

## Criterios de P1 (sección 8.3), con lo que hay hasta hoy

1. E +0.170 %, t por día 0.37; con 0.30 %: +0.110 %. No cumple.
2. WR 75.7 %, Wilson [68.8, 81.6]. Nivel: ninguno.
3. ΔE frente al azar +0.882 % (t 1.89), ΔWR +12.9 pt; frente al azar con A4 ≥ 1: ΔE +0.364 %, ΔWR +4.0 pt. Cumple.
4. P(E(P1) − E(C0 con A4 = 0) ≤ 0) = 0.637 (bootstrap por días). No cumple.
5. Episodios positivos 72 % de 18. Cumple.
6. Hashes intactos (se verifican antes de evaluar).

E-proceso del WR (p0 = 0.70): M = 2.692. Futilidad: no. 400 operaciones: no.

**S3 (D1):** 6158 señales de P1, 16 vetadas y cerradas (WR 62.5 %, 5 episodios); 0 velas sin DVOL.

## PnL por moneda: P1 (0.24 %, 15 USDT por operación)

| Moneda | n | WR | E % | PnL USDT |
|---|---|---|---|---|
| SOLUSDT | 39 | 79.5 % | +0.483 | +2.82 |
| ETHUSDT | 37 | 75.7 % | +0.284 | +1.57 |
| DOGEUSDT | 55 | 74.5 % | +0.113 | +0.94 |
| BTCUSDT | 38 | 73.7 % | -0.180 | -1.02 |
| **COMBINADO** (3/4 ganan) | 169 | 75.7 % | +0.170 | +4.31 |

## PnL por moneda: S1 (0.24 %, 15 USDT por operación)

| Moneda | n | WR | E % | PnL USDT |
|---|---|---|---|---|
| FILUSDT | 56 | 75.0 % | +1.135 | +9.53 |
| NEARUSDT | 65 | 75.4 % | +0.590 | +5.75 |
| ADAUSDT | 75 | 72.0 % | +0.413 | +4.64 |
| DOGEUSDT | 69 | 78.3 % | +0.438 | +4.53 |
| AVAXUSDT | 67 | 76.1 % | +0.432 | +4.34 |
| DOTUSDT | 57 | 71.9 % | +0.365 | +3.12 |
| UNIUSDT | 50 | 70.0 % | +0.373 | +2.80 |
| BNBUSDT | 60 | 80.0 % | +0.296 | +2.66 |
| SOLUSDT | 42 | 78.6 % | +0.360 | +2.27 |
| ETCUSDT | 59 | 66.1 % | +0.223 | +1.97 |
| ETHUSDT | 40 | 75.0 % | +0.304 | +1.82 |
| ATOMUSDT | 62 | 66.1 % | +0.108 | +1.01 |
| XRPUSDT | 77 | 72.7 % | +0.084 | +0.97 |
| LINKUSDT | 47 | 70.2 % | +0.023 | +0.16 |
| LTCUSDT | 46 | 67.4 % | -0.250 | -1.72 |
| BTCUSDT | 46 | 69.6 % | -0.340 | -2.35 |
| TRXUSDT | 60 | 65.0 % | -0.391 | -3.52 |
| BCHUSDT | 73 | 68.5 % | -0.352 | -3.86 |
| **COMBINADO** (14/18 ganan) | 1051 | 72.1 % | +0.216 | +34.13 |

**Datos:** metrics faltantes por moneda (fase 1 pide ≤ 5 %): BTCUSDT 0.0 %, ETHUSDT 0.0 %, SOLUSDT 0.0 %, DOGEUSDT 0.0 %, ADAUSDT 0.0 %, ATOMUSDT 0.0 %, AVAXUSDT 0.0 %, BCHUSDT 0.0 %, BNBUSDT 0.0 %, DOTUSDT 0.0 %, ETCUSDT 0.0 %, FILUSDT 0.0 %, LINKUSDT 0.0 %, LTCUSDT 0.0 %, NEARUSDT 0.0 %, TRXUSDT 0.0 %, UNIUSDT 0.0 %, XRPUSDT 0.0 %.
