import json
import os
import inspect
from quantitative_strategies.mean_reversion import MeanReversionStrategy
from quantitative_strategies.rolling_volatility import RollingVolatilityStrategy
from quantitative_strategies.vwap_strategy import VWAPReversionStrategy
from quantitative_strategies.volatility_squeeze import VolatilitySqueezeStrategy
from quantitative_strategies.capitulation import CapitulationStrategy
from config import BINANCE_MARKET, KLINE_INTERVAL_MS

# Modo OPCIONAL y desactivado por defecto: ALLOW_UNVALIDATED_STRATEGIES=1 en el .env carga, en las monedas sin
# estrategia validada, la de mejor PnL fuera de muestra aunque NO haya pasado la validacion (lo esperable es que
# pierda dinero). Solo para ver al bot operar en la testnet: con BINANCE_MARKET=mainnet se ignora.
ALLOW_UNVALIDATED = os.environ.get("ALLOW_UNVALIDATED_STRATEGIES", "").strip().lower() in ("1", "true", "yes", "si")

class StrategyEngine:
    def __init__(self):
        self.strategies = {}
        # open_time (ms) de la ultima vela cerrada procesada por simbolo: la precarga REST y el
        # WebSocket se solapan, y una vela repetida no debe entrar dos veces en la ventana.
        self.last_open_time = {}
        self.load_best_strategies()

    def max_window(self) -> int:
        """Ventana mas grande entre las estrategias cargadas (0 si no hay ninguna)."""
        return max((int(getattr(s, "window", 0)) for s in self.strategies.values()), default=0)

    def expected_next_open_time(self, symbol: str):
        """open_time de la siguiente vela que falta para que la ventana no tenga huecos (None si no hay historial)."""
        last = self.last_open_time.get(symbol)
        return None if last is None else last + KLINE_INTERVAL_MS

    def load_best_strategies(self):
        """Carga, por moneda, la estrategia VALIDADA por el walk-forward de ml_evaluator.py (campo "seleccionada"
        de ml_results.json) con los parametros de la ventana de entrenamiento mas reciente. Si una moneda no tiene
        estrategia validada, no opera y se explica por consola por que."""
        results_path = os.path.abspath(os.path.join(
            os.path.dirname(__file__), 
            "machine_learning_strategies", 
            "ml_results.json"
        ))
        
        strat_map = {
            "MeanReversion": MeanReversionStrategy,
            "TrendFollowing": RollingVolatilityStrategy,
            "VWAP": VWAPReversionStrategy,
            "VolatilitySqueeze": VolatilitySqueezeStrategy,
            "Capitulation": CapitulationStrategy
        }

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
        criteria = protocol.get("criterios", {})
        print(f"[ENGINE] Seleccion walk-forward del {protocol.get('generado')}: OOS {protocol.get('desarrollo', {}).get('primer_mes_prueba')}"
              f" a {protocol.get('desarrollo', {}).get('ultimo_mes_prueba')}, validacion final "
              f"{protocol.get('validacion_final', {}).get('desde')} a {protocol.get('validacion_final', {}).get('hasta')}, "
              f"alfa {criteria.get('alfa_bonferroni')} ({criteria.get('pares_probados')} pares).")

        experimental = ALLOW_UNVALIDATED and BINANCE_MARKET == "testnet"
        if ALLOW_UNVALIDATED and not experimental:
            print(f"[ENGINE] ⚠️ ALLOW_UNVALIDATED_STRATEGIES se ignora en {BINANCE_MARKET}: solo vale en la testnet.")

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
                name = max(candidates, key=lambda n: data[n].get("oos", {}).get("pnl", float("-inf")))
                tag = "NO VALIDADA, modo experimental ALLOW_UNVALIDATED_STRATEGIES"
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

            oos = params.get("oos") or {}
            hold = params.get("validacion_final") or {}
            aviso = " ⚠️ perdio en la validacion final" if hold.get("pnl", 0) < 0 else ""
            print(f"[ENGINE] 🧠 {symbol} -> Cargando {name} [{tag}] n={params['window']} k={params['multiplier']} | "
                  f"OOS: {oos.get('trades')} ops, WR {oos.get('win_rate')} %, PnL {oos.get('pnl')} USDT, p = {oos.get('p_valor')} | "
                  f"Validacion final: {hold.get('trades')} ops, PnL {hold.get('pnl')} USDT{aviso}")

        if not self.strategies:
            print("[ENGINE] ⏸️ Ninguna moneda tiene una estrategia validada: el bot no abrira operaciones. "
                  "Es un resultado valido de la validacion (ver ml_results.json y doc/matematica-del-bot.md, seccion 14).")

    def get_signal(self, symbol: str, market_data: dict) -> dict:
        if symbol not in self.strategies:
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
        strat = self.strategies[symbol]
        signal = strat.evaluate(symbol, {"close": float(market_data.get('close', 0.0)),
                                         "volume": float(market_data.get('volume', 0.0))})
            
        # Respetamos el formato de retorno exacto que Node.js espera
        if signal and signal.get("action") == "BUY":
            return {
                "symbol": symbol.upper(),
                "action": "BUY",
                "entry_price": signal.get("entry_price"),
                "take_profit": signal.get("take_profit"),
                "stop_loss": signal.get("stop_loss")
            }
            
        return {"symbol": symbol.upper(), "action": "HOLD"}