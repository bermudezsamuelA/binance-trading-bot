# quantitative_strategies/vwap_strategy.py
import pandas as pd

class VWAPReversionStrategy:
    def __init__(self, window=48, std_dev_multiplier=2.0):
        self.window = window
        self.std_dev_multiplier = std_dev_multiplier
        self.history = {} 

    def evaluate(self, symbol: str, market_data) -> dict:
        if isinstance(market_data, dict):
            current_price = float(market_data.get("close", 0.0))
            current_volume = float(market_data.get("volume", 1.0))
        else:
            current_price = float(market_data)
            current_volume = 1.0

        if symbol not in self.history:
            self.history[symbol] = []
            
        self.history[symbol].append({"price": current_price, "volume": current_volume})
        
        if len(self.history[symbol]) > self.window:
            self.history[symbol].pop(0)
            
        data = self.history[symbol]
        
        if len(data) < self.window:
            return {"action": "HOLD"}

        df = pd.DataFrame(data)
        df["pv"] = df["price"] * df["volume"]
        
        cumulative_pv = df["pv"].sum()
        cumulative_volume = df["volume"].sum()
        
        if cumulative_volume == 0:
            return {"action": "HOLD"}
            
        vwap = cumulative_pv / cumulative_volume
        rolling_std = df["price"].std()
        lower_band = vwap - (rolling_std * self.std_dev_multiplier)

        if current_price < lower_band:
            tp = vwap
            risk = tp - current_price
            sl = current_price - risk
            
            if risk < (current_price * 0.005): 
                return {"action": "HOLD"}
                
            return {
                "action": "BUY",
                "entry_price": current_price,
                "take_profit": round(tp, 2),
                "stop_loss": round(sl, 2),
                "weight": 0.85
            }
            
        return {"action": "HOLD"}