import pandas as pd
import glob
import os
from config import ACTIVE_ROSTER

def load_and_analyze_klines(symbol: str, timeframe: str):
    print(f"\nBuscando datos de {timeframe} para {symbol}...")
    
    all_csvs = glob.glob("./data/**/*.csv", recursive=True)
    files = [f for f in all_csvs if symbol in f and f"-{timeframe}-" in f]
    
    if not files:
        print(f"⚠️ No se encontraron archivos para {symbol}")
        return None

    columns = [
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades",
        "taker_buy_base", "taker_buy_quote", "ignore"
    ]

    dfs = [pd.read_csv(f, names=columns, header=None) for f in files]
    master_df = pd.concat(dfs, ignore_index=True)

    master_df['open_time'] = pd.to_datetime(master_df['open_time'].astype(float), unit='ms')
    master_df.set_index('open_time', inplace=True)
    master_df.sort_index(inplace=True)
    
    master_df['close'] = master_df['close'].astype(float)
    
    master_df['period_return'] = master_df['close'].pct_change()
    avg_volatility = master_df['period_return'].std() * 100

    print(f"Total Velas: {len(master_df):,}")
    print(f"Volatilidad Promedio por periodo: {avg_volatility:.4f}%")
    
    return master_df

if __name__ == '__main__':
    # Ahora iteramos correctamente sobre la lista de config.py
    for coin in ACTIVE_ROSTER:
        df = load_and_analyze_klines(coin, "15m")