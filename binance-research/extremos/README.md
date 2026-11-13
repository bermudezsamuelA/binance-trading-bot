# Estrategia de extremos (video de YouTube)

Backtest de la estrategia "extremo diario → cambio de estructura en 1 h → gatillo en 5 min" con datos reales de Binance
spot. Proyecto aparte: no usa ni modifica las estrategias del bot. Explicación y resultados:
[`doc/estrategia-extremos.md`](../../doc/estrategia-extremos.md).

| Archivo | Qué hace |
|---|---|
| `descargar_5m.py` | Descarga velas de 5 min del archivo público de Binance (`data.binance.vision`, sin API key) y las guarda como `.npy` |
| `estrategia.py` | Las reglas: condiciones diarias, estructura y Fibonacci en 1 h, gatillo, stop y objetivo. Simulación vela a vela |
| `backtest.py` | Corre la rejilla de parámetros, separa diseño y validación, y escribe los resultados en `output/` |
| `test_estrategia.py` | Pruebas: agregación de velas, pivotes, EMA y que ninguna decisión use velas futuras |

## Cómo correrlo en local

Desde la carpeta del proyecto, con el `.venv` activado (necesita `numpy` y `scipy`, que ya están en el proyecto):

```
cd binance-research/extremos
python descargar_5m.py
python -m unittest test_estrategia
python backtest.py
python backtest.py --walk-forward
```

- `descargar_5m.py` baja unos 450 MB de ZIP y deja unos 640 MB de `.npy` en `v3_research/tmp/k5m/`. Para guardarlo en el
  disco E: `python descargar_5m.py --salida E:/datos/k5m` y luego `set EXTREMOS_DATA_DIRS=E:/datos/k5m` antes del
  backtest. Si la descarga falla con la VPN activa, desactívala solo para este paso.
- `backtest.py` tarda unos minutos. Opciones: `--rapido` (solo la configuración del video), `--monedas BTCUSDT ETHUSDT`,
  `--tf 15m` (usa las velas de 15 min de la v3 en vez de las de 5 min).

## Salidas (`output/`)

- `resumen_5m.json`: configuración del video y mejor combinación elegida en diseño, con sus resultados en diseño y
  validación, el embudo (cuántas señales se pierden en cada paso) y las referencias.
- `rejilla_5m.csv`: todas las combinaciones.
- `resumen_wf_5m.json`, `wf_operaciones_*_5m.csv`: walk-forward (combinación elegida por bloque, resultados fuera de muestra y
  operaciones).
- `operaciones_video_5m.csv`, `operaciones_mejor_5m.csv`: cada operación con entrada, salida, stop, objetivo y resultado.
