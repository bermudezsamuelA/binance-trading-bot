# Auditoria de fugas de la v2 (escrita ANTES de ejecutar la prueba; 2026-10-14 07:05 VST)

- Hashes de spec_nn_v2.json: 8 scripts y 20 archivos de modelo coinciden.
- Lista blanca: H.SYMBOLS = BTC, ETH, SOL, DOGE; caches de entrenamiento (tmp/nn_cache, tmp/nn_cache_v2) solo con esas 4
  monedas y t max = 2025-06-30 23:45; research/futures solo esas 4 hasta 2025-06-30; ningun archivo de las 14 monedas
  reservadas/gastadas fuera de research/verificador; el codigo nn/ no nombra ninguna (salvo un ejemplo de uso en un docstring);
  holdout_log.csv sin entradas del Constructor.
- Perturbacion del futuro (audit_v2.py): 12 cortes (DOGE, BTC; incl. 2024-03-04): 74 variables y 10 canales de secuencia de
  la CNN identicos antes del corte (dif. 0.0), ~90 % cambiados despues.
- Umbral: con los 13 modelos congelados, el cuantil 0.98 de p en la validacion [2025-04-01, 2025-07-01 - 289 velas)
  (33 788 velas, etiquetas X5) = 0.714268362561, identico; choose() devuelve WR_val 0.987, E_val 2.18 %, 676 velas.
- Purga / "fuga leve": en la v1 la validacion terminaba 193 velas antes del test (horizonte G3), pero el umbral de la v2 usa
  etiquetas X5 (288 velas): las ultimas ~95 velas de validacion miraban hasta ~1 dia del test (en el walk-forward). Corregido
  con 289 velas en nn_v2_report.run (okv) y nn_v2_final (val < 2025-07-01 - 289). Verificado: la ultima vela de validacion es
  2025-06-27 23:30 y la ultima salida X5 usada 2025-06-30 16:45 (< 2025-07-01). Ajuste < 2025-04-01 - 193 (etiqueta G3).
- Prueba de humo reproducida (2024-01..2025-03, dentro de muestra): n 228, WR 84.6 %, E +1.615 %, identico.
- Sesgo de seleccion (no fuga): X5, WR_val >= 0.75 y el ensamble de 13 se eligieron mirando el walk-forward (20 configs).
- Conclusion: SIN FUGAS -> criterio (d) cumple. Se autoriza la ejecucion unica primaria_v2.
