# Predicción por análogos

Implementación del plan [`doc/plan-analogos.md`](../../doc/plan-analogos.md): buscar en el pasado los momentos más
parecidos al actual y usar lo que pasó después. Proyecto aparte: no usa ni modifica las estrategias del bot.
Resultados y decisión: [`doc/resultados-analogos.md`](../../doc/resultados-analogos.md).

| Archivo | Qué hace |
|---|---|
| `common.py` | Datos (velas de 15 min a 1 h, funding e interés abierto), periodos, búsqueda k-NN sin fuga (margen de 24 h y un vecino por episodio), regla de operación y métricas |
| `s1_knn.py` | Sugerencia 1: vecinos sobre la forma del precio (precio crudo, retornos, forma z; L, k, h, peso, q; 1 o 4 monedas) |
| `s2_dtw.py` | Sugerencia 2: re-ordenar los 200 candidatos euclidianos con DTW de banda r; horizonte escalado opcional |
| `s3_estado.py` | Sugerencia 3: vector de 10 variables (forma + contexto), estandarizado con el pasado, pesos aprendidos, PCA |
| `s4_palabras.py` | Sugerencia 4: patrones como palabras, conteo en línea, cota de Wilson y Bonferroni |
| `s5_multi.py` | Sugerencia 5: biblioteca de 1, 4 o 23 monedas y filtro con la temporalidad de 4 h |
| `run_all.py` | Corre todo: `python run_all.py` (o solo algunas: `python run_all.py s1 s3`) |
| `test_common.py`, `test_s2.py` | Pruebas: sin vecinos del futuro, búsqueda exacta, un vecino por episodio, regla sin solapes, DTW contra una versión de referencia |

**Datos:** los `.npy` de la v3 (`v3_research/tmp/data2022`, `v3_research/tmp/new20`, `v3_research`). Otra ubicación:
variable de entorno `ANALOGOS_DATA_DIRS` con las carpetas separadas por `;` (cada una con `klines/` y `futures/`).

**Tiempo aproximado** (4 núcleos): S1 unos 10 min, S2 unos 30 min, S3 unos 16 min, S4 menos de 2 min, S5 unos 8 min.

**Salidas:** `output/sN_rejilla.csv` (todas las combinaciones, diseño y validación) y `output/sN_resumen.json`
(la mejor combinación elegida solo con diseño y si pasa el criterio en validación).
