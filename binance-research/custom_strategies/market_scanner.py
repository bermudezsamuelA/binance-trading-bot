# custom_strategies/market_scanner.py
import os
import sys
import time
import requests
import numpy as np
import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from config import BINANCE_MARKET, MARKET_DATA_REST_URL
except ImportError:
    BINANCE_MARKET = os.environ.get("BINANCE_MARKET", "testnet").strip().lower()
    MARKET_DATA_REST_URL = "https://testnet.binance.vision" if BINANCE_MARKET == "testnet" else "https://api.binance.com"


class MarketScanner:
    def __init__(self, top_n: int = 50, market_type: str = "spot", use_mainnet_for_scan: bool = True):
        """
        Escáner del Top N de criptomonedas y clasificador en CRYPTO_L (Long) y CRYPTO_S (Short) (Módulo 3).

        Args:
            top_n (int): Cantidad de pares con mayor volumen a filtrar (por defecto Top 50).
            market_type (str): 'spot' o 'futures'.
            use_mainnet_for_scan (bool): En testnet el volumen 24h es ficticio; si es True, consulta
                                         el ranking de volumen en Mainnet pública sin requerir API Key.
        """
        self.top_n = int(top_n)
        self.market_type = market_type.lower()
        if self.market_type == "futures":
            self.base_url = "https://fapi.binance.com"
            self.ticker_endpoint = "/fapi/v1/ticker/24hr"
            self.klines_endpoint = "/fapi/v1/klines"
            self.time_endpoint = "/fapi/v1/time"
        else:
            self.base_url = "https://api.binance.com" if use_mainnet_for_scan else MARKET_DATA_REST_URL
            self.ticker_endpoint = "/api/v3/ticker/24hr"
            self.klines_endpoint = "/api/v3/klines"
            self.time_endpoint = "/api/v3/time"

    def _server_time_ms(self) -> int:
        try:
            r = requests.get(f"{self.base_url}{self.time_endpoint}", timeout=5)
            r.raise_for_status()
            return int(r.json()["serverTime"])
        except Exception:
            return int(time.time() * 1000)

    def get_top_volume_symbols(self) -> list:
        """
        Obtiene el Top N de símbolos cotizados en USDT por volumen 24h, excluyendo stablecoins
        y tokens apalancados.
        """
        excluded_prefixes = ("USDC", "FDUSD", "TUSD", "USDP", "DAI", "BUSD", "EUR", "AEUR", "UST", "PAXG")
        excluded_suffixes = ("UPUSDT", "DOWNUSDT", "BEARUSDT", "BULLUSDT")
        try:
            response = requests.get(f"{self.base_url}{self.ticker_endpoint}", timeout=10)
            response.raise_for_status()
            data = response.json()

            usdt_pairs = []
            for item in data:
                sym = item.get("symbol", "")
                if not sym.endswith("USDT"):
                    continue
                if sym.endswith(excluded_suffixes):
                    continue
                base_asset = sym[:-4]
                if base_asset in excluded_prefixes:
                    continue
                usdt_pairs.append(item)

            usdt_pairs.sort(key=lambda x: float(x.get("quoteVolume", 0.0)), reverse=True)
            return [item["symbol"] for item in usdt_pairs[:self.top_n]]
        except Exception as e:
            print(f"[SCANNER] Error obteniendo Top Volumen de Binance: {e}")
            return ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT"]

    def fetch_closed_klines(self, symbol: str, interval: str = "1h", limit: int = 230) -> pd.DataFrame:
        """
        Descarga únicamente velas CERRADAS (descarta la vela en formación cuyo close_time >= now_ms)
        para evitar señales falsas en vivo.
        """
        try:
            params = {"symbol": symbol, "interval": interval, "limit": min(limit + 1, 1000)}
            response = requests.get(f"{self.base_url}{self.klines_endpoint}", params=params, timeout=10)
            response.raise_for_status()
            now_ms = self._server_time_ms()
            closed_raw = [k for k in response.json() if int(k[6]) < now_ms][-limit:]

            if not closed_raw:
                return pd.DataFrame()

            df = pd.DataFrame(closed_raw, columns=[
                "open_time", "open", "high", "low", "close", "volume",
                "close_time", "quote_volume", "trades", "taker_buy_base", "taker_buy_quote", "ignore"
            ])
            df["open_time"] = df["open_time"].astype(np.int64)
            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = df[col].astype(float)
            return df
        except Exception as e:
            print(f"[SCANNER] Error descargando klines ({interval}) para {symbol}: {e}")
            return pd.DataFrame()

    def classify_asset(self, symbol: str, df_1h: pd.DataFrame = None, df_4h: pd.DataFrame = None) -> dict:
        """
        Clasifica un activo en los escenarios del Módulo 3, define su lista (`CRYPTO_L` o `CRYPTO_S`)
        y le asigna el color del semáforo (`ROJO`, `NARANJA`, `AMARILLO`, `GRIS`).
        """
        if df_1h is None:
            df_1h = self.fetch_closed_klines(symbol, interval="1h", limit=220)
        if df_1h.empty or len(df_1h) < 200:
            return {
                "symbol": symbol,
                "watchlist": "NONE",
                "direction": "NEUTRAL",
                "scenario": "DESCARTADO",
                "semaforo": "GRIS",
                "reason": "Datos insuficientes (< 200 velas 1H)"
            }

        close_1h = df_1h["close"].to_numpy(float)
        open_1h = df_1h["open"].to_numpy(float)
        ema50_1h = pd.Series(close_1h).ewm(span=50, adjust=False).mean().to_numpy()
        sma200_1h = pd.Series(close_1h).rolling(window=200).mean().to_numpy()

        curr_px = float(close_1h[-1])
        prev_px = float(close_1h[-2])
        cur_ema50_1h = float(ema50_1h[-1])
        prev_ema50_1h = float(ema50_1h[-2])
        cur_sma200_1h = float(sma200_1h[-1])

        # Opcional: obtener EMA 50 de 4H haciendo resample de 1H o recibiendo df_4h
        if df_4h is not None and len(df_4h) >= 50:
            ema50_4h_val = float(pd.Series(df_4h["close"].to_numpy(float)).ewm(span=50, adjust=False).mean().iloc[-1])
        else:
            # Aproximación rápida desde 1H (EMA 200 en 1H equivale estructuralmente a EMA 50 en 4H)
            ema50_4h_val = float(pd.Series(close_1h).ewm(span=200, adjust=False).mean().iloc[-1])

        # Desaceleración en 1H
        bodies = np.abs(close_1h - open_1h)
        avg_body = float(np.mean(bodies[-12:-3])) if len(bodies) >= 12 else float(np.mean(bodies))
        recent_body = float(np.mean(bodies[-3:]))
        is_decelerating = recent_body <= (avg_body * 0.75)

        dist_sma200_pct = abs(curr_px - cur_sma200_1h) / curr_px * 100.0
        dist_ema50_1h_pct = abs(curr_px - cur_ema50_1h) / curr_px * 100.0
        dist_ema50_4h_pct = abs(curr_px - ema50_4h_val) / curr_px * 100.0

        # 1. ESCENARIO 2: Sobreextensión chocando contra SMA 200 (1H) o EMA 50 (4H) con desaceleración (Caso BGB / BCH)
        if (dist_sma200_pct <= 1.5 or dist_ema50_4h_pct <= 1.2) and is_decelerating:
            # Si cayó desde arriba hacia la SMA 200, buscamos rebote en LONG
            came_from_above = float(np.mean(close_1h[-15:-5])) > cur_sma200_1h
            direction = "LONG" if came_from_above else "SHORT"
            watchlist = "CRYPTO_L" if direction == "LONG" else "CRYPTO_S"
            min_dist = min(dist_sma200_pct, dist_ema50_4h_pct)
            semaforo = "ROJO" if min_dist <= 0.75 else "NARANJA"
            return {
                "symbol": symbol,
                "watchlist": watchlist,
                "direction": direction,
                "scenario": "ESCENARIO_2_SOBREEXTENSION",
                "semaforo": semaforo,
                "current_price": curr_px,
                "ema50_1h": round(cur_ema50_1h, 8),
                "sma200_1h": round(cur_sma200_1h, 8),
                "reason": f"Choque con soporte/resistencia mayor (SMA200 1H / EMA50 4H a {min_dist:.2f}%) + desaceleración"
            }

        # 2. ESCENARIO 1: Ruptura reciente de EMA 50 (1H) o Pullback activo hacia ella (Caso ATOM)
        broke_up_1h = curr_px > cur_ema50_1h and prev_px <= prev_ema50_1h
        broke_down_1h = curr_px < cur_ema50_1h and prev_px >= prev_ema50_1h

        if broke_up_1h or broke_down_1h:
            direction = "LONG" if broke_up_1h else "SHORT"
            return {
                "symbol": symbol,
                "watchlist": "CRYPTO_L" if direction == "LONG" else "CRYPTO_S",
                "direction": direction,
                "scenario": "ESCENARIO_1_CONTINUACION",
                "semaforo": "NARANJA",  # Acaba de romper en 1H, ahora hay que esperar el pullback
                "current_price": curr_px,
                "ema50_1h": round(cur_ema50_1h, 8),
                "sma200_1h": round(cur_sma200_1h, 8),
                "reason": f"Ruptura {direction} de EMA 50 en 1H confirmada; esperando pullback"
            }

        # Activo en tendencia clara haciendo pullback cercano a la EMA 50 (1H)
        if dist_ema50_1h_pct <= 1.2:
            direction = "LONG" if curr_px >= cur_ema50_1h else "SHORT"
            semaforo = "ROJO" if (dist_ema50_1h_pct <= 0.6 and is_decelerating) else "NARANJA"
            return {
                "symbol": symbol,
                "watchlist": "CRYPTO_L" if direction == "LONG" else "CRYPTO_S",
                "direction": direction,
                "scenario": "ESCENARIO_1_CONTINUACION",
                "semaforo": semaforo,
                "current_price": curr_px,
                "ema50_1h": round(cur_ema50_1h, 8),
                "sma200_1h": round(cur_sma200_1h, 8),
                "reason": f"Pullback {direction} testeando EMA 50 en 1H (distancia {dist_ema50_1h_pct:.2f}%)"
            }

        return {
            "symbol": symbol,
            "watchlist": "NONE",
            "direction": "NEUTRAL",
            "scenario": "ESCENARIO_3_LATERAL_DESCARTADO",
            "semaforo": "AMARILLO",
            "current_price": curr_px,
            "ema50_1h": round(cur_ema50_1h, 8),
            "sma200_1h": round(cur_sma200_1h, 8),
            "reason": "Sin proximidad a zonas operables o en rango"
        }

    def scan_market(self) -> dict:
        """
        Escanea el Top N y devuelve las listas separadas `CRYPTO_L` y `CRYPTO_S` ordenadas por semáforo.
        """
        symbols = self.get_top_volume_symbols()
        crypto_l = []
        crypto_s = []
        priority_map = {"ROJO": 1, "NARANJA": 2, "AMARILLO": 3, "GRIS": 4}

        for sym in symbols:
            res = self.classify_asset(sym)
            if res["watchlist"] == "CRYPTO_L":
                crypto_l.append(res)
            elif res["watchlist"] == "CRYPTO_S":
                crypto_s.append(res)
            time.sleep(0.05)

        crypto_l.sort(key=lambda x: priority_map.get(x["semaforo"], 99))
        crypto_s.sort(key=lambda x: priority_map.get(x["semaforo"], 99))

        return {
            "scanned_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "total_top_scanned": len(symbols),
            "CRYPTO_L": crypto_l,
            "CRYPTO_S": crypto_s,
            "actionable_opportunities": crypto_l + crypto_s
        }