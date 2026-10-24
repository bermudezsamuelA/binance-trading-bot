# Canal sombra v3: prueba prospectiva (PROVISIONAL)

Periodo evaluado: **2026-10-01 a 2026-10-24 00:00 UTC** (hasta donde todas las series estan completas). Generado 2026-10-24T08:16:50Z. Umbral θ = 0.7143. No es la decisión final: el pre-registro termina el 2027-12-31 o 400 operaciones de P1, lo que llegue primero.

> **Provisional:** el funding desde el 2026-10-01 00:00 UTC se reconstruyó con la prima del perpetuo (Binance aún no publica el archivo del mes). Equivalencia con el funding real en 2026-09-01 a 2026-10-01 00:00: señales Jaccard 0.92, P1 Jaccard 1.0 (equivalente). Las cifras definitivas salen cuando se publique el funding real.

| Brazo | Costo | n | Abiertas | WR | Wilson 95 % | E % | t/día | ΔWR azar | ΔE azar % | Episodios + | Meses + |
|---|---|---|---|---|---|---|---|---|---|---|---|
| P1 | 0.24 % | 6 | 0 | 66.7 % | [30.0, 90.3] | -0.525 | -0.41 | +11.3 pt | +0.378 | 50 % de 2 | 0/1 |
| C0 | 0.24 % | 7 | 0 | 71.4 % | [35.9, 91.8] | -0.178 | -0.15 | +16.6 pt | +0.782 | 50 % de 2 | 0/1 |
| S3 | 0.24 % | 6 | 0 | 66.7 % | [30.0, 90.3] | -0.525 | -0.41 | +11.3 pt | +0.378 | 50 % de 2 | 0/1 |
| S1 | 0.24 % | 33 | 0 | 72.7 % | [55.8, 84.9] | +0.199 | 0.14 | +19.4 pt | +1.378 | 50 % de 2 | 1/1 |
| P1 | 0.30 % | 6 | 0 | 66.7 % | [30.0, 90.3] | -0.585 | -0.46 | +11.4 pt | +0.378 | 50 % de 2 | 0/1 |
| C0 | 0.30 % | 7 | 0 | 71.4 % | [35.9, 91.8] | -0.238 | -0.20 | +16.7 pt | +0.782 | 50 % de 2 | 0/1 |
| S3 | 0.30 % | 6 | 0 | 66.7 % | [30.0, 90.3] | -0.585 | -0.46 | +11.4 pt | +0.378 | 50 % de 2 | 0/1 |
| S1 | 0.30 % | 33 | 0 | 72.7 % | [55.8, 84.9] | +0.139 | 0.09 | +19.5 pt | +1.378 | 50 % de 2 | 1/1 |
| P1 | 0.19 % (BNB) | 6 | 0 | 66.7 % | [30.0, 90.3] | -0.475 | -0.37 | +11.2 pt | +0.378 | 50 % de 2 | 0/1 |
| C0 | 0.19 % (BNB) | 7 | 0 | 71.4 % | [35.9, 91.8] | -0.128 | -0.11 | +16.5 pt | +0.783 | 50 % de 2 | 0/1 |
| S3 | 0.19 % (BNB) | 6 | 0 | 66.7 % | [30.0, 90.3] | -0.475 | -0.37 | +11.2 pt | +0.378 | 50 % de 2 | 0/1 |
| S1 | 0.19 % (BNB) | 33 | 0 | 72.7 % | [55.8, 84.9] | +0.249 | 0.17 | +19.3 pt | +1.379 | 50 % de 2 | 1/1 |
| P1 | 0.17 % (BNB + TP límite) | 6 | 0 | 66.7 % | [30.0, 90.3] | -0.462 | -0.36 | +11.2 pt | +0.380 | 50 % de 2 | 0/1 |
| C0 | 0.17 % (BNB + TP límite) | 7 | 0 | 71.4 % | [35.9, 91.8] | -0.113 | -0.09 | +16.5 pt | +0.786 | 50 % de 2 | 0/1 |
| S3 | 0.17 % (BNB + TP límite) | 6 | 0 | 66.7 % | [30.0, 90.3] | -0.462 | -0.36 | +11.2 pt | +0.380 | 50 % de 2 | 0/1 |
| S1 | 0.17 % (BNB + TP límite) | 33 | 0 | 72.7 % | [55.8, 84.9] | +0.264 | 0.18 | +19.3 pt | +1.383 | 50 % de 2 | 1/1 |

## Criterios de P1 (sección 8.3), con lo que hay hasta hoy

1. E -0.525 %, t por día -0.41; con 0.30 %: -0.585 %. No cumple.
2. WR 66.7 %, Wilson [30.0, 90.3]. Nivel: ninguno.
3. ΔE frente al azar +0.378 % (t 0.27), ΔWR +11.3 pt; frente al azar con A4 ≥ 1: ΔE -0.252 %, ΔWR -4.0 pt. No cumple.
4. P(E(P1) − E(C0 con A4 = 0) ≤ 0) = 0.384 (bootstrap por días). No cumple.
5. Episodios positivos 50 % de 2. No cumple.
6. Hashes intactos (se verifican antes de evaluar).

E-proceso del WR (p0 = 0.70): M = 0.876. Futilidad: no. 400 operaciones: no.

**S3 (D1):** 32 señales de P1, 0 vetadas y cerradas (WR —, 0 episodios); 0 velas sin DVOL.

## PnL por moneda: P1 (0.24 %, 15 USDT por operación)

| Moneda | n | WR | E % | PnL USDT |
|---|---|---|---|---|
| BTCUSDT | 1 | 100.0 % | +0.772 | +0.12 |
| DOGEUSDT | 3 | 66.7 % | -0.472 | -0.21 |
| ETHUSDT | 2 | 50.0 % | -1.254 | -0.38 |
| **COMBINADO** (1/3 ganan) | 6 | 66.7 % | -0.525 | -0.47 |

## PnL por moneda: S1 (0.24 %, 15 USDT por operación)

| Moneda | n | WR | E % | PnL USDT |
|---|---|---|---|---|
| AVAXUSDT | 2 | 100.0 % | +2.747 | +0.82 |
| NEARUSDT | 1 | 100.0 % | +4.511 | +0.68 |
| LINKUSDT | 2 | 100.0 % | +2.149 | +0.64 |
| XRPUSDT | 2 | 100.0 % | +1.556 | +0.47 |
| DOTUSDT | 1 | 100.0 % | +2.949 | +0.44 |
| BTCUSDT | 1 | 100.0 % | +0.772 | +0.12 |
| DOGEUSDT | 4 | 75.0 % | +0.123 | +0.07 |
| UNIUSDT | 4 | 75.0 % | +0.109 | +0.07 |
| TRXUSDT | 2 | 50.0 % | -0.595 | -0.18 |
| BCHUSDT | 3 | 66.7 % | -0.551 | -0.25 |
| ADAUSDT | 3 | 66.7 % | -0.619 | -0.28 |
| BNBUSDT | 2 | 50.0 % | -1.089 | -0.33 |
| ETHUSDT | 2 | 50.0 % | -1.254 | -0.38 |
| LTCUSDT | 2 | 50.0 % | -1.307 | -0.39 |
| ETCUSDT | 2 | 50.0 % | -1.745 | -0.52 |
| **COMBINADO** (8/15 ganan) | 33 | 72.7 % | +0.199 | +0.99 |

**Datos:** metrics faltantes por moneda (fase 1 pide ≤ 5 %): BTCUSDT 0.0 %, ETHUSDT 0.0 %, SOLUSDT 0.0 %, DOGEUSDT 0.0 %, ADAUSDT 0.0 %, ATOMUSDT 0.0 %, AVAXUSDT 0.0 %, BCHUSDT 0.0 %, BNBUSDT 0.0 %, DOTUSDT 0.0 %, ETCUSDT 0.0 %, FILUSDT 0.0 %, LINKUSDT 0.0 %, LTCUSDT 0.0 %, NEARUSDT 0.0 %, TRXUSDT 0.0 %, UNIUSDT 0.0 %, XRPUSDT 0.0 %.
