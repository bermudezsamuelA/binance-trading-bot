from quantitative_strategies.mean_reversion import MeanReversionStrategy
# from quantitative_strategies.vwap_strategy import VWAPReversionStrategy 

class StrategyEngine:
    def __init__(self):
        # NOTA: En el futuro esto leerá el ml_results.json para asignar hiperparámetros
        self.strategy = MeanReversionStrategy(window=2880, std_dev_multiplier=1.0)
        
    def get_signal(self, symbol: str, market_data: dict) -> dict:
        # Extraemos las variables específicas que la estrategia requiere.
        # Mean Reversion solo pide el precio actual por ahora.
        current_price = float(market_data.get('close', 0.0))
        
        # Si fuera VWAP, haríamos esto:
        # current_volume = float(market_data.get('volume', 0.0))
        # signal = self.strategy.evaluate(symbol, current_price, current_volume)
        
        signal = self.strategy.evaluate(symbol, current_price)
        
        if signal["action"] == "BUY":
            return {
                "symbol": symbol.upper(),
                "action": "BUY",
                "entry_price": signal["entry_price"],
                "take_profit": signal["take_profit"],
                "stop_loss": signal["stop_loss"]
            }
            
        return {"symbol": symbol.upper(), "action": "HOLD"}