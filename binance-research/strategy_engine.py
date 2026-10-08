import json
import os
import inspect
from quantitative_strategies.mean_reversion import MeanReversionStrategy
from quantitative_strategies.rolling_volatility import RollingVolatilityStrategy
from quantitative_strategies.vwap_strategy import VWAPReversionStrategy
from quantitative_strategies.volatility_squeeze import VolatilitySqueezeStrategy

class StrategyEngine:
    def __init__(self):
        self.strategies = {}
        self.load_best_strategies()

    def load_best_strategies(self):
        results_path = os.path.abspath(os.path.join(
            os.path.dirname(__file__), 
            "machine_learning_strategies", 
            "ml_results.json"
        ))
        
        strat_map = {
            "MeanReversion": MeanReversionStrategy,
            "TrendFollowing": RollingVolatilityStrategy,
            "VWAP": VWAPReversionStrategy,
            "VolatilitySqueeze": VolatilitySqueezeStrategy
        }
        
        try:
            with open(results_path, 'r') as f:
                results = json.load(f)
                
            for symbol, data in results.items():
                if not data or "error" in data:
                    continue
                    
                best_strat_name = None
                best_pnl = -float('inf')
                best_params = {}
                
                for name, metrics in data.items():
                    if name in strat_map and isinstance(metrics, dict) and "pnl" in metrics:
                        if metrics["pnl"] > best_pnl:
                            best_pnl = metrics["pnl"]
                            best_strat_name = name
                            best_params = metrics
                            
                if best_strat_name:
                    print(f"[ENGINE] 🧠 {symbol} -> Cargando {best_strat_name} | Hist PnL: ${best_pnl}")
                    
                    strat_class = strat_map[best_strat_name]
                    sig = inspect.signature(strat_class.__init__)
                    valid_kwargs = {}
                    
                    if 'window' in sig.parameters and 'window' in best_params:
                        valid_kwargs['window'] = best_params['window']
                    
                    # Mapeo exacto a tu variable original
                    if 'std_dev_multiplier' in sig.parameters and 'multiplier' in best_params:
                        valid_kwargs['std_dev_multiplier'] = best_params['multiplier']
                    elif 'multiplier' in sig.parameters and 'multiplier' in best_params:
                        valid_kwargs['multiplier'] = best_params['multiplier']
                    
                    self.strategies[symbol] = strat_class(**valid_kwargs)
                    
        except Exception as e:
            print(f"[ENGINE] ⚠️ Error cargando ml_results.json: {e}")

    def get_signal(self, symbol: str, market_data: dict) -> dict:
        if symbol not in self.strategies:
            return None
            
        current_price = float(market_data.get('close', 0.0))
        current_volume = float(market_data.get('volume', 0.0))
        strat = self.strategies[symbol]
        
        # Inspeccionamos si tu método evaluate pide el volumen (como en VWAP) o solo el precio
        sig = inspect.signature(strat.evaluate)
        
        if 'current_volume' in sig.parameters or 'volume' in sig.parameters:
            signal = strat.evaluate(symbol, current_price, current_volume)
        else:
            signal = strat.evaluate(symbol, current_price)
            
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