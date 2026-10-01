import os
import sys
import glob
import json
import pandas as pd
import numpy as np

# Inyectar el directorio padre al path para poder importar los módulos raíz
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from optimize import QuantCalculator
from quantitative_strategies.mean_reversion import MeanReversionStrategy
from quantitative_strategies.rolling_volatility import RollingVolatilityStrategy

RESULTS_FILE = os.path.join(os.path.dirname(__file__), "ml_results.json")

def run_ml_evaluation(roster: list):
    print(f"[ML EVALUATOR] Iniciando evaluación maestra para {len(roster)} activos...")
    
    # 1. Definir los rangos dinámicos que este evaluador específico decide probar
    windows = np.arange(8, 100, 4)
    multipliers = np.arange(0.8, 3.2, 0.2)
    
    strategies = {
        "MeanReversion": MeanReversionStrategy,
        "TrendFollowing": RollingVolatilityStrategy
    }
    
    ml_analysis = {}

    for symbol in roster:
        ml_analysis[symbol] = {}
        print(f"\n[ML EVALUATOR] Preparando entorno para {symbol}...")
        
        # 2. Buscar el archivo CSV correspondiente en la carpeta de datos
        data_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data'))
        files = glob.glob(f"{data_path}/**/*{symbol}*.csv", recursive=True)
        m15_files = [f for f in files if '15m' in f]
        
        if not m15_files:
            print(f"[ML EVALUATOR] ⚠️ No se encontraron datos 15m para {symbol}")
            continue
            
        csv_file = m15_files[-1]
        df = pd.read_csv(csv_file)
        prices = df['close'].values if 'close' in df.columns else df.iloc[:, 4].values 
        
        # 3. Delegar el cálculo intensivo a la calculadora muda
        for strat_name, StratClass in strategies.items():
            best_result = QuantCalculator.evaluate_strategy(symbol, prices, StratClass, windows, multipliers)
            
            if best_result:
                ml_analysis[symbol][strat_name] = best_result
            else:
                ml_analysis[symbol][strat_name] = {"error": "Sin configuraciones rentables"}
                
    # 4. Compilar y guardar el análisis propio de este modelo
    with open(RESULTS_FILE, 'w') as f:
        json.dump(ml_analysis, f, indent=4)
        
    print(f"\n[ML EVALUATOR] Análisis comparativo completado y guardado en {RESULTS_FILE}")
    return ml_analysis

if __name__ == "__main__":
    target_roster = ["BTCUSDT", "ETHUSDT"]
    run_ml_evaluation(target_roster)