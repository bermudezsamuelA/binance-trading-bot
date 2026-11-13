# download_data.py
import argparse
import os
import datetime
from binance_historical_data import BinanceDataDumper
from config import ACTIVE_ROSTER

SYNC_FLAG_FILE = "./data/.last_sync"


def _flag_file_for_frequency(freq: str) -> str:
    """Mantiene ./data/.last_sync para 15m (compatibilidad total) y crea ./data/.last_sync_<freq> para otras (ej. 5m)."""
    return SYNC_FLAG_FILE if freq == "15m" else f"./data/.last_sync_{freq}"


def sync_historical_data(roster: list, frequencies: tuple = ("15m",), force: bool = False):
    today_str = datetime.date.today().isoformat()
    yesterday = datetime.date.today() - datetime.timedelta(days=1)
    os.makedirs("./data", exist_ok=True)

    for freq in frequencies:
        flag_path = _flag_file_for_frequency(freq)

        # 1. EVALUACIÓN RÁPIDA: ¿Ya sincronizamos esta temporalidad hoy?
        if not force and os.path.exists(flag_path):
            with open(flag_path, "r", encoding="utf-8") as f:
                last_sync = f.read().strip()
                if last_sync == today_str:
                    print(f"[DATA] Historial ({freq}) ya sincronizado hoy ({today_str}). Omitiendo descarga masiva.")
                    continue

        # 2. DESCARGA / ACTUALIZACIÓN
        print(f"[DATA] Iniciando verificacion y descarga historica ({freq}) para {roster}...")

        data_dumper = BinanceDataDumper(
            path_dir_where_to_dump="./data",
            asset_class="spot",
            data_type="klines",
            data_frequency=freq,
        )

        data_dumper.dump_data(
            tickers=roster,
            date_start=datetime.date(year=2023, month=1, day=1),
            date_end=yesterday,
            is_to_update_existing=True
        )

        with open(flag_path, "w", encoding="utf-8") as f:
            f.write(today_str)

        print(f"[DATA] Sincronizacion de datos ({freq}) completada.")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Descarga o actualiza klines historicos de Binance.")
    parser.add_argument(
        "--intervals",
        nargs="+",
        default=["15m"],
        choices=["5m", "15m", "1h", "4h", "1d"],
        help="Temporalidades a descargar (por defecto: 15m; agrega 5m para CustomFractalStrategy)."
    )
    parser.add_argument("--force", action="store_true", help="Fuerza la verificacion ignorando .last_sync")
    args = parser.parse_args()

    sync_historical_data(ACTIVE_ROSTER, frequencies=tuple(args.intervals), force=args.force)