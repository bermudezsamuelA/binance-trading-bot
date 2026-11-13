# Estrategia de extremos (video de YouTube): implementación y backtest (2026-11-02)

Código en `binance-research/extremos/` ([README](../binance-research/extremos/README.md)). Proyecto aparte: no toca las
estrategias del bot.

## Reglas implementadas

**1 · Diario (al cierre del día, en UTC).** Se tienen que cumplir las tres:

- **Extremo:**
  - Hay un soporte con al menos `toques` mínimos locales (pivote de 3 días a cada lado) dentro de ±0.5 ATR, todos del último año.
  - El mínimo de hoy entra en esa zona y el cierre no queda más de 0.5 ATR por debajo.
  - El mínimo de hoy está en el 25 % inferior del rango de 90 días.
- **Llega estirado:** en los últimos 5 días hubo un tramo de 5 velas con \(z \le -\theta\), donde \(z = \dfrac{\ln C_t - \ln C_{t-5}}{\sigma_d\sqrt{5}}\) y \(\sigma_d\) es la volatilidad diaria de los 30 días anteriores al tramo.
- **Frena y gira:**
  - Los cuerpos de las 3 últimas velas miden menos del 60 % de los de las 3 anteriores.
  - La mecha inferior media es al menos el 30 % de la vela.
  - Hoy cierra por encima de \(O_{t-1}\), de \(O_{t-2}\) y de \(C_{t-3}\).

**2 · 1 h, durante los 3 días siguientes a la señal.**

- El mínimo de la caída es el más bajo de las velas de 1 h desde 5 días antes de la señal.
- **Ruptura:** un cierre de 1 h por encima del último máximo local confirmado (3 velas a cada lado), después de ese mínimo.
- **Fibonacci:** se traza del mínimo al máximo del impulso.
- **Toque:** el precio toca \(P_{0.618} + 0.25\,\text{ATR}_{1h}\) con \(|\text{EMA}_{50} - P_{0.618}| \le c \cdot \text{ATR}_{1h}\).
- **Se descarta** si antes toca el 0.75.

**3 · Gatillo en 5 min**, hasta 6 h después del toque.

- Es la primera vela que cierra por encima de la diagonal de los dos últimos máximos decrecientes y/o de la EMA 20.
- Se compra a ese cierre.
- Si antes toca el 0.75, se cancela.

**Salida y costos.**

- **Stop:** en el 0.75. **Objetivo:** el máximo del impulso, o 1.6 veces el riesgo.
- Si no toca ninguno en 7 días, se vende al cierre. Si stop y objetivo caen en la misma vela, se cuenta el stop.
- **Costo:** 0.24 % ida y vuelta.
- Solo compras y una operación a la vez por moneda.

**Datos:**
- Velas spot de 5 min de 23 monedas, de 2021-10 a 2026-10, bajadas de `data.binance.vision`.
- El diario y el de 1 h se arman con esas mismas velas.
- **Diseño:** hasta 2024-12. **Validación:** desde 2025-01.
- **Criterio para adoptar:** E > 0 en validación, \(t \ge 2\), al menos 100 operaciones y además \(t \ge 2\) contando cada día de señal una sola vez. Una caída de mercado da señal en muchas monedas el mismo día, y esas operaciones no son casos independientes.

**Rejilla (64 combinaciones):**
- toques {2, 3}
- \(\theta\) {1.5, 2}
- condición 3 sí/no
- \(c\) {1, 2}
- gatillo {EMA 20, diagonal y EMA 20}
- objetivo {máximo, 1.6 R}

## Respuesta corta

**No pasa el criterio.**

- **Al pie de la letra** casi nunca opera: 1 operación en diseño y 1 en validación en 5 años y 23 monedas.
- **La mejor combinación de diseño** pierde en validación: −0.33 % por operación con 51 operaciones.
- **Lo único con algo de señal es el filtro diario solo:** comprar al día siguiente de las tres condiciones y vender 3 días después.

  | Periodo | Ganancia media | Estadístico t | Operaciones |
  |---|---|---|---|
  | Diseño | +0.69 % | 0.9 | 58 |
  | Validación | +2.21 % | 1.94 | 27 |

  En el mismo periodo, comprar todos los días perdió −0.57 %. Son muy pocos casos para fiarse.

## Resultados

| Variante | Diseño: n · E · acierto | Validación: n · E · acierto · t |
|---|---|---|
| Video al pie de la letra (2 toques, \(\theta = 2\), con condición 3, \(c = 1\), ambos gatillos, objetivo en el máximo) | 1 · −1.72 % · 0 % | 1 · +0.09 % · 100 % · — |
| Mejor en diseño (igual, pero sin condición 3 y \(c = 2\)) | 64 · +0.44 % · 36 % | 51 · **−0.33 %** · 29 % · −0.51 |
| Solo condiciones diarias, comprar al día siguiente y vender en 3 días | 58 · +0.69 % · 60 % | 27 · **+2.21 %** · 59 % · 1.94 |
| Comprar todos los días y vender en 3 días (referencia) | 6580 · +0.18 % · 48 % | 3838 · −0.57 % · 45 % · −4.4 |

Solo 2 de las 64 combinaciones ganan en validación con al menos 20 operaciones. La que más opera llega a 134
operaciones en validación.

## Walk-forward: elegir con todo el pasado y juzgar año por año

Para usar también 2025 al elegir parámetros sin contaminar la prueba, se eligen por bloques: con datos hasta 2023 se
juzga 2024, hasta 2024 se juzga 2025 y hasta 2025 se juzga 2026 (hasta octubre). En cada bloque gana la combinación con
mayor E en todo lo anterior, con al menos 20 operaciones. Se prueban dos familias:

- **Completa:** las 64 combinaciones de la estrategia del video.
- **Solo diario:** las tres condiciones diarias, comprar al abrir el día siguiente y vender a los 2, 3 o 5 días, sin stop (24 combinaciones).

| Familia | 2024 | 2025 | 2026 | Total fuera de muestra |
|---|---|---|---|---|
| Completa: n · E | 18 · +3.00 % | 22 · +0.90 % | 1 · −0.93 % | 41 · **+1.78 %** · \(t\) 1.75 · \(t\) por día 1.52 |
| Solo diario: n · E | 29 · +3.24 % | 32 · +2.66 % | 14 · −0.79 % | 75 · **+2.24 %** · \(t\) 3.20 · \(t\) por día **0.68** |
| Comprar todos los días, 3 días (referencia) | +0.30 % | −0.84 % | −0.47 % | — |

**La señal diaria sola parece buena, pero no lo es.** Sus 75 operaciones salen de solo 32 días distintos, y un solo
día, 2024-04-18, aporta 14 operaciones que ganaron +6.4 % cada una: fue el rebote de todo el mercado después de una
caída. Contando cada día una vez, la ganancia media baja a +0.78 % y \(t = 0.68\), que no se distingue del azar. Además,
2026 es negativo en las dos familias.

Ninguna de las dos pasa el criterio. Los parámetros elegidos fueron estables: 2 toques y \(\theta = 1.5\) o 2 en todos
los bloques.

## Dónde se pierden las señales (video al pie de la letra)

| Paso | Diseño | Validación |
|---|---|---|
| Días evaluados (moneda × día) | 26 311 | 15 387 |
| Condición 1: en el extremo | 7 087 | 5 072 |
| \+ condición 2: llegó estirado | 1 047 | 477 |
| \+ condición 3: frena y gira (señal diaria) | 76 | 33 |
| Sin toque del 0.618 en 3 días | 25 | 13 |
| Tocó el 0.618, pero la EMA 50 estaba lejos | 38 | 19 |
| Tocó el 0.75 antes del toque o del gatillo | 11 | 0 |
| **Operaciones** | **1** | **1** |

El paso más restrictivo es la confluencia con la EMA 50. En datos reales, la EMA 50 de 1 h casi nunca está cerca del
0.618 en el momento del toque, porque después de una caída fuerte la media queda muy arriba. Quitar la condición 3 y
ampliar \(c\) da más operaciones (64 y 51), pero con un acierto del 29–36 % no alcanza.

## Qué significa

1. El video describe la estrategia a ojo. Escrita como reglas exactas, casi nunca opera, y relajada para que opere más no gana en validación.
2. La señal diaria (extremo + caída fuerte + freno y giro) gana en promedio, pero casi todo viene de unos pocos rebotes de mercado que dan señal en muchas monedas a la vez. Contando cada día una vez, no se distingue del azar, ni con un corte fijo ni con walk-forward.
3. **Recomendación:** no llevarla al bot. Si se quiere seguir, la prueba útil sería tratar la señal como evento de mercado (por ejemplo, contar cuántas monedas la dan el mismo día) y juntar más años de datos, porque con unos 30 días de señal por periodo ningún resultado será concluyente.

## Cómo reproducir

```
cd binance-research/extremos
python descargar_5m.py
python -m unittest test_estrategia
python backtest.py
python backtest.py --walk-forward
```

La descarga tarda unos 3 minutos (450 MB de ZIP, 640 MB de `.npy`) y cada backtest otros 3. Las salidas quedan en
`binance-research/extremos/output/`.
