# E02 umbral con garantia (diseno, ENS13, X5)

| Config | n | WR % [Wilson 95] | E neta % | E_R | t día | Azar WR % / E % | ΔWR pt / ΔE % | t(ΔE) día |
|---|---|---|---|---|---|---|---|---|
| v2: max E con WR_val >= 0.75 | 188 | 81.4 [75.2, 86.3] | +1.41 | +0.145 | 4.80 | 61.7 / -0.43 | +19.7 / +1.83 | 5.78 |
| LTT Bonferroni, WR >= 0.75 (delta 0.10, n_ef = dias) | 0 | – | – | – | – | – | – | – | – |
| LTT Bonferroni, WR >= 0.8 (delta 0.10, n_ef = dias) | 0 | – | – | – | – | – | – | – | – |
| LTT calibracion agrandada, WR >= 0.7 | 143 | 79.0 [71.6, 84.9] | +1.15 | +0.115 | 2.50 | 62.7 / -0.37 | +16.3 / +1.52 | 3.19 |
| LTT calibracion agrandada, WR >= 0.75 | 0 | – | – | – | – | – | – | – | – |
| Conforme Jin-Candes + BH, FDR 0.25 (no causal) | 1161 | 70.3 [67.6, 72.8] | +0.17 | +0.005 | 1.09 | 64.7 / -0.23 | +5.6 / +0.40 | 2.62 |
| Conforme Jin-Candes + BH, FDR 0.2 (no causal) | 520 | 75.2 [71.3, 78.7] | +0.64 | +0.063 | 3.13 | 65.1 / -0.17 | +10.1 / +0.81 | 3.85 |

## WR realizado por pliegue (velas seleccionadas, por vela) y operaciones simuladas

| Regla | P0 | P1 | P2 | P3 | P4 | P5 | pliegues bajo objetivo |
|---|---|---|---|---|---|---|---|
| v2: max E con WR_val >= 0.75 | 540 v / 91 % · 19 op / 84 % | 379 v / 62 % · 24 op / 75 % | 922 v / 79 % · 37 op / 78 % | 868 v / 82 % · 35 op / 86 % | 389 v / 70 % · 34 op / 74 % | 483 v / 86 % · 39 op / 90 % | 1 de 6 (objetivo 0.75) |
| LTT Bonferroni, WR >= 0.75 (delta 0.10, n_ef = dias) | 0 | 0 | 0 | 0 | 0 | 0 | 0 de 6 (objetivo 0.75) |
| LTT Bonferroni, WR >= 0.8 (delta 0.10, n_ef = dias) | 0 | 0 | 0 | 0 | 0 | 0 | 0 de 6 (objetivo 0.80) |
| LTT calibracion agrandada, WR >= 0.7 | 1548 v / 86 % · 55 op / 80 % | 0 | 1520 v / 77 % · 58 op / 79 % | 0 | 282 v / 72 % · 30 op / 77 % | 0 | 0 de 6 (objetivo 0.70) |
| LTT calibracion agrandada, WR >= 0.75 | 0 | 0 | 0 | 0 | 0 | 0 | 0 de 6 (objetivo 0.75) |
| Conforme Jin-Candes + BH, FDR 0.25 (no causal) | 11479 v / 75 % · 239 op / 76 % | 26247 v / 62 % · 291 op / 64 % | 17693 v / 67 % · 301 op / 65 % | 216 v / 97 % · 13 op / 92 % | 2578 v / 65 % · 122 op / 68 % | 6213 v / 81 % · 195 op / 79 % | 3 de 6 (objetivo 0.75) |
| Conforme Jin-Candes + BH, FDR 0.2 (no causal) | 5722 v / 81 % · 141 op / 77 % | 850 v / 68 % · 45 op / 71 % | 11026 v / 71 % · 236 op / 69 % | 150 v / 97 % · 10 op / 90 % | 61 v / 92 % · 10 op / 90 % | 1638 v / 87 % · 78 op / 87 % | 3 de 6 (objetivo 0.80) |

Umbrales por pliegue: {"LTT 0.75": [null, null, null, null, null, null], "LTT 0.8": [null, null, null, null, null, null], "LTT agrandada 0.7": [[0.692, 0.899, 31, "7.2e-03"], null, [0.675, 0.837, 81, "3.0e-03"], [0.682, 0.831, 68, "6.9e-03"], [0.673, 0.814, 107, "5.6e-03"], [0.674, 0.814, 99, "5.4e-03"]], "LTT agrandada 0.75": [null, null, null, null, null, null], "BH 0.25": [11479, 26247, 17693, 216, 2578, 6213], "BH 0.2": [5722, 850, 11026, 150, 61, 1638]}
