import pandas as pd
import numpy as np

class RegimeClassifier:
    def __init__(self):
        # Aquí luego cargaremos el modelo pre-entrenado (ej: xgboost.Booster)
        self.model = None
        self.is_trained = False

    def extract_features(self, prices: list, volumes: list) -> pd.DataFrame:
        """
        Transforma los datos crudos en indicadores técnicos (Features) para el ML.
        Aquí calcularemos RSI, ADX, y Volatilidad Relativa.
        """
        # TODO: Implementar Feature Engineering
        pass

    def predict_regime(self, current_price: float, history: list) -> int:
        """
        Retorna 0 si es Mercado Lateral (Seguro para Mean Reversion)
        Retorna 1 si es Tendencia Fuerte (Veto a Mean Reversion, Seguro para Trend Following)
        """
        # Lógica temporal mockeada hasta que entrenemos el modelo
        # Si no hay modelo, asume que es seguro operar (0)
        if not self.is_trained:
            return 0 
            
        return 0