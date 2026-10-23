# Investigación de la estrategia v3 (copia versionada)

Copia del código, los modelos entrenados y los informes de la investigación de la [estrategia v3](../../doc/estrategia-v3-hacia-el-80.md). El original vive en `binance-research/data/research/`, que git ignora porque contiene ~2.9 GB de datos. Esta carpeta es una **copia**: los scripts originales siguen funcionando donde están, y lo que se cambie aquí no se refleja allí (ni al revés).

Copiado el 2026-10-23. Pesa ~7 MB; no hay ningún archivo de más de 10 MB.

## De dónde viene cada carpeta

| Carpeta | Origen | Contenido |
|---|---|---|
| `nn/` | `data/research/nn/*.py` | Redes y LightGBM de la fase NN: construcción de variables (`nn_build.py`), walk-forward (`nn_wf.py`), evaluación (`nn_eval.py`, `nn_v2_eval.py`), informes y la descarga de futuros (`nn_download_futures.py`). `nn_common.py` define las rutas. |
| `nn/models/`, `nn/models_v2/` | `data/research/nn/models*/` | Modelos entrenados: LightGBM (`.txt`), MLP y CNN de PyTorch (`.pt`) y sus escaladores (`_scaler.npz`). |
| `scripts/` | `data/research/scripts/*.py` y `HARNESS.md` | Arnés de evaluación (`harness.py`, documentado en `HARNESS.md`), análisis (`analista_*`), riesgo (`riesgo_*`), laboratorio (`be_*`, `be2*`), descargas (`download_klines.py`, `download_1s.py`) y réplica del bot (`bot_replica.py`). |
| `verificador/` | `data/research/verificador/*.py` | Solo el código de auditoría (`verify.py`, `audit_*`, `power*`, `probe_metrics*`). Sin `data*` ni `runs/`. |
| `output/constructor/` | ídem | Especificaciones (`spec_nn.json`, `spec_nn_v2.json`), informes de fases, `guia_nn.md` y los resultados walk-forward (`wf_results*.jsonl`). |
| `output/verificador/` | ídem | Auditorías, prerregistros (`preregistro_nn*.md`) y `ejecuciones_log.csv`. |
| `output/validador/` | ídem | `trials_log.csv` y `holdout_log.csv`: registro de todas las pruebas y de los usos de la reserva. |
| `output/riesgo/` | ídem | Solo `.md`, `.json` y `.csv` (rondas 1 a 3, fronteras de riesgo). |
| `output/bleeding_edge/`, `output/bleeding_edge_r2/` | ídem | Solo los informes `.md` (incluido `laboratorio_consolidado.md`). **Sin `preds/`** (~186 MB). |
| `output/analista/` | ídem | Solo `C1_spec_v2.json`. |
| `cache/deribit/` | `E:/tmp/r2_data/deribit/` | `dvol_BTC_1h.json` y `dvol_ETH_1h.json`: índice de volatilidad DVOL de Deribit, por hora. |

## Canal sombra de la v3 (`shadow/`)

Es la prueba **prospectiva** pre-registrada de la sección 8 de [estrategia-v3-hacia-el-80.md](../../doc/estrategia-v3-hacia-el-80.md). No opera ni envía órdenes: mide qué habría hecho la v3 desde el 2026-10-01.

| Archivo | Qué hace |
|---|---|
| `shadow/feeds.py` | Descargas incrementales: velas spot de 15 min y futuros (metrics, prima, velas y *funding*) de data.binance.vision para las 4 anclas, y el DVOL de Deribit (BTC y ETH) en `cache/deribit/`. Usa los parsers de `nn/nn_download_futures.py`. |
| `shadow/run_daily.py` | Verifica los *hashes* de `spec_nn_v2.json`, sus 13 modelos y los scripts, y evalúa con el ensamble congelado (mismo cálculo que `nn/nn_v3_desc.py`). Simula los brazos P1 (v2 + $A_4 \ge 1$ + X5 con 384 velas), C0 (sin compuerta) y S3 (P1 + veto D1 por DVOL), con costos de 0.24 %, 0.30 % y 0.19 %, y el azar por moneda y mes (también condicionado a $A_4 \ge 1$). |
| `shadow/test_run_daily.py` | Pruebas sin red con datos sintéticos, incluida una corrida completa con los modelos reales. |

Uso, desde `binance-research` y **con la VPN apagada** para las descargas:

```text
.venv\Scripts\python v3_research\shadow\run_daily.py --download
```

Sin `--download` solo recalcula con los datos que ya hay. La salida queda en `output/prospectivo/`: `resumen.md` (tabla de brazos y los 6 criterios de la sección 8.3 con lo que hay hasta hoy, más el e-proceso del WR y la futilidad), `resumen.json`, `senales.csv` (cada vela con $\hat p \ge \theta$, su $A_4$ y su $z_{30}$) y `operaciones_{P1,C0,S3}.csv`.

- **Retraso de los datos:** data.binance.vision publica al día siguiente, y el *funding* solo sale por mes. Cada corrida evalúa hasta el mínimo común de todas las series y recalcula desde el 2026-10-01. Las operaciones abiertas en ese corte no cuentan todavía.
- **Funding provisional:** mientras falta el archivo del mes en curso, `run_daily.py` reconstruye el *funding* con la fórmula de Binance a partir de la prima del perpetuo (que sí sale a diario): $F = P + \operatorname{clamp}(0.01\,\% - P,\ -0.05\,\%,\ 0.05\,\%)$, con $P$ la media ponderada de la prima de las 8 h previas. Antes de usarlo mide su equivalencia en el último mes con *funding* real (mismo modelo con el dato real y con el reconstruido: Jaccard de las señales y de P1, mínimo 0.8) y la guarda en `output/prospectivo/equivalencia_funding.json`; esa medición abre la reserva con motivo y queda en `holdout_log.csv`. El resumen sale marcado como **PROVISIONAL** hasta que se publique el archivo real. Con `--solo-definitivo` no se reconstruye nada.
- **Precalentamiento:** descarga desde 45 días antes del inicio (la especificación pide ≥ 35).
- **Fuera de este canal:** S1 (18 monedas), S2 (ENS12U, aún sin congelar) y S4 (opcional).
- **No cambiar** `nn/`, `models_v2/`, `scripts/harness.py` ni `spec_nn_v2.json`: los *hashes* forman parte del pre-registro y `run_daily.py` se detiene si no coinciden.

## Datos que faltan y cómo regenerarlos

Ninguno de estos datos está en git. Los scripts esperan encontrarlos **dentro de la carpeta de investigación** (la carpeta padre de `scripts/` y `nn/`), así que en una copia nueva hay que crearlos aquí, en `v3_research/`.

| Falta | Peso en el original | Lo usa | Cómo se regenera |
|---|---|---|---|
| `klines/` (`{SYM}_{tf}.npy`) | 287 MB | `harness.py`, `analista_common.py`, `be_common.py` | `python scripts/download_klines.py` (velas spot de data.binance.vision) |
| `futures/` (métricas, OI, *funding*, klines de futuros) | 133 MB | `nn/`, `be*` | `python nn/nn_download_futures.py --out <carpeta>/futures` |
| `tmp/` (cachés: `nn_cache*`, `be2_geom`, ...) | 1.7 GB | `nn_build.py`, `be2_common.py` | Se regenera solo al correr los scripts |
| `output/bleeding_edge/preds/` | ~186 MB | `be2_common.py` (`PD`) | Corriendo los `be_*.py` del laboratorio |
| `verificador/data*`, `verificador/runs/` | ~680 MB | `verificador/*.py` | `python verificador/download_reserved.py` y las corridas de `verify.py` |
| Velas de 1 s | — | `scripts/download_1s.py`, `live_lag.py` | `python scripts/download_1s.py` |
| Otros datos de R2 (Coinbase, Bitfinex) | — | ver rutas abajo | No hay script de descarga en esta copia |

Todas las descargas son de data.binance.vision (o Deribit, para el DVOL): con la VPN activa pueden fallar.

## Rutas absolutas que hay que ajustar

La mayoría de los scripts calcula sus rutas relativas a su propia ubicación (`HERE`/`RESEARCH` en `nn_common.py`, `be_common.py` y `analista_common.py`; `RESEARCH_DIR` en `harness.py`), así que funcionan desde `v3_research/` una vez estén los datos. Las excepciones:

| Archivo | Ruta | Qué hacer |
|---|---|---|
| `scripts/be2c_dvol.py` | `E:/tmp/r2_data/deribit/dvol_{BTC,ETH}_1h.json` | Apuntar a `cache/deribit/` |
| `scripts/be2c_dvol.py` | `E:/tmp/r2_data/coinbase_full/USDT-USD_15m.json`, `E:/tmp/r2_data/bitfinex/pos_long_1m_win.json` | Esos datos no se copiaron: hay que descargarlos de nuevo o saltar esas pruebas |
| `scripts/be_tabpfn.py` | `E:\tmp\be_pkgs` (paquetes aislados: `tabpfn` 2.2.1 y `scikit-learn` 1.6.1) y `HF_HOME = E:\hf-cache` | Instalar esos paquetes en otro entorno y ajustar las dos rutas. Importa `be_tabpfn_stub`, que vive en `E:\tmp\be_pkgs` y **no** está en esta copia |
| `nn/nn_download_futures.py` | `E:/.../data/research/futures` (solo en el ejemplo de uso) | Pasar `--out` con la ruta nueva |

## Dependencias de Python

Versiones del `.venv` de `binance-research` (`pip freeze`, 2026-10-23):

```text
numpy==2.4.6
pandas==3.0.6
scipy==1.17.1
scikit-learn==1.9.1
lightgbm==4.7.0
xgboost==3.2.0
torch==2.14.1+cpu
joblib==1.6.0
requests==2.34.2
```

Los scripts importan `numpy`, `pandas`, `scipy`, `sklearn`, `lightgbm` y `torch`; el resto es biblioteca estándar (`urllib`, `zipfile`, `concurrent`, ...). `tabpfn` solo lo usa `be_tabpfn.py`, desde su entorno aislado (ver arriba).
