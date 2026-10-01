import pandas as pd
import numpy as np

class StatisticalArbitrageStrategy:
    def __init__(self, window=96, z_score_threshold=2.0):
        self.window = window
        self.z_score_threshold = z_score_threshold
        # Guardamos el historial de ambos activos
        self.history_asset_A = [] # Ej: BTC
        self.history_asset_B = [] # Ej: ETH

    def evaluate(self, price_A: float, price_B: float) -> dict:
        self.history_asset_A.append(price_A)
        self.history_asset_B.append(price_B)
        
        if len(self.history_asset_A) > self.window:
            self.history_asset_A.pop(0)
            self.history_asset_B.pop(0)
            
        if len(self.history_asset_A) < self.window:
            return {"action": "HOLD"}

        series_A = pd.Series(self.history_asset_A)
        series_B = pd.Series(self.history_asset_B)
        
        # Calculamos el ratio de precio (Spread)
        spread = series_B / series_A
        
        mean_spread = spread.mean()
        std_spread = spread.std()
        
        current_spread = spread.iloc[-1]
        
        # Z-Score nos dice a cuántas desviaciones estándar está el spread actual de su media
        z_score = (current_spread - mean_spread) / std_spread

        # Si el Z-Score es muy negativo, ETH está muy barato en relación a BTC
        if z_score < -self.z_score_threshold:
            return {
                "action": "ARBITRAGE_BUY_B", # Señal de comprar ETH (y teóricamente hacer short en BTC)
                "z_score": round(z_score, 2),
                "target_spread": mean_spread
            }
            
        return {"action": "HOLD"}