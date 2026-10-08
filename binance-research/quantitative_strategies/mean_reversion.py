# quantitative_strategies/mean_reversion.py

import pandas as pd

class MeanReversionStrategy:
    def __init__(self, window=60, std_dev_multiplier=2.0):
        self.window = window
        self.std_dev_multiplier = std_dev_multiplier
        self.price_history = {} 

    def evaluate(self, symbol: str, market_data) -> dict:
        # Polimorfismo: compatible con dict (WebSocket/REST) y float (QuantCalculator)
        if isinstance(market_data, dict):
            current_price = float(market_data.get("close", 0.0))
        else:
            current_price = float(market_data)

        if symbol not in self.price_history:
            self.price_history[symbol] = []
            
        self.price_history[symbol].append(current_price)
        
        if len(self.price_history[symbol]) > self.window:
            self.price_history[symbol].pop(0)
            
        prices = self.price_history[symbol]
        
        if len(prices) < self.window:
            return {"action": "HOLD"}

        series = pd.Series(prices)
        rolling_mean = series.mean()
        rolling_std = series.std()
        lower_band = rolling_mean - (rolling_std * self.std_dev_multiplier)

        # Señal de reversión a la media (comprar sobreventa estadística)
        if current_price < lower_band:
            tp = rolling_mean
            risk = tp - current_price
            sl = current_price - risk
            
            # Filtro de seguridad ante spreads residuales o cálculo atípico
            if risk < (current_price * 0.005): 
                return {"action": "HOLD"}
                
            return {
                "action": "BUY",
                "entry_price": current_price,
                "take_profit": round(tp, 2),
                "stop_loss": round(sl, 2),
                "weight": 0.8
            }
            
        return {"action": "HOLD"}