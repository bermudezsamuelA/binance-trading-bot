# Prueba en 20 monedas nuevas (pre-registro)

Escrito el 2026-10-24, **antes de descargar sus datos**. Ningún agente ni script del proyecto usó estas monedas.

- **Monedas (fijas):** AAVE, ALGO, APE, APT, AXS, CHZ, CRV, EGLD, EOS, GALA, HBAR, ICP, INJ, KAVA, LDO, MANA, OP, RUNE, SAND y XLM (pares USDT spot y su perpetuo USD-M). Se eligieron por ser pares líquidos con perpetuo desde antes de 2023 y con el mismo nombre en spot y en futuros, sin mirar ningún resultado.
- **Periodo:** 2023-03-01 a 2026-10-01.
- **Modelo:** el congelado (`spec_nn_v2.json`, hashes verificados), sin reentrenar ni cambiar el umbral.
- **Prueba principal:** C0 (v2 sin compuerta, salida X5 con 384 velas) en las 20 monedas, costo 0.24 %. Pasa si la E combinada es > 0 con t por día ≥ 1.645 y más de la mitad de las monedas ganan.
- **Descriptivo:** la regla de P1 aplicada a estas monedas (compuerta con las 4 anclas, cuyas señales de 2023-2025 son de diseño) y la de S1 con las 24 monedas. No deciden nada.

**Nota (2026-10-24, antes de ver resultados):** EOS no tiene velas spot desde mediados de 2025 (Binance la renombró), así que cortaría el periodo de todas las monedas. Queda fuera por falta de datos: la prueba usa las 19 restantes.
