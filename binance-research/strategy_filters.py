# strategy_filters.py
"""
Filtros de entrada del bot en el backtest (walk_forward.py). strategy_engine.py aplica los mismos en vivo y
test_filters.py comprueba que den las mismas senales. Se configuran en config.py (None desactiva cada uno).

- Riesgo minimo (ENTRY_MIN_RISK_PCT): se descarta el BUY si entrada - SL < riesgo minimo * entrada. La senal
  descartada no bloquea: la vela siguiente puede abrir.
- Co-senal (COSIGNAL_CANDLES = W): el BUY de la moneda X en la vela t solo se toma si la MISMA regla de X (misma
  estrategia, mismos n y k) aplicada a otra moneda del roster dio BUY en una vela con open_time entre t - W y t - 1
  (en velas). La vela actual no cuenta: en vivo cada moneda llega por separado y la de otra puede no haber llegado.
  Las instancias de la regla en las otras monedas empiezan a la vez que la de X (misma precarga), como en vivo.
- Momentum (MOMENTUM_MONTHS = M): un mes solo se opera si el PnL en sombra de los M meses anteriores es > 0
  (momentum_gate). En sombra = lo que habria dado el walk-forward aunque ese mes no se operara.
"""
import numpy as np
import pandas as pd


class FilteredFS:
    """FastSymbol con el riesgo minimo y la co-senal aplicados en cada simulate. walk_forward.PairEvaluator lo usa
    igual que a FastSymbol, asi elige los parametros y prueba los meses con las mismas reglas que el bot."""

    def __init__(self, fs, open_time: np.ndarray, others: list, candle_ms: int, min_risk: float = None,
                 cosignal: int = None):
        """others: lista de (FastSymbol, open_time) de las demas monedas del roster."""
        self.fs, self.open_time, self.others = fs, open_time, others
        self.candle_ms, self.min_risk, self.cosignal = candle_ms, min_risk, cosignal
        self._masks = {}

    def cosignal_mask(self, strategy: str, w: int, m: float, first: int = 0) -> np.ndarray:
        """Velas de esta moneda con co-senal, para una instancia que empieza en `first` (y las de las otras monedas,
        en la misma fecha)."""
        key = (strategy, w, m, first)
        if key not in self._masks:
            t_first = self.open_time[first]
            times = [oot[ofs.buy_indices(strategy, w, m, int(np.searchsorted(oot, t_first)))]
                     for ofs, oot in self.others]
            hits = np.sort(np.concatenate(times)) if times else np.zeros(0, np.int64)
            lo = np.searchsorted(hits, self.open_time - self.cosignal * self.candle_ms, side="left")
            hi = np.searchsorted(hits, self.open_time - self.candle_ms, side="right")
            self._masks[key] = hi > lo
        return self._masks[key]

    def simulate(self, strategy: str, w: int, m: float, first: int = 0, **kw):
        mask = self.cosignal_mask(strategy, w, m, first) if self.cosignal else None
        return self.fs.simulate(strategy, w, m, first=first, min_risk=self.min_risk, entry_mask=mask, **kw)


def momentum_gate(rows: list, prior: list, months: int) -> list:
    """Interruptor de cada pliegue (mes de prueba): encendido si el PnL en sombra de los `months` meses anteriores es
    > 0. prior = sombra de los meses previos (los de desarrollo, para la validacion final). Sin historia, apagado."""
    shadow, on = list(prior), []
    for r in rows:
        on.append(bool(shadow) and sum(shadow[-months:]) > 0)
        shadow.append(r["pnl"])
    return on


def gate_trades(rows: list, entries: np.ndarray, exits: np.ndarray, pnl: np.ndarray, open_time: np.ndarray,
                on: list) -> tuple:
    """Deja solo las operaciones de los meses encendidos. Cada fila guarda su sombra (ops_sombra, pnl_sombra) y
    ops/pnl pasan a ser lo operado (0 si el mes estaba apagado). Aproximacion: el encadenamiento de una posicion por
    moneda sale de la sombra (una operacion de un mes apagado pudo retrasar la primera del mes siguiente)."""
    on_months = [r["prueba"] for r, o in zip(rows, on) if o]
    month = np.asarray(pd.to_datetime(open_time[entries], unit="ms", utc=True).strftime("%Y-%m"))
    keep = np.isin(month, on_months) if len(entries) else np.zeros(0, bool)
    gated = []
    for r, o in zip(rows, on):
        g = {**r, "ops_sombra": r["ops"], "pnl_sombra": r["pnl"], "encendido": o}
        if not o:
            g["ops"], g["pnl"] = 0, 0.0
        gated.append(g)
    return gated, entries[keep], exits[keep], pnl[keep]
