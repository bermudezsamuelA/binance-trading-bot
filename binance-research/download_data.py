# download_data.py
from binance_historical_data import BinanceDataDumper
import datetime
from config import ACTIVE_ROSTER

def sync_historical_data(roster: list):
    print(f"[DATA] Iniciando verificacion y descarga historica para {roster}...")
    
    data_dumper = BinanceDataDumper(
        path_dir_where_to_dump="./data",
        asset_class="spot",      
        data_type="klines",      
        data_frequency="15m",     
    )

    # Calcula la fecha de ayer dinámicamente
    yesterday = datetime.date.today() - datetime.timedelta(days=1)

    data_dumper.dump_data(
        tickers=roster,
        date_start=datetime.date(year=2024, month=1, day=1),
        date_end=yesterday,
        is_to_update_existing=True
    )

    print("[DATA] Sincronizacion de datos completada.")

if __name__ == '__main__':
    # Permite ejecución manual si es necesario
    sync_historical_data(ACTIVE_ROSTER)