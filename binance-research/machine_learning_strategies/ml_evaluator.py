import os
import sys
import glob
import json
import pandas as pd
import numpy as np

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from optimize import QuantCalculator
from config import ACTIVE_ROSTER

# Estrategias base
from quantitative_strategies.mean_reversion import MeanReversionStrategy
from quantitative_strategies.rolling_volatility import RollingVolatilityStrategy
from quantitative_strategies.vwap_strategy import VWAPReversionStrategy
from quantitative_strategies.volatility_squeeze import VolatilitySqueezeStrategy

# Modelos ML
from machine_learning_strategies.xgboost_classifier import XGBoostClassifier

RESULTS_FILE = os.path.join(os.path.dirname(__file__), "ml_results.json")

def run_ml_evaluation(roster: list):
    print(f"[ML EVALUATOR] Iniciando evaluación maestra para {len(roster)} activos...")
    
    windows = np.arange(8, 100, 4)
    multipliers = np.arange(0.8, 3.2, 0.2)
    
    strategies = {
        "MeanReversion": MeanReversionStrategy,
        "TrendFollowing": RollingVolatilityStrategy,
        "VWAP": VWAPReversionStrategy,
        "VolatilitySqueeze": VolatilitySqueezeStrategy
    }
    
    ml_analysis = {}

    for symbol in roster:
        ml_analysis[symbol] = {}
        print(f"\n==============================================")
        print(f"[ML EVALUATOR] Preparando entorno para {symbol}...")
        print(f"==============================================")
        
        data_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data'))
        files = glob.glob(f"{data_path}/**/*{symbol}*.csv", recursive=True)
        m15_files = [f for f in files if '15m' in f]
        
        if not m15_files:
            print(f"[ML EVALUATOR] ⚠️ No se encontraron datos 15m para {symbol}")
            continue
            
        csv_file = m15_files[-1]
        df = pd.read_csv(csv_file)
        
        # Mapeo de seguridad por si el CSV no tiene cabeceras
        if 'close' not in df.columns:
            df.columns = ["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume", "trades", "taker_buy_base", "taker_buy_quote", "ignore"]
            
        prices = df['close'].values 
        
        # --- FASE 1: OPTIMIZACIÓN CUANTITATIVA ---
        print(f"[FASE 1] Buscando hiperparámetros óptimos...")
        for strat_name, StratClass in strategies.items():
            best_result = QuantCalculator.evaluate_strategy(symbol, prices, StratClass, windows, multipliers)
            if best_result:
                ml_analysis[symbol][strat_name] = best_result
            else:
                ml_analysis[symbol][strat_name] = {"error": "Sin configuraciones rentables"}

        # --- FASE 2: ENTRENAMIENTO DE MACHINE LEARNING (XGBOOST) ---
        print(f"\n[FASE 2] Entrenando filtro táctico XGBoost para {symbol}...")
        
        # Etiquetado (Labeling): Le enseñamos a la IA qué es un buen trade.
        # Regla: "Es un buen trade (1) si el precio sube más de un 1% en las próximas 12 velas (3 horas)"
        df['future_return'] = df['close'].shift(-12) / df['close'] - 1
        target_labels = (df['future_return'] > 0.01).astype(int)
        
        # Instanciamos y entrenamos el cerebro táctico
        xgb_model = XGBoostClassifier()
        xgb_model.train(df, target_labels)
        
        # Marcamos en el JSON que el modelo está entrenado y listo
        ml_analysis[symbol]["XGBoost_Status"] = "Trained"
                
    with open(RESULTS_FILE, 'w') as f:
        json.dump(ml_analysis, f, indent=4)
        
    print(f"\n[ML EVALUATOR] ✅ Ciclo de entrenamiento completado. Archivo actualizado: {RESULTS_FILE}")
    return ml_analysis

if __name__ == "__main__":
    run_ml_evaluation(ACTIVE_ROSTER)