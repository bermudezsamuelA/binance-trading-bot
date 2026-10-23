# Verificador: fase 1 (2026-10-14, 06:07 VST)

**1. Datos reservados (bajo mi custodia).**
- Velas spot de 15 m de XRP, BNB, ADA, LINK, AVAX y LTC, del 2023-01 al 2026-09, en `research/verificador/data/` (131 419 velas por moneda).
- Solo falta un tramo: la caída de Binance del 2023-03-24 (5 velas). No hay errores de OHLC.
- Los SHA256 están en `manifest.json`.
- También descargué los `metrics` de futuros de esas monedas para la fase 2.
- No he calculado ningún rendimiento y no he compartido nada.

**2. Qué significa `create_time` en `metrics`** (detalle en `regla_metrics.md`).
Lo comprobé comparando el taker ratio con las velas de futuros de 5 m y el precio implícito OI_value/OI con las velas de 1 m:
- **Hasta el 2024-03-03:** T es el *final* del intervalo de 5 m. El taker ratio cubre [T−5, T) y el OI está tomado en T.
- **Desde el 2024-03-04:** T es el *inicio*. El taker ratio cubre [T, T+5) y el OI está tomado en T+5.
- El cambio ocurre el mismo día en BTC y en las 6 monedas reservadas.

**Regla:** cada registro se conoce en τ = T + 5 min. Para decidir al cierre de la vela que abre en t_i solo vale **T ≤ t_i + 10 min**; en vivo recomiendo T ≤ t_i + 5 min.
- Un `merge_asof` sobre el cierre, o un `resample` con `closed='right'`, mete el registro T = t_i + 15. Ese registro son los primeros 5 minutos de la operación, así que es una **fuga**.
- Huecos en BTC: 0 días faltantes; faltan 133 de 394 272 intervalos de 5 m (la racha más larga es de 10.4 h); hay 168 celdas vacías en los ratios long/short.
- 143 archivos traen las filas desordenadas: hay que ordenarlas.
- Los huecos se rellenan hacia adelante con un máximo de 30 min y un indicador de dato faltante.

**3. `verify.py`** (solo usa numpy y scipy; no depende del arnés).
- **Entrada:** CSV con `symbol, entry_t, exit_t, entry_px, exit_px, tp, sl, H, entry_mode` (compatible con `Trades.to_csv`).
- **Réplica:** vuelve a simular cada salida con reglas pesimistas.
- **Métricas:** n, WR con Wilson (y con n efectivo según el DEFF diario), b efectivo, E neta en % y en R (también con costos de 0.30 %), PF, MDD, t i.i.d. y t agrupado por día (CR1).
- **Control aleatorio emparejado:** misma moneda, mismo mes y misma geometría, con 200 repeticiones. Da ΔWR y ΔE con p pareado por día y p por repeticiones.
- **DSR:** con N = 12 268 + las del Constructor.
- **Veredicto automático:** según los criterios del pre-registro.
- **`--final`:** permite una sola ejecución por prueba y la anota con hashes en `ejecuciones_log.csv`.

**Validación.**
- **Autoprueba en un paseo aleatorio:** con TP +0.5 % y SL −2.5 % da WR 0.82 (límite inferior de Wilson 0.79), pero E −0.28 % y ΔWR ≈ 0, así que RECHAZA. Es el WR "fabricado por la geometría".
- **Oráculo con fuga:** da ΔWR +0.18 y el control lo detecta.
- **Contraste con el arnés** (BTC y ETH en diseño, 6 640 operaciones): n, WR, E, PF y b_eff coinciden exactamente, sin ninguna discrepancia en la réplica.

**4. Pre-registro** (`preregistro_nn.md`; congela el SHA256 de verify.py).
Una sola candidata congelada. La prueba primaria son las 6 monedas reservadas de 2025-07 a 2026-09; la secundaria, las 4 originales (solo como apoyo). Se exige:
- (a) E > 0 con t por día > 1.645, y E > 0 con costos de 0.30 %;
- (b) límite inferior de Wilson ≥ 0.70;
- (c) ΔE frente al azar > 0 con p < 0.05 en las dos pruebas;
- (d) auditoría sin fugas.

**Muestra necesaria.**
- **Para (b):**

  | WR observado | Operaciones (n) | n con potencia del 80 % |
  |---|---|---|
  | 0.75 | 324 | 625 |
  | 0.72 | 2 025 | — |
  | 0.80 | 85 | — |

- **Para (a), con WR 0.75 y DEFF 1.5:** la red tiene que superar al azar de su propia geometría por ≥ 10 puntos con R ≥ 4 % (467 operaciones con 0.24 % de costo, 662 con 0.30 %) o por ≥ 15 puntos con R ≈ 2 % (286 / 483). Con 5 puntos y R ≤ 2 %, E ≤ 0. El equipo anterior midió ventajas de −1.5 a +6 puntos.

**¿Alcanza el periodo primario?** Son 457 días × 6 monedas.
- A la frecuencia de C1 (~30 operaciones por moneda y año) salen **≈ 225 operaciones: no alcanza para (b)** salvo que el WR sea ≥ 0.78.
- Hacen falta ≥ 43 operaciones por moneda y año para llegar a 324, y ≈ 83 para llegar a 625.

**5. Lo que necesito del Constructor para la fase 2.**
- Pesos y código congelados, con su hash.
- Las *features* y sus fuentes.
- Umbral, TP, SL y H.
- La frecuencia esperada en el OOS de diseño.
- Las configuraciones registradas.
- Un script que genere las señales a partir de un `.npy` cualquiera.
