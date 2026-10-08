import os
import datetime
from binance_historical_data import BinanceDataDumper
from config import ACTIVE_ROSTER

SYNC_FLAG_FILE = "./data/.last_sync"

def sync_historical_data(roster: list):
    today_str = datetime.date.today().isoformat()
    
    # 1. EVALUACIÓN RÁPIDA: ¿Ya sincronizamos hoy?
    if os.path.exists(SYNC_FLAG_FILE):
        with open(SYNC_FLAG_FILE, "r") as f:
            last_sync = f.read().strip()
            if last_sync == today_str:
                print(f"[DATA] Historial ya sincronizado hoy ({today_str}). Omitiendo descarga masiva.")
                return

    # 2. DESCARGA / ACTUALIZACIÓN
    print(f"[DATA] Iniciando verificacion y descarga historica para {roster}...")
    
    data_dumper = BinanceDataDumper(
        path_dir_where_to_dump="./data",
        asset_class="spot",      
        data_type="klines",      
        data_frequency="15m",    
    )

    yesterday = datetime.date.today() - datetime.timedelta(days=1)

    data_dumper.dump_data(
        tickers=roster,
        date_start=datetime.date(year=2023, month=1, day=1), 
        date_end=yesterday,
        is_to_update_existing=True
    )

    os.makedirs("./data", exist_ok=True)
    with open(SYNC_FLAG_FILE, "w") as f:
        f.write(today_str)

    print("[DATA] Sincronizacion de datos completada.")

if __name__ == '__main__':
    sync_historical_data(ACTIVE_ROSTER)