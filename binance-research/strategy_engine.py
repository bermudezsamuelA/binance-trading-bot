import datetime
import json
import os
import inspect
from quantitative_strategies.mean_reversion import MeanReversionStrategy
from quantitative_strategies.rolling_volatility import RollingVolatilityStrategy
from quantitative_strategies.vwap_strategy import VWAPReversionStrategy
from quantitative_strategies.volatility_squeeze import VolatilitySqueezeStrategy
from quantitative_strategies.capitulation import CapitulationStrategy
from config import (ACTIVE_ROSTER, BINANCE_MARKET, COSIGNAL_CANDLES, ENTRY_MIN_RISK_PCT, KLINE_INTERVAL,
                    KLINE_INTERVAL_MS, META_SHADOW, MOMENTUM_MONTHS)
from meta_filter import MetaFilter
from optimize import FEE_PER_SIDE, NOTIONAL_USDT, SLIPPAGE_PER_SIDE

# Modo OPCIONAL y desactivado por defecto: ALLOW_UNVALIDATED_STRATEGIES=1 en el .env carga, en las monedas sin
# estrategia validada, la de mejor PnL fuera de muestra aunque NO haya pasado la validacion (lo esperable es que
# pierda dinero). Solo para ver al bot operar en la testnet: con BINANCE_MARKET=mainnet se ignora.
ALLOW_UNVALIDATED = os.environ.get("ALLOW_UNVALIDATED_STRATEGIES", "").strip().lower() in ("1", "true", "yes", "si")
# Opcional, solo en la testnet: TESTNET_IGNORE_MOMENTUM=1 en el .env abre aunque el interruptor de momentum este
# apagado (el diario de senales lo anota), para juntar resultados reales de las senales. Con mainnet se ignora.
TESTNET_IGNORE_MOMENTUM = os.environ.get("TESTNET_IGNORE_MOMENTUM", "").strip().lower() in ("1", "true", "yes", "si")

# Mismos nombres que ml_results.json / fast_backtest.STRATEGY_CLASSES
STRATEGY_MAP = {
    "MeanReversion": MeanReversionStrategy,
    "TrendFollowing": RollingVolatilityStrategy,
    "VWAP": VWAPReversionStrategy,
    "VolatilitySqueeze": VolatilitySqueezeStrategy,
    "Capitulation": CapitulationStrategy
}


def shadow_oos(entry: dict, columns: list) -> tuple:
    """(operaciones, PnL) OOS de desarrollo SIN el interruptor de momentum: la suma de la sombra de cada pliegue. Es
    lo que hace el bot cuando el interruptor se ignora en la testnet."""
    if "pnl_sombra" not in columns:
        oos = entry.get("oos") or {}
        return oos.get("trades", 0), oos.get("pnl", float("-inf"))
    ops, pnl = columns.index("ops_sombra"), columns.index("pnl_sombra")
    rows = entry.get("pliegues") or []
    return sum(r[ops] for r in rows), sum(r[pnl] for r in rows)


def rule_copy(strategy):
    """Instancia NUEVA de la misma estrategia con los mismos parametros (sin historial de velas)."""
    params = {name: getattr(strategy, name) for name in inspect.signature(type(strategy).__init__).parameters
              if name != "self" and hasattr(strategy, name)}
    return type(strategy)(**params)


class StrategyEngine:
    def __init__(self):
        self.init_state(ignore_momentum=TESTNET_IGNORE_MOMENTUM and BINANCE_MARKET == "testnet")
        self.load_best_strategies()
        self.build_shadows()
        if META_SHADOW:
            self.meta = MetaFilter(KLINE_INTERVAL, KLINE_INTERVAL_MS, FEE_PER_SIDE + SLIPPAGE_PER_SIDE, NOTIONAL_USDT)
            print(f"[ENGINE] {self.meta.describe()}")

    def init_state(self, min_risk=ENTRY_MIN_RISK_PCT, cosignal=COSIGNAL_CANDLES, momentum=MOMENTUM_MONTHS,
                   roster=None, ignore_momentum=False):
        """Estado vacio y filtros de entrada (config.py; los mismos que valida walk_forward.py con strategy_filters.py).
        Las pruebas lo llaman con otros filtros sobre un motor creado sin leer ml_results.json. ignore_momentum: el
        interruptor apagado no bloquea (solo en la testnet, TESTNET_IGNORE_MOMENTUM)."""
        self.ignore_momentum = ignore_momentum
        self.strategies = {}
        # open_time (ms) de la ultima vela cerrada procesada por simbolo: la precarga REST y el
        # WebSocket se solapan, y una vela repetida no debe entrar dos veces en la ventana.
        self.last_open_time = {}
        self.min_risk, self.cosignal, self.momentum = min_risk, cosignal, momentum
        self.roster = list(roster or ACTIVE_ROSTER)
        self.momentum_on = {}      # simbolo -> interruptor de momentum (ml_results.json)
        self.shadows = {}          # simbolo X -> {otra moneda Y: instancia de la regla de X que ve las velas de Y}
        self.cosignal_hits = {}    # simbolo X -> open_time de los BUY de la regla de X en otras monedas
        self.journal_entry = None  # BUY de la ultima vela evaluada (abierto o bloqueado), para orders/signals.csv
        self.meta = None           # MetaFilter en sombra (META_SHADOW); None = apagado
        self.fold_rows = {}        # simbolo -> (filas de los pliegues de su estrategia en ml_results.json, columnas)

    def max_window(self) -> int:
        """Ventana mas grande entre las estrategias cargadas (0 si no hay ninguna)."""
        return max((int(getattr(s, "window", 0)) for s in self.strategies.values()), default=0)

    def expected_next_open_time(self, symbol: str):
        """open_time de la siguiente vela que falta para que la ventana no tenga huecos (None si no hay historial)."""
        last = self.last_open_time.get(symbol)
        return None if last is None else last + KLINE_INTERVAL_MS

    def build_shadows(self):
        """Co-senal: para cada moneda X con estrategia, una instancia de SU regla (mismos n y k) por cada otra moneda
        del roster, alimentada con las velas de esa moneda."""
        if not self.cosignal:
            return
        for symbol, strategy in self.strategies.items():
            self.shadows[symbol] = {other: rule_copy(strategy) for other in self.roster if other != symbol}
            self.cosignal_hits[symbol] = []

    def watchers(self, symbol: str) -> list:
        """Monedas cuya regla tiene una instancia en sombra sobre las velas de `symbol`."""
        return [x for x, shadows in self.shadows.items() if symbol in shadows]

    def load_best_strategies(self):
        """Carga, por moneda, la estrategia VALIDADA por el walk-forward de ml_evaluator.py (campo "seleccionada"
        de ml_results.json) con los parametros de la ventana de entrenamiento mas reciente. Si una moneda no tiene
        estrategia validada, no opera y se explica por consola por que."""
        results_path = os.path.abspath(os.path.join(
            os.path.dirname(__file__),
            "machine_learning_strategies",
            "ml_results.json"
        ))

        strat_map = STRATEGY_MAP

        try:
            with open(results_path, 'r', encoding='utf-8') as f:
                results = json.load(f)
        except Exception as e:
            print(f"[ENGINE] ⚠️ Error cargando ml_results.json: {e}. No se carga ninguna estrategia.")
            return

        protocol = results.get("_protocolo")
        if not isinstance(protocol, dict):
            print("[ENGINE] ⚠️ ml_results.json no tiene la validacion walk-forward (formato viejo): no se carga ninguna "
                  "estrategia. Ejecuta: python machine_learning_strategies/ml_evaluator.py")
            return
        candle = (protocol.get("datos") or {}).get("vela")
        if candle != KLINE_INTERVAL:
            print(f"[ENGINE] ⚠️ ml_results.json es de velas de {candle} y el bot usa {KLINE_INTERVAL} (config.py): no se "
                  f"carga ninguna estrategia. Ejecuta: python machine_learning_strategies/ml_evaluator.py")
            return
        criteria = protocol.get("criterios", {})
        print(f"[ENGINE] Seleccion walk-forward del {protocol.get('generado')}: OOS {protocol.get('desarrollo', {}).get('primer_mes_prueba')}"
              f" a {protocol.get('desarrollo', {}).get('ultimo_mes_prueba')}, validacion final "
              f"{protocol.get('validacion_final', {}).get('desde')} a {protocol.get('validacion_final', {}).get('hasta')}, "
              f"alfa {criteria.get('alfa_bonferroni')} ({criteria.get('pares_probados')} pares).")
        print(f"[ENGINE] Filtros de entrada: riesgo minimo {self.min_risk}, co-senal {self.cosignal} velas, "
              f"momentum {self.momentum} meses (ml_results.json: {protocol.get('filtros')}).")

        experimental = ALLOW_UNVALIDATED and BINANCE_MARKET == "testnet"
        if ALLOW_UNVALIDATED and not experimental:
            print(f"[ENGINE] ⚠️ ALLOW_UNVALIDATED_STRATEGIES se ignora en {BINANCE_MARKET}: solo vale en la testnet.")
        if TESTNET_IGNORE_MOMENTUM and BINANCE_MARKET != "testnet":
            print(f"[ENGINE] ⚠️ TESTNET_IGNORE_MOMENTUM se ignora en {BINANCE_MARKET}: el interruptor de momentum se respeta.")
        elif self.ignore_momentum:
            print("[ENGINE] 🧪 TESTNET_IGNORE_MOMENTUM: el interruptor de momentum no bloquea (el diario de senales lo anota).")
        columns = protocol.get("pliegues_columnas") or []

        for symbol, data in results.items():
            if symbol.startswith("_") or not isinstance(data, dict):
                continue
            name = data.get("seleccionada")
            tag = "validada"
            # Solo estrategias validadas; ademas, una que pierde en la validacion final nunca se carga en modo normal
            # (ml_evaluator.py ya la marca rechazada; se comprueba otra vez por si el JSON viene de otra version).
            if not (name in strat_map and isinstance(data.get(name), dict) and data[name].get("status") == "validada"
                    and (data[name].get("validacion_final") or {}).get("pnl", 0) >= 0):
                reason = data.get('motivo', 'sin estrategia validada')
                if name in strat_map and isinstance(data.get(name), dict) and data[name].get("status") == "validada":
                    reason = f"{name} esta validada, pero pierde en la validacion final ({data[name]['validacion_final'].get('pnl')} USDT)"
                print(f"[ENGINE] ⏸️ {symbol} no opera: {reason}")
                for strat_name in strat_map:
                    if isinstance(data.get(strat_name), dict):
                        print(f"[ENGINE]      · {strat_name}: {data[strat_name].get('status')} ({data[strat_name].get('motivo')})")
                if not experimental:
                    continue
                # Modo experimental: la de mejor PnL OOS entre las que tienen parametros rentables en la ventana mas reciente
                candidates = [n for n in strat_map if isinstance(data.get(n), dict)
                              and data[n].get("entrenamiento_vivo", {}).get("operar") and data[n].get("window")]
                if not candidates:
                    print(f"[ENGINE]      Modo experimental: {symbol} tampoco tiene parametros rentables en la ventana mas reciente.")
                    continue
                tag = "NO VALIDADA, modo experimental ALLOW_UNVALIDATED_STRATEGIES"
                if self.ignore_momentum:
                    # Con el interruptor ignorado, el bot hace lo que la sombra: se elige por el PnL OOS sin interruptor
                    # (y con operaciones, para no cargar una que nunca opero)
                    shadow = {n: shadow_oos(data[n], columns) for n in candidates}
                    candidates = [n for n in candidates if shadow[n][0] > 0] or candidates
                    name = max(candidates, key=lambda n: shadow[n][1])
                    tag += f"; elegida por su PnL OOS sin interruptor ({shadow[name][0]} ops, {shadow[name][1]:+.2f} USDT)"
                else:
                    name = max(candidates, key=lambda n: data[n].get("oos", {}).get("pnl", float("-inf")))
                if data[name].get("pasa_walk_forward"):
                    tag += "; pasa el walk-forward pero no la validacion final"

            params = data[name]
            if not params.get("window") or params.get("multiplier") is None:
                print(f"[ENGINE] ⏸️ {symbol} no opera: {name} no tiene parametros para vivo.")
                continue
            strat_class = strat_map[name]
            sig = inspect.signature(strat_class.__init__)
            valid_kwargs = {}
            if 'window' in sig.parameters:
                valid_kwargs['window'] = int(params['window'])
            # Mapeo exacto a tu variable original
            if 'std_dev_multiplier' in sig.parameters:
                valid_kwargs['std_dev_multiplier'] = float(params['multiplier'])
            elif 'multiplier' in sig.parameters:
                valid_kwargs['multiplier'] = float(params['multiplier'])
            self.strategies[symbol] = strat_class(**valid_kwargs)
            self.fold_rows[symbol] = ((params.get("pliegues") or []) + (params.get("pliegues_validacion") or []), columns)

            # Interruptor de momentum: lo calcula ml_evaluator.py; sin ese dato (JSON viejo) la moneda no abre
            momentum = params.get("momentum")
            self.momentum_on[symbol] = bool(momentum and momentum.get("encendido"))
            switch = ""
            if self.momentum:
                off = "APAGADO (ignorado en testnet: abre igual)" if self.ignore_momentum else "APAGADO (no abre)"
                switch = (f" | Momentum {'ENCENDIDO' if self.momentum_on[symbol] else off}"
                          + (f", PnL en sombra {momentum.get('meses')} meses {momentum.get('pnl_sombra')} USDT"
                             if momentum else ", sin dato en ml_results.json"))

            oos = params.get("oos") or {}
            hold = params.get("validacion_final") or {}
            aviso = " ⚠️ perdio en la validacion final" if hold.get("pnl", 0) < 0 else ""
            print(f"[ENGINE] 🧠 {symbol} -> Cargando {name} [{tag}] n={params['window']} k={params['multiplier']} | "
                  f"OOS: {oos.get('trades')} ops, WR {oos.get('win_rate')} %, PnL {oos.get('pnl')} USDT, p = {oos.get('p_valor')} | "
                  f"Validacion final: {hold.get('trades')} ops, PnL {hold.get('pnl')} USDT{aviso}{switch}")

        if not self.strategies:
            print("[ENGINE] ⏸️ Ninguna moneda tiene una estrategia validada: el bot no abrira operaciones. "
                  "Es un resultado valido de la validacion (ver ml_results.json y doc/matematica-del-bot.md, seccion 14).")

    def filter_checks(self, symbol: str, buy: dict, open_time) -> list:
        """(motivo, bloquea) de cada filtro de entrada que este BUY no cumple (vacio = se abre). Los mismos de
        strategy_filters.py; el momentum apagado no bloquea si se ignora en la testnet (queda anotado)."""
        checks = []
        if self.momentum and not self.momentum_on.get(symbol, False):
            checks.append(("momentum apagado, ignorado en testnet", False) if self.ignore_momentum
                          else (f"momentum apagado ({self.momentum} meses en sombra <= 0)", True))
        entry, stop = float(buy["entry_price"]), float(buy["stop_loss"])
        if self.min_risk is not None and entry - stop < entry * self.min_risk:
            checks.append((f"riesgo {(entry - stop) / entry:.2%} < {self.min_risk:.1%}", True))
        if self.cosignal:
            if open_time is None:
                checks.append(("sin open_time para la co-senal", True))
            else:
                lo, hi = open_time - self.cosignal * KLINE_INTERVAL_MS, open_time - KLINE_INTERVAL_MS
                hits = self.cosignal_hits[symbol] = [h for h in self.cosignal_hits.get(symbol, []) if h >= lo]
                if not any(lo <= h <= hi for h in hits):
                    checks.append((f"sin co-senal en las {self.cosignal} velas previas", True))
        return checks

    def meta_records(self) -> list:
        """Pasa al filtro en sombra el BUY de la ultima vela evaluada (si hubo) y devuelve los registros ya juzgados
        (cada uno espera la vela de BTC de su mismo open_time). Solo para las velas del WebSocket, como el diario."""
        if self.meta is None or not self.meta.enabled:
            return []
        if self.journal_entry:
            rows, columns = self.fold_rows.get(self.journal_entry["symbol"], ([], []))
            self.meta.on_buy(self.journal_entry, rows, columns)
        return self.meta.pop_ready()

    def get_signal(self, symbol: str, market_data: dict, own: bool = True, shadow_for=None) -> dict:
        """Procesa una vela cerrada de `symbol`: alimenta las instancias en sombra de la co-senal que miran esta moneda
        y, si tiene estrategia, la evalua y aplica los filtros de entrada. own / shadow_for: la precarga
        (server.pre_seed_engine) da a cada instancia solo sus velas (None = todas las que miran esta moneda)."""
        self.journal_entry = None
        if self.meta is not None:
            self.meta.add_candle(symbol, market_data)
        watchers = self.watchers(symbol)
        if symbol not in self.strategies and not watchers:
            return None

        # Deduplicacion por open_time: se ignora toda vela con open_time <= la ultima procesada.
        open_time = market_data.get('open_time')
        if open_time is not None:
            open_time = int(open_time)
            last = self.last_open_time.get(symbol)
            if last is not None and open_time <= last:
                return {"symbol": symbol.upper(), "action": "HOLD"}
            if last is not None and open_time > last + KLINE_INTERVAL_MS:
                faltan = (open_time - last) // KLINE_INTERVAL_MS - 1
                print(f"[ENGINE] ⚠️ {symbol}: faltan {faltan} vela(s) entre {last} y {open_time}.")
            self.last_open_time[symbol] = open_time

        # Todas las estrategias aceptan la vela completa (dict); VWAP y Capitulation leen de ahi el volumen.
        # Igual que optimize.simulate_live, para que vivo y backtest den las mismas senales.
        candle = {"close": float(market_data.get('close', 0.0)), "volume": float(market_data.get('volume', 0.0))}
        for watcher in watchers:
            if shadow_for is None or watcher in shadow_for:
                shadow_signal = self.shadows[watcher][symbol].evaluate(symbol, candle)
                if open_time is not None and shadow_signal and shadow_signal.get("action") == "BUY":
                    self.cosignal_hits[watcher].append(open_time)

        if symbol not in self.strategies or not own:
            return None
        strat = self.strategies[symbol]
        signal = strat.evaluate(symbol, candle)
        if not (signal and signal.get("action") == "BUY"):
            return {"symbol": symbol.upper(), "action": "HOLD"}

        # Respetamos el formato de retorno exacto que Node.js espera
        buy = {
            "symbol": symbol.upper(),
            "action": "BUY",
            "entry_price": signal.get("entry_price"),
            "take_profit": signal.get("take_profit"),
            "stop_loss": signal.get("stop_loss")
        }
        checks = self.filter_checks(symbol, buy, open_time)
        reasons = [text for text, blocks in checks if blocks]
        name = next((n for n, c in STRATEGY_MAP.items() if type(strat) is c), type(strat).__name__)
        entry, stop = float(buy["entry_price"]), float(buy["stop_loss"])
        self.journal_entry = {
            "logged_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "symbol": symbol.upper(), "open_time": open_time, "strategy": name, "window": getattr(strat, "window", None),
            "multiplier": getattr(strat, "std_dev_multiplier", None), "entry_price": entry,
            "take_profit": float(buy["take_profit"]), "stop_loss": stop, "risk_pct": round(100 * (entry - stop) / entry, 4),
            "decision": "bloqueada" if reasons else "BUY", "reason": "; ".join(text for text, _ in checks),
            "momentum_on": self.momentum_on.get(symbol) if self.momentum else None, "market": BINANCE_MARKET}
        if reasons:
            return {"symbol": symbol.upper(), "action": "HOLD", "bloqueada": "; ".join(reasons)}
        return buy
