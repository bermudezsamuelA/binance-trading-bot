# Auditoria de fugas del candidato ENS6 (escrita ANTES de ejecutar las pruebas; 2026-10-14 06:47 VST)

- Hashes de spec_nn.json: 7 scripts y 9 archivos de modelo coinciden.
- Perturbacion del futuro (audit_nn.py): en 16 cortes (SOL, ETH; incl. 2023, el 2024-03-03/04 y 2025) se alteraron spot, BTC,
  metrics (T > t+5 y T > t+10 min), funding (calc_time > cierre), premium y klines UM posteriores al corte; las 74 variables
  de todas las velas <= corte quedaron identicas (dif. 0.0e+00) y cambiaron en ~90 % despues.
- Alineacion empirica: klines UM 15 m correlacion 0.998 con spot a desfase 0 (~0 a +-1); extremos de premiumIndex coinciden con
  la vela de la divergencia futuros/spot o la siguen (nunca la anticipan). Metrics: T <= t_i + 5 min (mas estricto que mi regla).
  Funding: calc_time <= cierre (calc_time trae +0..9 ms: conservador).
- Umbral: recalculado con los modelos congelados, el cuantil 0.98 de p en la validacion 2025-04..06 (34 172 velas) = 0.713364215387,
  identico al congelado; choose_threshold devuelve lo mismo. Platt y parada temprana solo en validacion.
- Purga H+1 = 193 velas antes de validacion y test; etiquetas (triple barrera) no estan entre las variables; escalador del MLP
  ajustado en el tramo de ajuste; z-scores rodantes causales; BTC alineado por open_time con relleno hacia adelante.
- Datos del Constructor: futuros solo hasta 2025-06-30; ninguna entrada suya en holdout_log.csv; ninguna moneda reservada.
- Prueba de humo reproducida (2025-04..06, dentro de muestra para el umbral): n 51, WR 86.3 %, E +1.72 %, identico al reportado;
  verify.py replica las 51 salidas sin discrepancias.
- Conclusion: SIN FUGAS DETECTADAS -> criterio (d) = cumple. Se autoriza la ejecucion unica.
