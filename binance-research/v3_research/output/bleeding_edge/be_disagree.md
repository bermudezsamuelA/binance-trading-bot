# E09 desacuerdo del ensamble y calibracion de la cola; E01d bootstrap de la compuerta A_model (diseno)

## (1) Desacuerdo entre los 13 modelos (desviacion de las probabilidades), senales v2, resultado por vela

| Tercil de desacuerdo | velas | dias | WR vela % | E vela % |
|---|---|---|---|---|
| T1 (poco desacuerdo) | 1131 | 76 | 77.3 | +1.08 |
| T2 | 1168 | 64 | 76.6 | +1.11 |
| T3 (mucho desacuerdo) | 1282 | 53 | 84.1 | +1.79 |

Correlacion desacuerdo vs p_hat en las senales: +0.20 (si es alta, filtrar por desacuerdo corta las mejores senales).

| Config | n | WR % [Wilson 95] | E neta % | E_R | t día | Azar WR % / E % | ΔWR pt / ΔE % | t(ΔE) día |
|---|---|---|---|---|---|---|---|---|
| v2 | 188 | 81.4 [75.2, 86.3] | +1.41 | +0.145 | 4.80 | 61.7 / -0.43 | +19.7 / +1.83 | 5.78 |
| v2 y desacuerdo en T1-T2 (abstenerse en T3) | 165 | 81.2 [74.6, 86.4] | +1.35 | +0.146 | 4.41 | 61.6 / -0.44 | +19.6 / +1.78 | 5.66 |
| v2 y desacuerdo en T1 | 123 | 78.9 [70.8, 85.1] | +1.13 | +0.119 | 3.07 | 61.0 / -0.50 | +17.9 / +1.63 | 4.18 |

## (2) Calibracion en la cola (todas las velas de test, resultado X5 por vela)

| Cuantil de p_hat | velas | p_hat Platt medio (etiqueta G3) | isotonica X5 media | WR X5 realizado % |
|---|---|---|---|---|
| [0.653, 0.664] | 10502 | 0.657 | 0.756 | 70.0 |
| [0.664, 0.682] | 6302 | 0.672 | 0.783 | 72.5 |
| [0.682, 0.696] | 2100 | 0.688 | 0.804 | 83.1 |
| [0.696, 0.707] | 1050 | 0.701 | 0.879 | 82.1 |
| [0.707, 0.791] | 1051 | 0.726 | 0.972 | 84.6 |

| Config | n | WR % [Wilson 95] | E neta % | E_R | t día | Azar WR % / E % | ΔWR pt / ΔE % | t(ΔE) día |
|---|---|---|---|---|---|---|---|---|
| isotonica X5 >= 0.8 (sin umbral v2) | 289 | 74.7 [69.4, 79.4] | +0.69 | +0.048 | 2.21 | 62.1 / -0.45 | +12.6 / +1.14 | 3.56 |

| Config | n | WR % [Wilson 95] | E neta % | E_R | t día | Azar WR % / E % | ΔWR pt / ΔE % | t(ΔE) día |
|---|---|---|---|---|---|---|---|---|
| isotonica X5 >= 0.85 (sin umbral v2) | 128 | 80.5 [72.8, 86.4] | +1.60 | +0.138 | 3.65 | 60.5 / -0.43 | +19.9 / +2.03 | 4.44 |

## (3) Bootstrap por dias (5000) de la compuerta A_model W=48 sobre las 188 operaciones v2

- E(A>=1) - E(A=0) = +1.04 % ; IC 95 % [+0.15, +1.97] ; P(dif <= 0) = 0.010
- WR(A>=1) - WR(A=0) = +8.1 pt ; IC 95 % [-2.2, +19.5] ; P(dif <= 0) = 0.066
- n(A>=1) = 111 en 41 dias; n(A=0) = 77 en 68 dias
