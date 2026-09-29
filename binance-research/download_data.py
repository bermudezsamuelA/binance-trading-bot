from binance_historical_data import BinanceDataDumper
import datetime

if __name__ == '__main__':
    # Initialize the automated downloader
    data_dumper = BinanceDataDumper(
        path_dir_where_to_dump="./data",
        asset_class="spot",      # 'spot', 'um' (USDT futures), or 'cm' (Coin futures)
        data_type="klines",      # 'klines' (candles), 'trades', or 'aggTrades'
        data_frequency="1h",     # 1m, 5m, 15m, 1h, 4h, 1d, etc.
    )

    print("Starting bulk download from Binance Vision...")

    # Dump 5 years of data (2021 to 2026)
    data_dumper.dump_data(
        tickers=["BTCUSDT"],
        date_start=datetime.date(year=2021, month=1, day=1),
        date_end=datetime.date(year=2026, month=1, day=1),
        is_to_update_existing=True
    )

    print("Download complete. Data saved to ./data/")