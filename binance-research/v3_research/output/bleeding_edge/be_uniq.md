# E11 ponderacion por unicidad (LightGBM x3 semillas, diseno, salida X5, regla v2)

| Config | n | WR % [Wilson 95] | E neta % | E_R | t día | Azar WR % / E % | ΔWR pt / ΔE % | t(ΔE) día |
|---|---|---|---|---|---|---|---|---|
| LGB x3 sin ponderar (lgbv4 s0-s2) | 293 | 73.7 [68.4, 78.4] | +0.59 | +0.050 | 1.80 | 63.0 / -0.35 | +10.7 / +0.94 | 2.73 | brecha val−prueba (WR por vela): +13.8 pt
| LGB x3 ponderado por unicidad | 252 | 79.4 [73.9, 83.9] | +0.94 | +0.096 | 2.83 | 61.1 / -0.54 | +18.2 / +1.48 | 4.25 | brecha val−prueba (WR por vela): +7.6 pt
