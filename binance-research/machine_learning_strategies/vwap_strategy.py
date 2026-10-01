import pandas as pd

class VWAPReversionStrategy:
    def __init__(self, window=48, std_dev_multiplier=2.0):
        self.window = window
        self.std_dev_multiplier = std_dev_multiplier
        self.history = {} 

    def evaluate(self, symbol: str, current_price: float, current_volume: float = 1.0) -> dict:
        if symbol not in self.history:
            self.history[symbol] = []
            
        # Guardamos tanto el precio como el volumen
        self.history[symbol].append({'price': current_price, 'volume': current_volume})
        
        if len(self.history[symbol]) > self.window:
            self.history[symbol].pop(0)
            
        data = self.history[symbol]
        
        if len(data) < self.window:
            return {"action": "HOLD"}

        # Cálculo del VWAP: Suma de (Precio * Volumen) / Suma del Volumen
        df = pd.DataFrame(data)
        df['pv'] = df['price'] * df['volume']
        
        cumulative_pv = df['pv'].sum()
        cumulative_volume = df['volume'].sum()
        
        # Evitar división por cero si el volumen es 0
        if cumulative_volume == 0:
            return {"action": "HOLD"}
            
        vwap = cumulative_pv / cumulative_volume
        
        # Calculamos la desviación estándar clásica de los precios para las bandas
        rolling_std = df['price'].std()
        lower_band = vwap - (rolling_std * self.std_dev_multiplier)

        # Si el precio cae por debajo de la banda inferior del VWAP, compramos el pánico
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
                "weight": 0.85 # Mayor peso que una media móvil simple
            }
            
        return {"action": "HOLD"}