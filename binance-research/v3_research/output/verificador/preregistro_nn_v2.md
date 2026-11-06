# Pre-registro v2: candidato NN v2 del Constructor

Lo redactó el Verificador el **2026-10-14 a las 06:59 VST, antes de recibir la especificación v2 y sin haber visto ningún resultado suyo**. No se modifica después de la ejecución.

## 1. Conjunto de prueba (fijado por el coordinador antes de la v2)

- **Prueba primaria.** Un conjunto **nuevo** de 8 monedas spot USDT que el equipo no ha usado. Las entradas van del **2025-07-01 al 2026-10-01** (semiabierto).
- **Custodia.** La lista y los datos están bajo custodia del Verificador, en el anexo reservado `research/verificador/preregistro_nn_v2_reservado.md`. Su SHA256 es `e2db3a0707ca56a1a80314b4cfb81cca768a0c048e91dc5fcf395541d8ac5d28`. Se revelará con el veredicto: el hash permite comprobar que el conjunto no cambió.
- **Solo descriptivas, sin peso en el veredicto:** las 6 monedas de la fase 2 (ya gastadas) y las 4 originales.
- **Condición de validez de la v2.** Para entrenar, seleccionar, fijar el umbral o hacer la parada temprana solo puede usar datos anteriores al 2025-07-01, y solo de una lista blanca de monedas que declare en su especificación (recomendado: BTC, ETH, SOL y DOGE).
  - Si la v2 usó cualquier dato de una moneda del conjunto reservado, en cualquier periodo, la prueba primaria queda **anulada**.
  - La auditoría revisa los símbolos y las fechas que carga el código.

## 2. Criterios (los MISMOS que en `preregistro_nn.md`; se exigen los cuatro)

| | Criterio |
|---|---|
| **(a)** | E neta > 0 **y** t agrupado por día > 1.645 **y** E neta > 0 con costos de 0.30 % |
| **(b)** | Límite inferior de Wilson al 95 % del WR (P(neto > 0)) **≥ 0.70** |
| **(c)** | ΔE frente al azar emparejado (misma moneda, mismo mes, misma geometría, 200 repeticiones) > 0 con p < 0.05 en la prueba pareada agrupada por día **y** en la de repeticiones |
| **(d)** | Auditoría sin fugas: perturbación del futuro, alineación de las fuentes, umbral reproducido con la validación, purga, escaladores, datos prohibidos y reproducción independiente |

- **Veredicto.** ACEPTA solo si se cumplen (a), (b), (c) y (d).
- **Reporte separado de dos preguntas:**
  - **(A) ¿Hay ventaja?** Criterios (a), (c) y (d).
  - **(B) ¿Se demuestra WR ≥ 70 %?** Criterio (b), más el WR puntual con su IC (con n bruto y con n efectivo) y la comparación entre diseño y prueba.
- **Una sola candidata congelada.** Si llegan K > 1, se aplica Holm a (a) y (c) y Wilson al nivel 1 − 0.05/K a (b).
- **Ejecución.** Una sola vez, con `verify.py --final primaria_v2`. El código es el mismo que en la fase 2 (SHA256 `0aeb80997c89e09bccfd4da0216b9b57ab0fc56f6bdf2575c5e504082ddb3d7b`). Costos: 0.24 % y, en estrés, 0.30 %.

## 3. Configuraciones acumuladas

- `trials_log.csv` suma **12 342** configuraciones al 2026-10-14 06:58: las 12 268 del equipo anterior, más las 54 de la v1 y 20 posteriores del Constructor.
- El DSR (informativo) usará el total que tenga el registro en el momento de ejecutar. El Constructor debe registrar **todas** las configuraciones de la v2.

## 4. Potencia

- **Cálculo reservado.** La potencia de (b) y de (a) a la frecuencia observada está en el anexo reservado (`power_v2.py`).
- **Referencia pública** (ver `preregistro_nn.md` §5): para que (b) pueda cumplirse hace falta un WR verdadero claramente mayor que 0.72. Con WR 0.75 se necesitan ≥ 324 operaciones observadas, y ≈ 625 para una potencia del 80 %.
