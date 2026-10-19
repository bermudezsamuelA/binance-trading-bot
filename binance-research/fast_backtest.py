# fast_backtest.py
"""
Version rapida (numpy) de optimize.simulate_live para las cuatro estrategias de quantitative_strategies/.

Da EXACTAMENTE las mismas operaciones que simulate_live con las clases reales (mismas velas de entrada y
salida, mismos precios y mismo PnL hasta el ultimo bit):
- La media y la desviacion de cada ventana se calculan con el mismo orden de sumas que pandas
  (Series.mean / Series.std: suma por pares de numpy sobre cada ventana, varianza en dos pasadas).
- Las comparaciones, el filtro de riesgo minimo y el round() de TP/SL son los mismos que en cada evaluate().
- Las reglas de entrada y salida son las de simulate_live (entrada al cierre, TP/SL desde la vela siguiente,
  hueco = apertura, empate = SL, no reabrir en la vela de salida, posicion abierta al final = descartada).

Como la estrategia ve todas las velas (tambien con posicion abierta), sus senales no dependen de las
operaciones: se calculan de una vez para toda la serie y despues se recorre solo de operacion en operacion.

Modo tramo (simulate con first/start/entry_end/stop): una instancia NUEVA de la estrategia recibe velas desde
`first` (precarga, como pre_seed_engine: sus senales se ignoran), solo abre en [start, entry_end), empieza sin
posicion y sigue las operaciones abiertas hasta su salida real, sin pasar de `stop`. Es lo que vive el bot al
arrancar con parametros nuevos. Su referencia es simulate_live sobre ese mismo tramo con la clase real
(simulate_reference con segment=...).

Si una version nueva de pandas o numpy cambiara el orden de las sumas, la paridad se romperia: por eso
ml_evaluator.py ejecuta check_parity() antes de usarla y aborta si no hay paridad exacta.
Prueba completa: python fast_backtest.py
"""
import contextlib
import glob
import io
import os
import sys
import time

import numpy as np
import pandas as pd

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from optimize import NOTIONAL_USDT, FEE_PER_SIDE, SLIPPAGE_PER_SIDE, simulate_live
from quantitative_strategies.mean_reversion import MeanReversionStrategy
from quantitative_strategies.rolling_volatility import RollingVolatilityStrategy
from quantitative_strategies.vwap_strategy import VWAPReversionStrategy
from quantitative_strategies.volatility_squeeze import VolatilitySqueezeStrategy

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "spot")
CANDLE_MS = 15 * 60 * 1000

# Mismos nombres que ml_results.json / strategy_engine.py
STRATEGY_CLASSES = {
    "MeanReversion": MeanReversionStrategy,
    "TrendFollowing": RollingVolatilityStrategy,
    "VWAP": VWAPReversionStrategy,
    "VolatilitySqueeze": VolatilitySqueezeStrategy,
}

# Constantes copiadas de evaluate() de cada estrategia (la prueba de paridad avisa si cambian)
MIN_RISK_PCT = 0.005          # MeanReversion, VWAP y VolatilitySqueeze: riesgo minimo 0.5 % del precio
TF_REWARD = 2.0               # RollingVolatility: TP = entrada + 2R
SQUEEZE_REWARD = 2.5          # VolatilitySqueeze: TP = entrada + 2.5R
SQUEEZE_THRESHOLD = VolatilitySqueezeStrategy().squeeze_threshold
ROWS_PER_BLOCK = 8192         # filas por bloque al calcular ventanas (acota la memoria)


def load_history(symbol: str, data_dir: str = DATA_DIR, end_date: str = None) -> pd.DataFrame:
    """Todas las velas de 15 min descargadas (meses completos + dias sueltos del mes en curso), en orden.
    open_time en ms (Binance paso a microsegundos en 2025). Opcional: solo hasta end_date (YYYY-MM-DD, incluido)."""
    files = sorted(glob.glob(os.path.join(data_dir, "monthly", "klines", symbol, "15m", f"{symbol}-15m-*.csv")))
    files += sorted(glob.glob(os.path.join(data_dir, "daily", "klines", symbol, "15m", f"{symbol}-15m-*.csv")))
    if not files:
        raise FileNotFoundError(f"No hay velas de 15m de {symbol} en {data_dir}")
    cols = ["open_time", "open", "high", "low", "close", "volume"]
    frames = []
    for f in files:
        d = pd.read_csv(f, header=None, usecols=range(6))
        if not str(d.iloc[0, 0]).strip().isdigit():
            d = d.iloc[1:]
        d.columns = cols
        frames.append(d)
    df = pd.concat(frames, ignore_index=True)
    t = df["open_time"].astype(np.int64).to_numpy()
    df["open_time"] = np.where(t > 10**14, t // 1000, t)
    for col in cols[1:]:
        df[col] = df[col].astype(float)
    df = df.drop_duplicates("open_time").sort_values("open_time").reset_index(drop=True)
    if end_date is not None:
        limit = int(pd.Timestamp(end_date, tz="UTC").value // 10**6) + 86_400_000
        df = df[df["open_time"] < limit].reset_index(drop=True)
    return df


def _window_sums(x: np.ndarray, w: int, with_var: bool):
    """Suma (y suma de cuadrados respecto de la media) de cada ventana de w valores que termina en i.
    Cada fila contigua se reduce con np.sum(axis=1): el mismo orden por pares que Series.sum de pandas."""
    n = len(x)
    total = np.full(n, np.nan)
    sq = np.full(n, np.nan) if with_var else None
    if n < w:
        return total, sq
    view = np.lib.stride_tricks.sliding_window_view(x, w)
    count = np.float64(w)
    for start in range(0, len(view), ROWS_PER_BLOCK):
        block = np.ascontiguousarray(view[start:start + ROWS_PER_BLOCK])
        s = block.sum(axis=1)
        total[start + w - 1:start + w - 1 + len(s)] = s
        if with_var:
            # nanops.nanvar: avg = suma / n; sum((avg - x) ** 2)
            avg = s / count
            sq[start + w - 1:start + w - 1 + len(s)] = ((avg[:, None] - block) ** 2).sum(axis=1)
    return total, sq


class FastSymbol:
    """Velas de una moneda y las estadisticas de cada ventana (se calculan una vez y se reutilizan)."""

    def __init__(self, candles: pd.DataFrame):
        self.o = candles["open"].to_numpy(float)
        self.h = candles["high"].to_numpy(float)
        self.l = candles["low"].to_numpy(float)
        self.c = candles["close"].to_numpy(float)
        self.v = candles["volume"].to_numpy(float)
        self.n = len(self.c)
        self._stats = {}
        self._vwap = {}

    def stats(self, w: int):
        """(media, desviacion muestral) de los ultimos w cierres; NaN mientras la ventana no esta llena."""
        if w not in self._stats:
            count = np.float64(w)
            s, sq = _window_sums(self.c, w, with_var=True)
            mean = s / count
            # ddof = 1, como Series.std(); np.sqrt de la varianza, como nanops.nanstd
            std = np.sqrt(sq / (count - np.float64(1)))
            self._stats[w] = (mean, std)
        return self._stats[w]

    def vwap(self, w: int):
        """(VWAP, volumen de la ventana) como VWAPReversionStrategy: sum(precio*volumen) / sum(volumen)."""
        if w not in self._vwap:
            pv_sum, _ = _window_sums(self.c * self.v, w, with_var=False)
            vol_sum, _ = _window_sums(self.v, w, with_var=False)
            with np.errstate(divide="ignore", invalid="ignore"):
                vwap = pv_sum / vol_sum
            self._vwap[w] = (vwap, vol_sum)
        return self._vwap[w]

    # --- Senales: indices de las velas en las que evaluate() devuelve BUY ---
    def buy_indices(self, strategy: str, w: int, m: float, first: int = 0, end: int = None) -> np.ndarray:
        """Velas con BUY para una instancia que recibe velas desde `first` (0 = toda la serie), hasta `end`.
        Su ventana se llena en first + w - 1; desde ahi la media y la desviacion son las de la serie completa."""
        c = self.c
        end = self.n if end is None else end
        valid_from = first + w - 1
        mean, std = self.stats(w)
        cut = lambda idx: idx[np.searchsorted(idx, valid_from):np.searchsorted(idx, end)]
        with np.errstate(invalid="ignore"):
            if strategy == "MeanReversion":
                lower = mean - (std * m)
                risk = mean - c
                buy = (c < lower) & ~(risk < c * MIN_RISK_PCT)
                return cut(np.flatnonzero(buy))
            if strategy == "TrendFollowing":
                upper = mean + (std * m)
                return cut(np.flatnonzero(c > upper))
            if strategy == "VWAP":
                vwap, vol_sum = self.vwap(w)
                lower = vwap - (std * m)
                risk = vwap - c
                buy = (vol_sum != 0) & (c < lower) & ~(risk < c * MIN_RISK_PCT)
                return cut(np.flatnonzero(buy))
            if strategy == "VolatilitySqueeze":
                upper = mean + (std * m)
                lower = mean - (std * m)
                band_width = (upper - lower) / mean
                squeezed = cut(np.flatnonzero(band_width < SQUEEZE_THRESHOLD))
                breakout = cut(np.flatnonzero(c > upper))
                # Maquina de estados de la trampa (empieza desarmada en `first`): se arma en una vela comprimida
                # (sin evaluar ruptura en esa vela) y se dispara en la primera ruptura posterior; despues hace
                # falta otra compresion en una vela posterior a la ruptura.
                events = []
                last = valid_from - 1
                while True:
                    a = np.searchsorted(squeezed, last, side="right")
                    if a >= len(squeezed):
                        break
                    b = np.searchsorted(breakout, squeezed[a], side="right")
                    if b >= len(breakout):
                        break
                    last = int(breakout[b])
                    events.append(last)
                events = np.asarray(events, dtype=np.int64)
                if len(events) == 0:
                    return events
                risk = c[events] - mean[events]
                return events[~(risk < c[events] * MIN_RISK_PCT)]
        raise ValueError(f"Estrategia desconocida: {strategy}")

    def entry_levels(self, strategy: str, w: int, i: int):
        """(entrada, TP, SL) de la senal en la vela i, con las mismas operaciones escalares que evaluate()."""
        current_price = float(self.c[i])
        if strategy == "VWAP":
            center = self.vwap(w)[0][i]
        else:
            center = self.stats(w)[0][i]
        if strategy in ("MeanReversion", "VWAP"):
            tp = center
            risk = tp - current_price
            sl = current_price - risk
        else:
            sl = center
            risk = current_price - sl
            tp = current_price + (risk * (TF_REWARD if strategy == "TrendFollowing" else SQUEEZE_REWARD))
        return current_price, float(round(tp, 8)), float(round(sl, 8))

    # --- Simulacion: igual que optimize.simulate_live ---
    def _first_exit(self, start: int, tp: float, sl: float, stop: int):
        o, h, l = self.o, self.h, self.l
        size = 64
        while start < stop:
            end = min(stop, start + size)
            hit = (o[start:end] <= sl) | (o[start:end] >= tp) | (l[start:end] <= sl) | (h[start:end] >= tp)
            if hit.any():
                return start + int(np.argmax(hit))
            start = end
            size *= 4
        return None

    def simulate(self, strategy: str, w: int, m: float, detail: bool = False,
                 first: int = 0, start: int = 0, entry_end: int = None, stop: int = None):
        """Operaciones de la estrategia. Devuelve (entrada_idx, salida_idx, pnl) como arreglos, o la lista de dicts
        de simulate_live si detail=True. Por defecto, toda la serie; con first/start/entry_end/stop, el modo tramo
        (instancia nueva precargada desde first, sin posicion, entradas en [start, entry_end), salidas antes de stop)."""
        cost = FEE_PER_SIDE + SLIPPAGE_PER_SIDE
        stop = self.n if stop is None else stop
        entry_end = stop if entry_end is None else min(entry_end, stop)
        buys = self.buy_indices(strategy, w, m, first, entry_end)
        o = self.o
        entries, exits, pnls, rows = [], [], [], []
        k = 0
        allowed = start  # primera vela en la que se puede abrir (no se reabre en la vela de salida)
        while True:
            k = np.searchsorted(buys, allowed, side="left")
            if k >= len(buys):
                break
            i = int(buys[k])
            entry_price, tp, sl = self.entry_levels(strategy, w, i)
            j = self._first_exit(i + 1, tp, sl, stop)
            if j is None:
                break  # sigue abierta al final de los datos (o en stop): simulate_live no la cuenta
            if o[j] <= sl:
                exit_price, reason = o[j], "SL"
            elif o[j] >= tp:
                exit_price, reason = o[j], "TP"
            elif self.l[j] <= sl:
                exit_price, reason = sl, "SL"
            else:
                exit_price, reason = tp, "TP"
            qty = NOTIONAL_USDT / entry_price
            gross = qty * (exit_price - entry_price)
            fees = qty * (entry_price + exit_price) * cost
            pnl = gross - fees
            entries.append(i)
            exits.append(j)
            pnls.append(pnl)
            if detail:
                rows.append({"entry_index": i, "exit_index": j, "entry_price": entry_price,
                             "exit_price": exit_price, "reason": reason, "pnl": pnl})
            allowed = j + 1
        if detail:
            return rows
        return (np.asarray(entries, dtype=np.int64), np.asarray(exits, dtype=np.int64),
                np.asarray(pnls, dtype=np.float64))


class _SignalWindow:
    """Envuelve la estrategia real: la evalua en TODAS las velas (su estado evoluciona igual), pero solo deja
    pasar sus senales en [start, end). Antes es la precarga (pre_seed_engine ignora las senales); despues el
    bot ya no abre operaciones nuevas, aunque sigue vigilando la que este abierta."""

    def __init__(self, strategy, start: int, end: int):
        self.strategy, self.start, self.end, self.i = strategy, start, end, 0

    def evaluate(self, symbol, market_data):
        signal = self.strategy.evaluate(symbol, market_data)
        i, self.i = self.i, self.i + 1
        return signal if self.start <= i < self.end else {"action": "HOLD"}


def simulate_reference(symbol: str, candles: pd.DataFrame, strategy: str, w: int, m: float, segment=None) -> list:
    """simulate_live con la clase real (la de produccion), sin los mensajes de calentamiento. Con
    segment=(first, start, entry_end, stop): simulate_live sobre las velas [first, stop) con una instancia nueva,
    abriendo solo en [start, entry_end). Los indices se devuelven en la numeracion de la serie completa."""
    real = STRATEGY_CLASSES[strategy](window=int(w), std_dev_multiplier=float(m))
    with contextlib.redirect_stdout(io.StringIO()):
        if segment is None:
            return simulate_live(symbol, candles, real)
        first, start, entry_end, stop = segment
        part = candles.iloc[first:stop].reset_index(drop=True)
        trades = simulate_live(symbol, part, _SignalWindow(real, start - first, entry_end - first))
    for t in trades:
        t["entry_index"] += first
        t["exit_index"] += first
    return trades


def compare_trades(ref: list, fast: list) -> dict:
    """Jaccard de las operaciones (entrada, salida) y diferencia exacta de precios y PnL."""
    a = {(t["entry_index"], t["exit_index"]) for t in ref}
    b = {(t["entry_index"], t["exit_index"]) for t in fast}
    union = a | b
    jaccard = 1.0 if not union else len(a & b) / len(union)
    identical = len(ref) == len(fast) and all(
        r["entry_index"] == f["entry_index"] and r["exit_index"] == f["exit_index"]
        and r["entry_price"] == f["entry_price"] and r["exit_price"] == f["exit_price"]
        and r["reason"] == f["reason"] and r["pnl"] == f["pnl"] for r, f in zip(ref, fast))
    return {"jaccard": jaccard, "identical": identical, "trades_ref": len(ref), "trades_fast": len(fast),
            "pnl_ref": float(sum(t["pnl"] for t in ref)), "pnl_fast": float(sum(t["pnl"] for t in fast))}


def check_stats_bitwise(candles: pd.DataFrame, windows, samples: int = 400, seed: int = 0) -> int:
    """Compara bit a bit la media/desviacion/VWAP rapidas con pandas en posiciones al azar. Devuelve fallos."""
    fs = FastSymbol(candles)
    rng = np.random.default_rng(seed)
    c, v = fs.c, fs.v
    fails = 0
    for w in windows:
        mean, std = fs.stats(w)
        vwap, _ = fs.vwap(w)
        for i in rng.integers(w - 1, fs.n, size=samples):
            prices = [float(x) for x in c[i - w + 1:i + 1]]
            s = pd.Series(prices)
            df = pd.DataFrame([{"price": p, "volume": float(x)} for p, x in zip(prices, v[i - w + 1:i + 1])])
            df["pv"] = df["price"] * df["volume"]
            ref_vwap = df["pv"].sum() / df["volume"].sum()
            if not (s.mean() == mean[i] and s.std() == std[i] and df["price"].std() == std[i]
                    and (ref_vwap == vwap[i] or (np.isnan(ref_vwap) and np.isnan(vwap[i])))):
                fails += 1
    return fails


def check_parity(cases, verbose: bool = True) -> bool:
    """cases: lista de (symbol, candles, strategy, window, multiplier[, (first, start, entry_end, stop)]).
    True solo si todas son identicas."""
    ok = True
    fast_cache = {}
    for case in cases:
        symbol, candles, strategy, w, m = case[:5]
        segment = case[5] if len(case) > 5 else None
        key = (symbol, id(candles))
        if key not in fast_cache:
            fast_cache[key] = FastSymbol(candles)
        t0 = time.perf_counter()
        ref = simulate_reference(symbol, candles, strategy, w, m, segment)
        t1 = time.perf_counter()
        if segment is None:
            fast = fast_cache[key].simulate(strategy, w, m, detail=True)
        else:
            first, start, entry_end, stop = segment
            fast = fast_cache[key].simulate(strategy, w, m, detail=True, first=first, start=start,
                                            entry_end=entry_end, stop=stop)
        t2 = time.perf_counter()
        res = compare_trades(ref, fast)
        ok &= res["identical"] and res["jaccard"] == 1.0
        if verbose:
            where = f"velas={len(candles):>6}" if segment is None else f"tramo={segment}"
            print(f"  {symbol:<8} {strategy:<17} n={w:>2} k={m:<4} {where} "
                  f"ops={res['trades_ref']:>4}/{res['trades_fast']:<4} Jaccard={res['jaccard']:.3f} "
                  f"PnL={res['pnl_ref']:+.6f}/{res['pnl_fast']:+.6f} identicas={res['identical']} "
                  f"({t1 - t0:.2f} s vs {t2 - t1:.3f} s)")
    return ok


if __name__ == "__main__":
    # Prueba de paridad completa: 4 monedas x 4 estrategias, parametros extremos y al azar, sobre tramos de
    # 1 y 3 meses, en modo tramo (instancia nueva precargada, sin posicion heredada) y sobre la historia completa.
    sys.stdout.reconfigure(encoding="utf-8")
    rng = np.random.default_rng(20261019)
    windows = list(range(8, 100, 4))
    mults = [round(0.8 + 0.2 * i, 2) for i in range(13)]
    all_ok = True
    for symbol in ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT"]:
        hist = load_history(symbol)
        t = pd.to_datetime(hist["open_time"], unit="ms", utc=True)
        month = hist[(t >= "2026-09-01") & (t < "2026-10-01")].reset_index(drop=True)
        quarter = hist[(t >= "2024-02-01") & (t < "2024-05-01")].reset_index(drop=True)
        fails = check_stats_bitwise(month, windows, samples=60)
        print(f"{symbol}: media/desviacion/VWAP bit a bit vs pandas -> {fails} fallos")
        all_ok &= fails == 0
        cases = []
        for strategy in STRATEGY_CLASSES:
            params = [(8, 0.8), (96, 3.2)] + [(int(rng.choice(windows)), float(rng.choice(mults))) for _ in range(2)]
            for w, m in params:
                cases.append((symbol, month, strategy, w, m))
            w, m = int(rng.choice(windows)), float(rng.choice(mults))
            cases.append((symbol, quarter, strategy, w, m))
        all_ok &= check_parity(cases)
        # Modo tramo: instancia nueva precargada con max(n + 20, 100) velas (como pre_seed_engine), entradas
        # durante un mes y salidas hasta 2 meses despues; el inicio cae en un mes al azar o en una vela al azar.
        cases = []
        for strategy in STRATEGY_CLASSES:
            for k in range(3):
                w, m = int(rng.choice(windows)), float(rng.choice(mults))
                if k < 2:
                    month0 = pd.Timestamp("2023-02-01", tz="UTC") + pd.DateOffset(months=int(rng.integers(0, 42)))
                    start = int(np.searchsorted(hist["open_time"].to_numpy(), month0.value // 10**6))
                else:
                    start = int(rng.integers(200, len(hist) - 9000))
                first = start - max(w + 20, 100)
                cases.append((symbol, hist, strategy, w, m, (first, start, start + 2976, min(len(hist), start + 3 * 2976))))
        all_ok &= check_parity(cases)
    # Historia completa (2023-01 -> ultimo dia descargado) en dos casos con muchas operaciones
    hist = load_history("SOLUSDT")
    all_ok &= check_parity([("SOLUSDT", hist, "TrendFollowing", 8, 0.8), ("SOLUSDT", hist, "VolatilitySqueeze", 20, 1.4)])
    print("PARIDAD EXACTA" if all_ok else "SIN PARIDAD: no usar la version rapida")
    sys.exit(0 if all_ok else 1)
