import pandas as pd

class MeanReversionStrategy:
    def __init__(self, window=60, std_dev_multiplier=2.0):
        self.window = window
        self.std_dev_multiplier = std_dev_multiplier
        self.price_history = {} 

    def evaluate(self, symbol: str, current_price: float) -> dict:
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
        
        # Calculate the LOWER band this time
        lower_band = rolling_mean - (rolling_std * self.std_dev_multiplier)

        # The Mean Reversion Trigger: Price crashes below the lower band
        if current_price < lower_band:
            # Take Profit: Target a snap-back to the average price
            tp = rolling_mean
            
            # Risk Management: Set a stop loss equal to the target profit (1:1 Risk/Reward)
            risk = tp - current_price
            sl = current_price - risk
            
            # Prevent edge cases where math creates extremely tight stops
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