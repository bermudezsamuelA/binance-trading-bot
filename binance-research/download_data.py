from binance_historical_data import BinanceDataDumper
import datetime

if __name__ == '__main__':
    data_dumper = BinanceDataDumper(
        path_dir_where_to_dump="./data",
        asset_class="spot",      
        data_type="klines",      
        data_frequency="1h",     
    )

    # The same roster used by our trading engine
    target_roster = ["BTCUSDT", "ETHUSDT"]

    print(f"Starting bulk download for {target_roster} from Binance Vision...")

    data_dumper.dump_data(
        tickers=target_roster,
        date_start=datetime.date(year=2021, month=1, day=1),
        # Using today's year ensures it pulls up to the current date
        date_end=datetime.date(year=2026, month=1, day=1),
        is_to_update_existing=True
    )

    print("Download complete. Data saved to ./data/")