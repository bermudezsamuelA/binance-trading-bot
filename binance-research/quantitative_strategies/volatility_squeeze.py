import pandas as pd

class VolatilitySqueezeStrategy:
    def __init__(self, window=20, std_dev_multiplier=2.0, squeeze_threshold=0.05):
        self.window = window
        self.std_dev_multiplier = std_dev_multiplier
        self.squeeze_threshold = squeeze_threshold
        self.price_history = {}

    def evaluate(self, symbol: str, market_data) -> dict:
        # Polimorfismo para aceptar Node.js (dict) o QuantCalculator (float)
        if isinstance(market_data, dict):
            current_price = float(market_data.get("close", 0.0))
        else:
            current_price = float(market_data)

        if symbol not in self.price_history:
            self.price_history[symbol] = []
            setattr(self, f"{symbol}_armed", False)

        self.price_history[symbol].append(current_price)

        if len(self.price_history[symbol]) > self.window:
            self.price_history[symbol].pop(0)

        prices = self.price_history[symbol]

        if len(prices) < self.window:
            return {"action": "HOLD"}

        series = pd.Series(prices)
        rolling_mean = series.mean()
        rolling_std = series.std()

        upper_band = rolling_mean + (rolling_std * self.std_dev_multiplier)
        lower_band = rolling_mean - (rolling_std * self.std_dev_multiplier)

        # Calcular el ancho de las bandas (volatilidad relativa)
        band_width = (upper_band - lower_band) / rolling_mean

        # Detectar el "Squeeze" (compresión extrema de volatilidad)
        is_squeezed = band_width < self.squeeze_threshold

        # Si el mercado se durmió, armamos la trampa
        if is_squeezed and not getattr(self, f"{symbol}_armed"):
            setattr(self, f"{symbol}_armed", True)
            
        # Si la trampa está armada y el precio rompe la banda superior violentamente
        elif getattr(self, f"{symbol}_armed") and current_price > upper_band:
            setattr(self, f"{symbol}_armed", False) # Reseteamos la trampa

            sl = rolling_mean
            risk = current_price - sl
            tp = current_price + (risk * 2.5) # Ratio 2.5R porque las explosiones son grandes

            if risk < (current_price * 0.005):
                return {"action": "HOLD"}

            return {
                "action": "BUY",
                "entry_price": current_price,
                "take_profit": round(tp, 2),
                "stop_loss": round(sl, 2),
                "weight": 0.9 # Señal muy fuerte
            }

        return {"action": "HOLD"}