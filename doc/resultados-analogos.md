# Resultados: predicción por análogos (2026-11-01)

Implementación del [plan](plan-analogos.md) con datos reales de Binance. Código en `binance-research/analogos/` y salidas completas en `binance-research/analogos/output/`.

**Condiciones de la prueba:**
- Velas de 1 h de BTC, ETH, SOL y DOGE, de 2021-10 a 2026-10.
- Biblioteca de vecinos con 24 h de margen y como máximo un vecino por bloque de 12 h y moneda.
- Una consulta cada 2 h.
- Regla: comprar si \(\hat y > 0.24\,\%\) y el consenso \(\pi \ge q\); vender a las \(h\) velas; sin solapar operaciones; 15 USDT por operación.
- Los parámetros se eligen solo en **diseño** (2023-01 a 2024-12) y se miden en **validación** (2025-01 a 2026-10).

**Criterio para adoptar una sugerencia:** E neta positiva en validación, con \(t \ge 2\) y al menos 100 operaciones.

## Respuesta corta

**Ninguna de las 5 sugerencias pasa el criterio.** Todas ganan en diseño, donde se eligen los parámetros, y pierden o quedan en cero en validación. El IC de validación está entre −0.02 y +0.03 en todas: la predicción prácticamente no se relaciona con lo que pasa después. La única versión con una E alta en validación es el control con fuga de futuro, que confirma que la prueba detecta la trampa.

## Tabla: la mejor combinación de cada sugerencia, elegida solo con diseño

| Sugerencia | Configuración elegida | E diseño | E validación | n validación | t validación | IC validación | ¿Pasa? |
|---|---|---|---|---|---|---|---|
| 1 · Forma del precio (k-NN) | forma z, L = 24, 1 moneda, h = 24, k = 30, con peso, q = 0.65 | +0.37 % | **−0.14 %** | 970 | −1.28 | +0.011 | No |
| 2 · DTW | r = 0 (sin deformación, igual a la 1), L = 48, h = 24, k = 30, q = 0.65 | +0.29 % | **−0.30 %** | 836 | −2.41 | −0.022 | No |
| 3 · Estado del mercado | forma + contexto, pesos aprendidos, PCA m = 4, h = 24, k = 100, q = 0.70 | +1.60 % | **−0.39 %** | 138 | −0.96 | +0.028 | No |
| 4 · Patrones como palabras | n = 3, 4 niveles, h = 12, ≥ 30 apariciones, con Bonferroni | +0.63 % | **−0.17 %** | 603 | −1.38 | +0.005 | No |
| 5 · Todas las monedas y filtro de 4 h | biblioteca de 1 moneda, sin filtro, h = 24, k = 100, q = 0.65 | +0.42 % | **−0.59 %** | 118 | −1.75 | −0.022 | No |
| Referencia: comprar siempre cada 24 h | — | +0.08 % | −0.27 % | — | — | — | — |

Validación (2025–2026) fue un periodo difícil para estas monedas: comprar a ciegas cada 24 h perdió −0.27 % por operación. Algunas reglas pierden menos que eso, pero ninguna gana.

## Detalle por sugerencia

**1 · Forma del precio.** Precio crudo −0.30 %, retornos −0.46 % y forma z −0.14 % en validación: normalizar la forma ayuda, pero no alcanza. Con la biblioteca de 4 monedas, −0.44 %.

**2 · DTW.** Ninguna banda mejora a la euclidiana. En validación, de la mejor variante de cada una:

| Banda | Horizonte fijo | Horizonte escalado |
|---|---|---|
| r = 0.05 | −0.26 % | −0.38 % |
| r = 0.10 | −0.24 % | −0.25 % |
| r = 0.20 | −0.19 % | −0.32 % |

La pendiente media del camino quedó en 0.99–1.00: en estas ventanas casi no hay patrones "más lentos o más rápidos" que aprovechar.

**3 · Estado del mercado.** Camino de mejoras en validación:

| Paso | E validación | t |
|---|---|---|
| Solo forma | −0.24 % | −0.81 |
| \+ contexto sin estandarizar | +0.02 % | +0.10 |
| \+ estandarizar | −0.08 % | −0.32 |
| \+ pesos aprendidos | **+0.12 %** | +0.53 |
| \+ PCA (m = 4) | −0.39 % | −0.96 |
| Solo contexto | +0.12 % | +0.46 |
| Control con fuga (sin margen) | +1.21 % | +3.27 |

El contexto mejora algo frente a la forma sola, pero nada se acerca a \(t = 2\). PCA fue la mejor en diseño (+1.60 %) y la peor en validación: es el ejemplo más claro de sobreajuste.

En entrenamiento, las variables con más relación con el futuro fueron el retorno de 24 h, la tendencia de BTC y el funding, todas con un IC de solo 0.05–0.06.

**4 · Palabras.** La corrección de Bonferroni reduce las operaciones de diseño de 403 a 125, pero no cambia el resultado. En validación pierde −0.16 % sin corrección y −0.17 % con ella.

**5 · Todas las monedas.** La biblioteca más grande no ayuda:
- 1 moneda: −0.59 %.
- 4 monedas: −0.45 %.
- 23 monedas: −0.21 %. Aquí solo el 8 % de los vecinos son de la misma moneda.

El filtro de 4 h empeora en todos los casos: −0.28 %, −0.61 % y −0.32 %.

## Qué significa

1. **El precio pasado, solo o con este contexto, no predice las 12–24 h siguientes lo bastante para pagar 0.24 % de comisión** en estas monedas y en estos años. Es el mismo resultado que dieron las estrategias de Bollinger.
2. **Elegir mirando los datos infla siempre el resultado.** Las 5 sugerencias ganaban entre +0.29 % y +1.60 % en diseño.
3. **El marco de prueba funciona.** Detecta la fuga de futuro (+1.21 % solo con trampa) y no deja pasar resultados de suerte. Se puede reutilizar para probar otras ideas.
4. **Recomendación:** no llevar ninguna de estas reglas al bot. Si se quiere seguir por esta línea, lo único con algo de señal es el contexto de la sugerencia 3, con pesos aprendidos (+0.12 %, \(t = 0.53\)). Tendría que mejorarse con información nueva, por ejemplo liquidaciones o flujo de órdenes, y validarse en monedas y meses que no se hayan mirado.

## Cómo reproducir

```
cd binance-research/analogos
python -m unittest test_common test_s2
python run_all.py
```

Unos 60 minutos en 4 núcleos (el más largo es la sugerencia 2, unos 30 min). Los datos son los `.npy` de `v3_research/tmp/data2022` y `v3_research/tmp/new20`; si están en otra carpeta, se indica con `ANALOGOS_DATA_DIRS`.
