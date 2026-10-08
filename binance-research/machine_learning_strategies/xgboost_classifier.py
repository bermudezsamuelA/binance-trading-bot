import pandas as pd
import numpy as np
import xgboost as xgb
from sklearn.metrics import accuracy_score

class XGBoostClassifier:
    def __init__(self):
        # Hiperparámetros de un árbol de decisión institucional
        self.model = xgb.XGBClassifier(
            n_estimators=100,        # Número de árboles
            max_depth=4,             # Profundidad (no muy alto para evitar memorizar)
            learning_rate=0.05,      # Velocidad de aprendizaje
            random_state=42,
            eval_metric='logloss'
        )
        self.is_trained = False
        self.market_memory = pd.DataFrame()

    def extract_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calcula indicadores reales (RSI, Medias, Volatilidad) para que XGBoost tenga 
        las 'pistas' necesarias para tomar decisiones.
        """
        features = pd.DataFrame(index=df.index)
        
        features['return'] = df['close'].pct_change()
        features['volatility_10'] = features['return'].rolling(window=10).std()
        features['volatility_20'] = features['return'].rolling(window=20).std()
        
        sma_20 = df['close'].rolling(window=20).mean()
        features['dist_sma_20'] = (df['close'] - sma_20) / sma_20
        
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(window=14).mean()
        loss = -delta.where(delta < 0, 0).rolling(window=14).mean()
        rs = gain / (loss + 1e-9)
        features['rsi_14'] = 100 - (100 / (1 + rs))
        
        if 'volume' in df.columns:
            features['vol_change'] = df['volume'].pct_change()
            
        return features.dropna()

    def train(self, historical_data: pd.DataFrame, target_labels: pd.Series):
        print("[XGBOOST] Extrayendo variables técnicas (Feature Engineering)...")
        X = self.extract_features(historical_data)
        
        # Alinear los datos (eliminar los NaN iniciales del RSI y Volatilidad)
        valid_indices = X.index.intersection(target_labels.index)
        X = X.loc[valid_indices]
        y = target_labels.loc[valid_indices]

        # Dividimos los datos: 80% para estudiar, 20% para el examen final
        split_idx = int(len(X) * 0.8)
        X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
        y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]

        print(f"[XGBOOST] Entrenando modelo con {len(X_train)} muestras históricas...")
        self.model.fit(X_train, y_train)
        
        # Examen final: ¿Qué tan bueno es adivinando datos que nunca ha visto?
        preds = self.model.predict(X_test)
        acc = accuracy_score(y_test, preds)
        print(f"[XGBOOST] ✅ Modelo entrenado! Precisión en datos no vistos: {acc*100:.2f}%\n")
        self.is_trained = True

    def predict_signal_quality(self, current_candle: dict) -> int:
        """
        Retorna 1 (Trade Aprobado) o 0 (Trade Vetado/Falsa Alarma)
        """
        if not self.is_trained:
            return 1 
            
        new_row = pd.DataFrame([current_candle])
        self.market_memory = pd.concat([self.market_memory, new_row], ignore_index=True)
        
        if len(self.market_memory) > 50:
            self.market_memory = self.market_memory.iloc[-50:]
            
        if len(self.market_memory) < 20:
            return 1 
            
        features = self.extract_features(self.market_memory)
        current_features = features.iloc[-1:]
        
        prediction = self.model.predict(current_features)[0]
        return int(prediction)