# Laboratorio: resumen consolidado de las rondas 1, 2A y 2B

**Alcance:** solo diseño (pruebas *walk-forward* 2024-01..2025-06; BTC, ETH, SOL y DOGE). El *holdout* no se tocó.

**Configuraciones registradas en `log_trials`:**

| Registro | Configuraciones |
|---|---|
| `bleeding_edge_r2`, ronda 1 | 132 |
| `bleeding_edge_r2`, ronda 2A | 33 |
| `bleeding_edge_r2`, ronda 2B | 13 |
| `bleeding_edge_r2_A_peek` (el vistazo del Investigador A) | 30 |
| **Total** | **208** |

**Informes de detalle:** `laboratorio_r1.md`, `laboratorio_r2a.md` y `laboratorio_r2b.md`, en esta misma carpeta.

## 1. Pila final recomendada (v3)

**v3 = v2 ENS13 + co-señal A ≥ 1 (W = 48) + salida X5 con barrera de tiempo H = 384 (96 h).** Se completa con:

- comisiones con BNB y TP con orden límite;
- reglas de riesgo: MAX3 posiciones y tope de riesgo por episodio, según la sección 3.3 del documento.

**E7 (H = 384) queda ADOPTADA**, con una reserva: si la deriva es bajista, su ganancia de E puede desaparecer.

**Cifras de diseño de v3:**

| Ensamble | n | WR [Wilson] | WR beta-binomial por episodio | E | E_R | t día | Episodios (positivos) | Meses positivos | Δ frente a la pila (v2 + A ≥ 1) | P_ep(ΔWR ≤ 0) / P_ep(ΔE ≤ 0) |
|---|---|---|---|---|---|---|---|---|---|---|
| ENS13 | 131 | **87.8 % [81.1, 92.3]** | 87.8 % [81.6, 93.0] | **+2.02 %** (+2.07 % con BNB) | +0.206 | 5.75 | 24 (92 %) | 15 de 15 | **+2.3 pt / +0.12 %** | 0.04 / 0.00 |
| ENS12 | 108 | 87.0 % | — | +1.90 % | — | — | — | — | +3.4 / +0.21 | — |
| ENS12U | 336 | 81.8 % | — | +1.09 % | — | — | — | — | +3.3 / +0.11 | — |

## 2. Qué pasó, qué quedó con reserva y qué se rechazó

| Pieza | Ronda | Tipo | ENS13: ΔWR pt / ΔE % (base) | Réplica | Estado |
|---|---|---|---|---|---|
| **E7: H 288 → 384** | 1 | Salida | +2.3 / +0.12 (X5); +1.5 / +0.07 en *walk-forward* | ENS12 +3.4 / +0.21; ENS12U +3.3 / +0.11 | **ADOPTADA** (reserva: deriva bajista) |
| **D1: veto si z30 del DVOL de BTC < −1** | 2B | Selección, de episodio | +3.9 / +0.35 (X5); +3.3 / +0.33 (v3) | ENS12 +4.7 / +0.43; ENS12U +2.8 / +0.21; ENS6 +2.5 / +0.26. Todos los pliegues con vetos mejoran; las señales aisladas se replican en 7 de 8 casos | **Con reserva.** Falla solo la condición del azar condicionado (explica el 63–129 %). Son los mismos 5–7 episodios en todos los ensambles. Va al brazo S3 y a la prueba de 2022 |
| D2: corte por tercil de entrenamiento y validación | 2B | Episodio | +4.6 / +0.37 | Igual que D1 (Holm 0.02–0.16) | Con reserva: es una variante de D1 y no añade nada |
| G_BE (co-señal de BTC o ETH), F_rank1 (la moneda que inicia el pánico), E13 (episodio ≥ 3 días después del anterior), E11 (BTC > SMA de 30 días) | 1 | Selección (de episodio y dentro) | +2.4 a +4.7, con E ≥ 0 | El signo se replica en 2–3 de 3 ensambles | Hipótesis: inestables por pliegue y con n chico |
| H1: rezagados (las otras 3 anclas ya rebotaron) | 2A | Episodio | +0.8 / −0.04 | ENS12 +1.1; ENS12U +0.5 | No pasa. Está contaminada; se graba hacia adelante |
| H5: prioridad por antigüedad bajo cupo | 2A | Dentro del episodio | 0.0 (no medible con 4 monedas) | — | Probarla en el *holdout* de 20 monedas |
| Frontera WR–E: TP2 = +0.6 % desde 36 h, o geometría (0.6, 1.75, 384) | 1 (*post hoc*) | Salida | +4.7 / −0.05; +4.0 / −0.08 | De +4.4 a +6.6 pt con ΔE de −0.07 a +0.06 | Palanca de preferencias, no mejora. Brazo opcional |
| Geometría elegida en WF (E1 y E15), re-entrada tras TP, segunda etapa logística (LR5 y LR6), cortacircuitos tras SL, MAX2 o MAX3 como mejora, co-firma de ENS12U, θ elegido con la compuerta | 1 | — | De −8 a +1.7, con ΔE ≤ 0 | — | Rechazadas (MAX3 se mantiene como regla de riesgo) |
| H2 TP anclado a la brecha, H3 TP2 por estado, H4 meta-etiquetado bayesiano, H6 *funding* previo, H7 divergencia de OI y *taker*, H8a y H8b calibración beta y θ por episodio, H9 Platt mensual, H10 co-firma G5 | 2A | — | De −13.6 a +8.4, todas con ΔE < 0 o ΔWR < 1 | — | Rechazadas. H2 solo redistribuye WR y E; H3 es una toma parcial disfrazada (se dispara en el 70 %) |
| C1 desvío de USDT-USD en Coinbase; B1 margen de Bitfinex (dos colas) | 2B | Episodio | −0.6 / −0.07; −2.5 y −0.6 | C1 mixta; B1 negativa (no ejecutada en ENS12U ni ENS6 por cobertura) | Rechazadas |

## 3. Cifras de diseño y estimación fuera de muestra

| Pila | Diseño ENS13: n · WR · E | WR fuera de muestra | E fuera de muestra | Encogimiento |
|---|---|---|---|---|
| v2 + A ≥ 1 (pila anterior) | 131 · 85.5 % · +1.90 % | 72–78 % | +0.6 a +1.1 % | Estimación del Juez: la v2 retuvo ≈ 48 % de su ventaja sobre el azar (de +19.7 a +9.4 pt), y la co-señal, un 50–75 % |
| **v3 = + H 384 (adoptada)** | 131 · 87.8 % · +2.02 % | **73–79 %** | **+0.6 a +1.2 %** | Se suman +1 a +1.5 pt. La parte estructural de E7 (≈ +1.7 pt, que el azar también gana) se retiene en un 70–100 % si la deriva no es negativa. La parte propia del modelo (≈ +0.6 pt), en un ≈ 50 % |
| v3 + D1 (brazo S3, sin adoptar) | 123 · 91.1 % · +2.35 % | ≈ 74–80 % | +0.65 a +1.4 % | D1 sumaría +0.5 a +2 pt (factor 0.3–0.6): el corte salió de mirar los datos y el n efectivo es de ≈ 6 episodios. Hay un 35–45 % de probabilidad de que su efecto real sea ≈ 0. Solo 2022 o la prospectiva pueden confirmarlo |

- **Un 80 % por operación con límite de Wilson ≥ 0.75 sigue siendo improbable.** Con v3, el objetivo realista es ≈ 75–78 % y ≈ 80 % de meses ganadores.
- El IC beta-binomial por episodio en diseño (81.6–93.0 %) muestra lo poco que se sabe con 24 episodios.

## 4. Brazos que propongo añadir al pre-registro (sección 8.2 del documento)

1. **P1 (principal) = v3.** Igual que la P1 actual, pero con H = 384 velas. Criterio: el mismo que P1.
2. **S3 = v3 + D1.** No comprar si el z30 del DVOL de BTC es < −1.
   - **Definición del z30:** con las últimas 720 horas cerradas, usando la hora con ts + 1 h ≤ apertura de la vela de señal. El dato sale de la API pública de Deribit, cada hora.
   - **Tipo:** regla de **episodio**.
   - **Criterio:** tras ≥ 150 señales de P1, las vetadas deben tener un WR menor que las conservadas, con P ≤ 0.10 en un *bootstrap* por episodio y en ≥ 5 episodios vetados.
   - **Estrés de 2022:** el DVOL existe desde 2021-03, pero el modelo necesita los *metrics* de futuros de Binance de 2022, que hoy no están en la máquina.
3. **S4 (opcional, solo si el usuario prioriza el WR sobre la E) = v3 + TP2 = +0.6 % desde las 36 h.**
   - En diseño da +4.7 pt de WR y −0.05 % de E.
   - Es *post hoc* y debe confirmarse por su cuenta.
4. **Reglas dentro del episodio para el *holdout* fresco de 20 monedas** (mismas fechas, monedas nuevas):
   - confirmar E7 en monedas nuevas;
   - probar H5 (con cupo MAX3, priorizar la moneda que dio señal primero en el episodio).
5. **Grabar hacia adelante desde ya** (todo es público y no depende de `fapi`):
   - DVOL de BTC y ETH, cada hora;
   - USDT-USD de Coinbase, en velas de 15 min;
   - margen de Bitfinex (`…/last`);
   - L4, el rebote de las otras 3 anclas (para H1);
   - los marcadores G_BE y F_rank1 de cada señal.
   - Así, las hipótesis de episodio se podrán probar con datos prospectivos limpios.

## 5. Advertencias

- Todo lo de diseño comparte los mismos 24 episodios. Las "réplicas" entre ensambles cambian las operaciones, pero **no los episodios**.
- Las reglas de episodio (D1, D2, H1, G_BE, E13 y E11) solo se pueden confirmar con episodios nuevos: 2022 o la prospectiva.
- E7 y H5 son reglas dentro del episodio, así que el *holdout* de 20 monedas sí puede confirmarlas.
