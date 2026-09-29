import pandas as pd
import glob
import os

def load_and_analyze_klines(symbol: str, timeframe: str):
    print(f"Hunting for {symbol} {timeframe} data files...")
    
    # Recursively search for ALL zip files anywhere inside the ./data directory
    all_zips = glob.glob("./data/**/*.zip", recursive=True)
    
    # Filter for the specific symbol and timeframe (e.g., looking for "BTCUSDT" and "-1h-")
    files = [f for f in all_zips if symbol in f and f"-{timeframe}-" in f]
    
    if not files:
        print("No data files found. Here is the actual folder structure:")
        for root, dirs, _ in os.walk("./data"):
            print(f"- {root}")
        return None

    print(f"Found {len(files)} files. Compiling into master dataset (this might take a few seconds)...")

    # Standard Binance API Klines (Candlestick) columns
    columns = [
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades",
        "taker_buy_base", "taker_buy_quote", "ignore"
    ]

    # Read all zipped CSVs and combine them
    dfs = [pd.read_csv(f, names=columns, header=None) for f in files]
    master_df = pd.concat(dfs, ignore_index=True)

    # Clean and format the timeline
    master_df['open_time'] = pd.to_datetime(master_df['open_time'], unit='ms')
    master_df.set_index('open_time', inplace=True)
    master_df.sort_index(inplace=True)
    
    # Convert string prices to floats for math operations
    master_df['close'] = master_df['close'].astype(float)
    
    # Calculate rolling volatility to inform our strategy
    master_df['hourly_return'] = master_df['close'].pct_change()
    avg_hourly_volatility = master_df['hourly_return'].std() * 100

    print("\n--- Data Compilation Complete ---")
    print(master_df[['open', 'high', 'low', 'close', 'volume']].tail())
    print(f"\nTotal 1-Hour Candles: {len(master_df):,}")
    print(f"Average Hourly Volatility: {avg_hourly_volatility:.4f}%")
    
    return master_df

if __name__ == '__main__':
    df = load_and_analyze_klines("BTCUSDT", "1h")