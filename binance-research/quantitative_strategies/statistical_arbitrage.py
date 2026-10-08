import pandas as pd
import numpy as np

class StatisticalArbitrageStrategy:
    def __init__(self, asset_a="BTCUSDT", asset_b="ETHUSDT", window=96, z_score_threshold=2.0):
        # Definimos cuáles son las dos "patas" del arbitraje
        self.asset_a = asset_a
        self.asset_b = asset_b
        
        self.window = window
        self.z_score_threshold = z_score_threshold
        
        # Guardamos el último precio conocido de cada activo
        self.last_prices = {self.asset_a: None, self.asset_b: None}
        
        # Historial unificado del ratio (Spread)
        self.spread_history = []

    def evaluate(self, symbol: str, market_data) -> dict:
        # 1. Filtro: Si el símbolo no es parte del par de arbitraje, lo ignoramos
        if symbol not in [self.asset_a, self.asset_b]:
            return {"action": "HOLD"}

        # 2. Polimorfismo: extraemos el precio sin importar de dónde venga
        if isinstance(market_data, dict):
            current_price = float(market_data.get("close", 0.0))
        else:
            current_price = float(market_data)

        # 3. Actualizamos la memoria del último precio conocido
        self.last_prices[symbol] = current_price

        # 4. Si aún no tenemos datos de ambos activos, no podemos calcular el spread
        if self.last_prices[self.asset_a] is None or self.last_prices[self.asset_b] is None:
            return {"action": "HOLD"}

        # 5. Calculamos el Spread actual (Ej: Precio ETH / Precio BTC)
        current_spread = self.last_prices[self.asset_b] / self.last_prices[self.asset_a]
        self.spread_history.append(current_spread)
        
        if len(self.spread_history) > self.window:
            self.spread_history.pop(0)
            
        if len(self.spread_history) < self.window:
            return {"action": "HOLD"}

        series_spread = pd.Series(self.spread_history)
        mean_spread = series_spread.mean()
        std_spread = series_spread.std()
        
        # Prevenir división por cero
        if std_spread == 0:
            return {"action": "HOLD"}

        # Z-Score nos dice a cuántas desviaciones estándar está el spread actual de su media
        z_score = (current_spread - mean_spread) / std_spread

        # 6. Ejecución: Si el Z-Score es muy negativo, el Asset B (ETH) está muy barato respecto al Asset A (BTC)
        if z_score < -self.z_score_threshold:
            
            # Proyectamos un TP/SL genérico para el activo infravalorado
            target_price = self.last_prices[self.asset_b]
            risk_pct = 0.01 # Stop Loss del 1%
            
            sl = target_price * (1 - risk_pct)
            tp = target_price * (1 + (risk_pct * 2)) # Take Profit del 2% (2R)

            return {
                "action": "BUY",
                "target_symbol": self.asset_b, # Indicamos a Node.js explícitamente qué moneda comprar
                "entry_price": target_price,
                "take_profit": round(tp, 2),
                "stop_loss": round(sl, 2),
                "z_score": round(z_score, 2),
                "weight": 0.85 
            }
            
        return {"action": "HOLD"}