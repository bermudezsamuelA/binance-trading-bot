# E27 cobertura beta con BTC y E26 umbral adaptativo ACI (diseno, ENS13, X5)

## E27 cobertura con BTC (solo operaciones en ETH, SOL y DOGE)

| Variante | n | WR % [Wilson] | E % | t día | σ por op % | peor op % | Azar con la misma cobertura: WR % / E % |
|---|---|---|---|---|---|---|---|
| h = 0.0 x beta (sin cobertura) | 141 | 81.6 [74.4, 87.1] | +1.63 | 4.35 | 4.42 | -11.4 | 64.9 / -0.22 |
| h = 0.5 x beta | 141 | 78.7 [71.3, 84.7] | +0.95 | 3.50 | 3.27 | -10.9 | 58.4 / -0.53 |
| h = 1.0 x beta | 141 | 59.6 [51.3, 67.3] | +0.27 | 1.14 | 2.88 | -10.3 | 41.2 / -0.83 |

## E26 umbral adaptativo en linea (ACI sobre la tasa de perdidas)

| Variante | n | WR % [Wilson] | E % | t día | WR por pliegue (%) |
|---|---|---|---|---|---|
| theta fijo v2 (referencia, mismo motor) | 188 | 81.4 [75.2, 86.3] | +1.41 | 4.80 | 84 (19), 75 (24), 78 (37), 86 (35), 74 (34), 90 (39) |
| ACI alpha 0.25, eta 0.005 | 230 | 77.4 [71.6, 82.3] | +0.95 | 3.09 | 80 (25), 56 (9), 79 (42), 75 (24), 71 (38), 82 (92) |
| ACI alpha 0.25, eta 0.02 | 282 | 74.1 [68.7, 78.9] | +0.51 | 1.61 | 60 (10), 62 (8), 75 (75), 72 (40), 74 (53), 77 (96) |
| ACI alpha 0.20, eta 0.005 | 188 | 78.2 [71.8, 83.5] | +1.12 | 3.62 | 82 (17), 43 (7), 78 (40), 78 (27), 70 (30), 85 (67) |
| ACI alpha 0.20, eta 0.02 | 131 | 72.5 [64.3, 79.4] | +0.58 | 1.17 | 60 (10), 60 (5), 76 (49), 62 (13), 73 (22), 78 (32) |
