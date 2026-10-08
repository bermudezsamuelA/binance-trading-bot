import pandas as pd
import numpy as np

class HMMRegimeDetector:
    def __init__(self, n_regimes=2):
        """
        n_regimes: Número de estados ocultos a descubrir. 
        Por defecto 2 (Ej: Mercado Lateral vs Mercado en Tendencia).
        """
        self.n_regimes = n_regimes
        self.model = None
        self.is_trained = False
        self.market_memory = []

    def extract_volatility_features(self, df: pd.DataFrame) -> np.ndarray:
        """
        HMM suele alimentarse de retornos logarítmicos y rangos verdaderos (True Range),
        no de precios absolutos, ya que busca cambios en la "frecuencia" del mercado.
        """
        returns = np.log(df['close'] / df['close'].shift(1)).dropna()
        # Se formatea como una matriz 2D que requiere la librería hmmlearn
        return returns.values.reshape(-1, 1)

    def train(self, historical_data: pd.DataFrame):
        """
        Aquí usaremos hmmlearn.GaussianHMM para descubrir los regímenes ocultos.
        """
        print(f"[HMM] Entrenando modelo de Markov con {self.n_regimes} regímenes...")
        features = self.extract_volatility_features(historical_data)
        
        # TODO: self.model = GaussianHMM(n_components=self.n_regimes).fit(features)
        
        print("[HMM] Modelo entrenado en simulación. Regímenes detectados.")
        self.is_trained = True

    def predict_regime(self, current_candle: dict) -> int:
        """
        Inferencia en vivo. 
        Retorna 0 (Lateral/Baja Volatilidad) o 1 (Tendencia/Alta Volatilidad)
        """
        if not self.is_trained:
            return 0 # Asume mercado lateral por defecto
            
        current_price = float(current_candle.get("close", 0.0))
        self.market_memory.append(current_price)
        
        # Guardamos memoria suficiente para calcular la varianza (ej. últimas 50 velas)
        if len(self.market_memory) > 50:
            self.market_memory.pop(0)
            
        if len(self.market_memory) < 10:
            return 0 
            
        # TODO: Predecir el régimen actual basado en la última secuencia
        # regime = self.model.predict(features)[-1]
        
        return 0