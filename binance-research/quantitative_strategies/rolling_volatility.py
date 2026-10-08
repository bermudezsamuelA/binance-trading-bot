# quantitative_strategies/rolling_volatility.py
import pandas as pd

class RollingVolatilityStrategy:
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
            setattr(self, f"{symbol}_ready", False)
            
        self.price_history[symbol].append(current_price)
        
        if len(self.price_history[symbol]) > self.window:
            self.price_history[symbol].pop(0)
            
        prices = self.price_history[symbol]
        current_ticks = len(prices)
        
        # 1. Fase de calentamiento
        if current_ticks < self.window:
            if current_ticks % 10 == 0:
                print(f"[STRATEGY:{symbol}] Calentando motor... {current_ticks}/{self.window} registros.")
            return {"action": "HOLD"}

        # 2. Cálculo de volatilidad móvil
        series = pd.Series(prices)
        rolling_mean = series.mean()
        rolling_std = series.std()
        upper_band = rolling_mean + (rolling_std * self.std_dev_multiplier)

        # 3. Aviso de inicialización completada
        if not getattr(self, f"{symbol}_ready"):
            print(f"[STRATEGY:{symbol}] Buffer lleno. Monitoreando rupturas sobre {upper_band:.2f}")
            setattr(self, f"{symbol}_ready", True)
        
        # 4. Señal de ruptura alcista (Trend Following)
        if current_price > upper_band:
            sl = rolling_mean
            risk = current_price - sl
            tp = current_price + (risk * 2.0)
            
            setattr(self, f"{symbol}_ready", False)
            
            return {
                "action": "BUY",
                "entry_price": current_price,
                "take_profit": round(tp, 2),
                "stop_loss": round(sl, 2),
                "weight": 0.8
            }
            
        return {"action": "HOLD"}