import pandas as pd

class RollingVolatilityStrategy:
    def __init__(self, window=60, std_dev_multiplier=2.0):
        self.window = window
        self.std_dev_multiplier = std_dev_multiplier
        self.price_history = {} 

    def evaluate(self, symbol: str, current_price: float) -> dict:
        if symbol not in self.price_history:
            self.price_history[symbol] = []
            # Use a flag to track if we've announced readiness
            setattr(self, f"{symbol}_ready", False)
            
        self.price_history[symbol].append(current_price)
        
        if len(self.price_history[symbol]) > self.window:
            self.price_history[symbol].pop(0)
            
        prices = self.price_history[symbol]
        current_ticks = len(prices)
        
        # 1. Warm-up Phase
        if current_ticks < self.window:
            # Print a status update every 10 ticks so it doesn't spam the terminal
            if current_ticks % 10 == 0:
                print(f"[{symbol}] Warming up engine... {current_ticks}/{self.window} ticks collected.")
            return {"action": "HOLD"}

        # 2. Calculate Rolling Volatility
        series = pd.Series(prices)
        rolling_mean = series.mean()
        rolling_std = series.std()
        upper_band = rolling_mean + (rolling_std * self.std_dev_multiplier)

        # 3. Readiness Announcement (Only prints once per coin)
        if not getattr(self, f"{symbol}_ready"):
            print(f" [{symbol}] Window full! Actively scanning for momentum breakouts above {upper_band:.2f}")
            setattr(self, f"{symbol}_ready", True)
        
        # 4. The Trend-Following Trigger
        if current_price > upper_band:
            sl = rolling_mean
            risk = current_price - sl
            tp = current_price + (risk * 2.0)
            
            # Reset readiness so it announces again if it re-enters the scanning phase later
            setattr(self, f"{symbol}_ready", False)
            
            return {
                "action": "BUY",
                "entry_price": current_price,
                "take_profit": round(tp, 2),
                "stop_loss": round(sl, 2),
                "weight": 0.8  
            }
            
        return {"action": "HOLD"}