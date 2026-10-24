"""Canal sombra diario de la v3: la prueba PROSPECTIVA pre-registrada (doc/estrategia-v3-hacia-el-80.md, seccion 8).

No opera ni envia ordenes. Con la especificacion congelada (output/constructor/spec_nn_v2.json, sus 13 modelos y los
scripts, verificados por SHA-256 antes de empezar), evalua las 4 anclas desde 2026-10-01 hasta donde haya datos
COMPLETOS y simula los brazos del pre-registro con el arnes del laboratorio (harness.simulate):

  P1  primario: v2 (p >= theta) + compuerta A4 >= 1 (otra ancla con senal en las ultimas 48 velas, incluida la
      actual) + salida X5 con barrera de 384 velas. Es lo de nn/nn_v3_desc.py, con los mismos calculos.
  C0  control: v2 sin compuerta, X5 384.
  S3  secundario (regla de episodio D1): P1 sin comprar cuando z30(DVOL de BTC) < -1.
  S1  secundario: v2 en las 18 monedas del universo (4 anclas + 14) con A18 >= 3 (al menos 3 de las otras 17 con senal
      en las ultimas 48 velas), X5 384. Con --solo-anclas no se calcula.
  Azar: entradas en todas las velas validas (por moneda y mes) y azar condicionado (solo en velas con A4 >= 1).
  Costos: 0.24 % (principal), 0.30 % (estres), 0.19 % (BNB) y 0.17 % (BNB con el TP como orden limite: la salida por TP
  no paga deslizamiento; aproximacion: se llena al tocar el TP), estos dos informativos.
  R (exploratorio, hipotesis 4.4 "BTC > SMA30" grabada en el documento): P1+R y S1+R solo compran si el cierre de BTC
      esta por encima de su media de 30 dias (2880 velas de 15 min). Fijada el 2026-10-24 antes de mirarla en 2022
      (estres) y en 2025-07..2026-09; una sola regla, sin variantes.
S2 (ENS12U, aun sin congelar) y S4 (opcional) no estan aqui.

Los datos llegan con retraso (data.binance.vision publica al dia siguiente y el funding solo por mes), asi que cada
corrida evalua hasta el minimo comun de todas las series y recalcula todo desde 2026-10-01 (es determinista). Las
operaciones que siguen abiertas en ese corte no cuentan todavia.

Uso (desde binance-research, con la VPN apagada para --download):
  .venv\\Scripts\\python v3_research\\shadow\\run_daily.py --download
  .venv\\Scripts\\python v3_research\\shadow\\run_daily.py            # solo recalcula con los datos que ya hay
Salida: v3_research/output/prospectivo/ (resumen.md, resumen.json, senales.csv, operaciones_{brazo}.csv).
"""
import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
RESEARCH = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(RESEARCH, "nn"))
sys.path.insert(0, HERE)
import nn_v3_desc as V3  # noqa: E402  (registra X5_384 y trae C, W, R, H y la carga de los modelos)

C, W, R, H = V3.C, V3.W, V3.R, V3.H
ANCHORS = V3.ANCHORS
OTHERS = ["ADAUSDT", "ATOMUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOTUSDT", "ETCUSDT", "FILUSDT", "LINKUSDT",
          "LTCUSDT", "NEARUSDT", "TRXUSDT", "UNIUSDT", "XRPUSDT"]
UNIVERSE = list(ANCHORS) + OTHERS          # universo de 18 del pre-registro (seccion 8.2)
S1_MIN = 3
REGIME_CANDLES = 30 * 96      # media de 30 dias del cierre de BTC (hipotesis 4.4)
DAY_MS = 86_400_000
OUT_DIR = os.path.join(RESEARCH, "output", "prospectivo")
DVOL_FILE = os.path.join(RESEARCH, "cache", "deribit", "dvol_BTC_1h.json")
WARMUP_DAYS = 75            # > 35 dias que pide la spec (W.WARM = 800 velas, z de 672 y funding_z de 2016) y el mes de
                            # la prueba de equivalencia del funding provisional (EQUIVALENCE_DAYS) con su calentamiento
# costo: (comision por lado, deslizamiento por lado, TP con orden limite)
COSTS = {"0.24 %": (H.FEE, H.SLIP, False), "0.30 %": (0.0013, H.SLIP, False), "0.19 % (BNB)": (0.00075, H.SLIP, False),
         "0.17 % (BNB + TP límite)": (0.00075, H.SLIP, True)}
MAIN_COST = "0.24 %"

# Pre-registro (seccion 8.2 y 8.3, redactado el 2026-10-15 y actualizado el 2026-10-16). No se cambia durante la prueba.
PREREGISTRO = {
    "inicio": "2026-10-01", "fin": "2027-12-31 o 400 operaciones de P1, lo que llegue primero",
    "brazos": {"P1": "v2 + A4 >= 1 (W = 48 velas de 15 min) + X5 con 384 velas",
               "C0": "v2 sin compuerta, X5 con 384 velas",
               "S3": "P1 + D1 (no comprar si z30 del DVOL de BTC < -1)",
               "S1": "v2 + A18 >= 3 en las 18 monedas, X5 con 384 velas"},
    "criterios_P1": ["1. E > 0 con t por dia >= 1.645, y E > 0 con c = 0.30 %",
                     "2. Wilson inferior >= 0.70 (aprueba 70), >= 0.75 (aprueba 75); 80 solo con inferior >= 0.80",
                     "3. dE frente al azar > 0 con t >= 1.645, y dWR > 0",
                     "4. E(P1) - E(C0 con A4 = 0) > 0 con P <= 0.10 (bootstrap por dias)",
                     "5. >= 60 % de los episodios en positivo",
                     "6. hashes intactos"],
    "criterio_S3": "con >= 150 senales de P1, las vetadas por D1 tienen menos WR (P <= 0.10 por episodio), >= 5 episodios",
    "vigilancia": "e-proceso sobre el WR con p0 = 0.70 (rechaza H0 si M >= 20); futilidad con >= 200 operaciones",
}
P0, E_STOP = 0.70, 20.0
LAMBDA_MAX = 1 / P0 - 1e-6   # la apuesta (X - p0) debe dejar 1 + lambda (X - p0) > 0


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def to_ms(s):
    return int(dt.datetime.fromisoformat(s).replace(tzinfo=dt.timezone.utc).timestamp() * 1000)


def iso(ms):
    return dt.datetime.fromtimestamp(int(ms) / 1000, dt.timezone.utc).strftime("%Y-%m-%d %H:%M")


# ------------------------------------------------------------------ cobertura de los datos
def data_end_ms(data_dir: str, symbols=ANCHORS) -> tuple:
    """Primer open_time de 15 min que YA NO tiene todas sus series completas (fin exclusivo de la evaluacion) y el
    detalle por serie. Una vela t necesita: su vela spot (de cada ancla y de BTC), la de futuros y la de la prima
    (t + 15 min), los metrics hasta t + 5 min y el funding vigente (cada 8 h: el ultimo calc_time + 8 h)."""
    limits = {}
    for sym in symbols:
        spot = C.load_spot(data_dir, sym)
        fu = C.load_fut(data_dir, sym)
        limits[f"{sym} spot"] = int(spot[:, 0].max()) + C.MS15
        limits[f"{sym} fut15m"] = int(fu["fut15m"][:, 0].max()) + C.MS15
        limits[f"{sym} premium15m"] = int(fu["premium15m"][:, 0].max()) + C.MS15
        limits[f"{sym} metrics"] = int(fu["metrics"][:, 0].max()) - 300_000 + C.MS15
        limits[f"{sym} funding"] = int(fu["funding"][:, 0].max()) + 8 * 3_600_000
    end = min(limits.values())
    return end - end % C.MS15, limits


# ------------------------------------------------------------------ funding provisional
# Binance publica el funding solo en archivos mensuales: el mes en curso no tiene dato real hasta el mes siguiente. El
# funding de USD-M se calcula con la prima del perpetuo (que si sale a diario): F = P + clamp(I - P, -0.05 %, 0.05 %),
# con P = media ponderada (pesos 1..n, mas peso a lo reciente) de la prima de las 8 h previas e I = 0.01 % cada 8 h.
# Aqui P sale de las 32 velas de 15 min de la prima (Binance usa muestras por minuto): es una aproximacion, y por eso
# se mide su equivalencia con el funding real (equivalence) antes de usarla y los resultados quedan como PROVISIONALES.
FUNDING_MS = 8 * 3_600_000
FUNDING_INTEREST = 0.0001
FUNDING_CLAMP = 0.0005


def funding_proxy(premium: np.ndarray, after_ms: int, until_ms: int) -> np.ndarray:
    """Filas [calc_time, funding] reconstruidas en la rejilla de 8 h (00, 08 y 16 UTC) con after_ms < T <= until_ms,
    solo donde estan las 32 velas de prima de [T - 8 h, T)."""
    premium = premium[np.argsort(premium[:, 0], kind="stable")]
    t, close = premium[:, 0].astype(np.int64), premium[:, 4]
    rows, T = [], (int(after_ms) // FUNDING_MS + 1) * FUNDING_MS
    w = np.arange(1, 33, dtype=float)
    while T <= until_ms:
        a, b = np.searchsorted(t, T - FUNDING_MS), np.searchsorted(t, T)
        x = close[a:b]
        if b - a == 32 and np.all(np.isfinite(x)):
            P = float((w * x).sum() / w.sum())
            rows.append((T, P + float(np.clip(FUNDING_INTEREST - P, -FUNDING_CLAMP, FUNDING_CLAMP))))
        T += FUNDING_MS
    return np.array(rows, dtype=np.float64).reshape(-1, 2)


class ProxyFunding:
    """Mientras esta activo, nn_common.load_fut devuelve el funding real hasta `cut_ms` (incluido) y, despues, el
    reconstruido con la prima. cut_ms None = desde el ultimo funding real. No toca los archivos ni los modelos."""

    def __init__(self, cut_ms=None):
        self.cut_ms, self.original = cut_ms, None

    def __enter__(self):
        self.original = C.load_fut
        original, cut_ms = self.original, self.cut_ms

        def load_fut(data_dir, sym):
            fu = dict(original(data_dir, sym))
            fr = fu["funding"]
            cut = int(fr[:, 0].max()) if cut_ms is None else int(cut_ms)
            proxy = funding_proxy(fu["premium15m"], cut, int(fu["premium15m"][:, 0].max()) + C.MS15)
            fu["funding"] = np.vstack([fr[fr[:, 0] <= cut], proxy])
            return fu
        C.load_fut = load_fut
        return self

    def __exit__(self, *exc):
        C.load_fut = self.original


def funding_fit(data_dir: str, days: int = 90) -> dict:
    """Funding reconstruido frente al real en los ultimos `days` dias con dato real, por moneda."""
    out = {}
    for sym in ANCHORS:
        fu = C.load_fut(data_dir, sym)
        fr = fu["funding"][np.argsort(fu["funding"][:, 0])]
        last = int(fr[:, 0].max())
        real = fr[fr[:, 0] > last - days * DAY_MS]
        grid = (real[:, 0].astype(np.int64) + 60_000) // FUNDING_MS * FUNDING_MS   # la marca real trae milisegundos
        proxy = funding_proxy(fu["premium15m"], last - days * DAY_MS - FUNDING_MS, last + 60_000)
        j = np.searchsorted(proxy[:, 0].astype(np.int64), grid)
        ok = (j < len(proxy)) & (proxy[np.minimum(j, len(proxy) - 1), 0].astype(np.int64) == grid)
        r, p = real[ok, 1], proxy[j[ok], 1]
        varies = ok.sum() > 2 and np.std(r) > 0 and np.std(p) > 0   # dentro de la banda el funding es justo 0.01 %
        out[sym] = {"n": int(ok.sum()), "corr": round(float(np.corrcoef(r, p)[0, 1]), 4) if varies else None,
                    "iguales_pct": round(100 * float(np.mean(np.abs(r - p) < 5e-6)), 1) if ok.any() else None,
                    "error_medio_pb": round(float(np.mean(np.abs(r - p)) * 1e4), 3) if ok.any() else None,
                    "error_max_pb": round(float(np.max(np.abs(r - p)) * 1e4), 3) if ok.any() else None}
    return out


def signal_sets(ev: dict) -> tuple:
    """(velas con p >= theta, velas de P1) de una evaluacion, como conjuntos de (moneda, open_time)."""
    sig, p1 = set(), set()
    for sym, d in ev["D"].items():
        for i in np.flatnonzero(d["sig"][d["i0"]:d["i1"]]) + d["i0"]:
            t = int(d["S"]["t"][i])
            sig.add((sym, t))
            if d["A"][i] >= 1:
                p1.add((sym, t))
    return sig, p1


def jaccard(a: set, b: set) -> float:
    return 1.0 if not a and not b else len(a & b) / len(a | b)


EQUIVALENCE_DAYS = 30
EQUIVALENCE_MIN_JACCARD = 0.8


def equivalence(data_dir: str, out_dir: str) -> dict:
    """Mismo modelo con el funding real y con el reconstruido en los ultimos EQUIVALENCE_DAYS dias con dato real:
    coincidencia (Jaccard) de las velas con senal y de las de P1. Se guarda y solo se repite cuando llega un mes nuevo
    de funding real. Ese periodo es de la reserva gastada: se abre con motivo (queda en holdout_log.csv) y no decide nada."""
    path = os.path.join(out_dir, "equivalencia_funding.json")
    real_end = min(int(C.load_fut(data_dir, s)["funding"][:, 0].max()) for s in ANCHORS)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            cached = json.load(f)
        if cached.get("funding_real_hasta") == iso(real_end):
            return cached
    end = real_end + FUNDING_MS - (real_end + FUNDING_MS) % C.MS15
    cut = end - EQUIVALENCE_DAYS * DAY_MS
    start = dt.datetime.fromtimestamp(cut / 1000, dt.timezone.utc).strftime("%Y-%m-%d")
    reason = "equivalencia del funding provisional (infraestructura; no decide nada)"
    real = signal_sets(evaluate(data_dir, start, end, reason))
    with ProxyFunding(cut_ms=to_ms(start) - FUNDING_MS):
        prox = signal_sets(evaluate(data_dir, start, end, reason))
    res = {"funding_real_hasta": iso(real_end), "ventana": [start, iso(end)], "funding": funding_fit(data_dir),
           "senales": {"real": len(real[0]), "provisional": len(prox[0]), "jaccard": round(jaccard(real[0], prox[0]), 4)},
           "P1": {"real": len(real[1]), "provisional": len(prox[1]), "jaccard": round(jaccard(real[1], prox[1]), 4)}}
    res["equivalente"] = bool(res["senales"]["jaccard"] >= EQUIVALENCE_MIN_JACCARD
                              and res["P1"]["jaccard"] >= EQUIVALENCE_MIN_JACCARD)
    os.makedirs(out_dir, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    return res


# ------------------------------------------------------------------ D1 (DVOL)
def dvol_z30(path: str = DVOL_FILE):
    """(hora de cierre, z30) del DVOL: z = (DVOL_h - media de 720 horas) / desviacion (ddof 0), como be2c_dvol.py."""
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        d = np.array(json.load(f), float)
    d = d[np.argsort(d[:, 0], kind="stable")]
    ct = d[:, 0].astype(np.int64) + 3_600_000
    dv = d[:, 4]
    z = np.full(len(dv), np.nan)
    cs, cs2 = np.cumsum(np.r_[0, dv]), np.cumsum(np.r_[0, dv * dv])
    for i in range(719, len(dv)):
        m = (cs[i + 1] - cs[i - 719]) / 720
        v = (cs2[i + 1] - cs2[i - 719]) / 720 - m * m
        z[i] = (dv[i] - m) / (np.sqrt(max(v, 0)) + 1e-9)
    return ct, z


def z_at_open(series, t_open):
    """z30 de la ultima hora cerrada antes de la apertura de cada vela (NaN si no hay DVOL o tiene > 2 h)."""
    t_open = np.asarray(t_open, np.int64)
    if series is None:
        return np.full(len(t_open), np.nan)
    ct, z = series
    i = np.searchsorted(ct, t_open, side="right") - 1
    ok = (i >= 0) & (t_open - ct[np.maximum(i, 0)] <= 2 * 3_600_000)
    return np.where(ok, z[np.maximum(i, 0)], np.nan)


# ------------------------------------------------------------------ estadistica del pre-registro
def episodes(entry_t, net) -> list:
    """PnL por episodio: dias con operaciones separados por <= 2 dias forman un mismo episodio."""
    if not len(entry_t):
        return []
    day = np.asarray(entry_t, np.int64) // DAY_MS
    order = np.argsort(day, kind="stable")
    day, net = day[order], np.asarray(net, float)[order]
    cut = np.r_[True, np.diff(day) > 2]
    ids = np.cumsum(cut) - 1
    return [float(x) for x in np.bincount(ids, weights=net)]


def e_process(wins_by_exit, p0: float = P0) -> list:
    """M_n = prod (1 + lambda_i (X_i - p0)) con lambda_i predecible (solo con operaciones ya cerradas): medio Kelly
    con el WR previo encogido hacia 0.75 (10 operaciones de prior), entre 0 y 1/p0."""
    m, out, k, n = 1.0, [], 0, 0
    for x in wins_by_exit:
        p_hat = (k + 0.75 * 10) / (n + 10)
        lam = float(np.clip(0.5 * (p_hat - p0) / (p0 * (1 - p0)), 0.0, LAMBDA_MAX))
        m *= 1 + lam * (float(x) - p0)
        out.append(m)
        k, n = k + int(x), n + 1
    return out


def boot_diff_days(a_net, a_day, b_net, b_day, B: int = 5000, seed: int = 0) -> float:
    """P(E(a) - E(b) <= 0) con bootstrap por dias (cada brazo remuestrea sus dias con reemplazo)."""
    if len(a_net) < 2 or len(b_net) < 2:
        return float("nan")
    rng = np.random.default_rng(seed)

    def groups(net, day):
        u, inv = np.unique(day, return_inverse=True)
        return np.bincount(inv, weights=net), np.bincount(inv).astype(float)
    sa, na = groups(np.asarray(a_net, float), np.asarray(a_day))
    sb, nb = groups(np.asarray(b_net, float), np.asarray(b_day))
    ia, ib = rng.integers(0, len(sa), (B, len(sa))), rng.integers(0, len(sb), (B, len(sb)))
    diff = sa[ia].sum(1) / na[ia].sum(1) - sb[ib].sum(1) / nb[ib].sum(1)
    return float(np.mean(diff <= 0))


def closed(tr):
    """Operaciones ya cerradas (las que siguen abiertas en el corte de datos salen con motivo END)."""
    return np.asarray(tr.reason) != H.END


def arm_stats(trades: list, base: dict, label: str) -> dict:
    """Resumen de un brazo con sus operaciones cerradas: el de nn_report.summarize (Wilson, t por dia, dWR y dE frente al
    azar de la misma moneda y mes) mas meses, episodios y abiertas."""
    done = [(s, t.subset(closed(t))) for s, t in trades]
    done = [(s, t) for s, t in done if len(t)]
    open_n = sum(int((~closed(t)).sum()) for _, t in trades)
    if not done:
        return {"label": label, "n": 0, "abiertas": open_n}
    m, T, syms = R.summarize(done, base, 1, label)
    mon = [iso(x)[:7] for x in T.entry_t]
    u, inv = np.unique(mon, return_inverse=True)
    mp = np.bincount(inv, weights=T.net_ret)
    ep = episodes(T.entry_t, T.net_ret)
    m.update(abiertas=open_n, meses_positivos=[int((mp > 0).sum()), len(u)],
             episodios=len(ep), episodios_positivos_pct=100.0 * float(np.mean(np.array(ep) > 0)) if ep else float("nan"),
             pnl_15usdt=float(np.sum(T.net_ret) * 15))
    m.pop("by_sym", None)
    return m


# ------------------------------------------------------------------ evaluacion
def evaluate(data_dir: str, start: str, end_ms: int, reason: str = None, dvol_file: str = DVOL_FILE,
             symbols=ANCHORS) -> dict:
    with open(V3.SPEC, encoding="utf-8") as f:
        spec = json.load(f)
    V3.check_hashes(spec)
    names, thr = spec["variables"], spec["regla"]["umbral"]
    ms0 = to_ms(start)
    members = V3.load_members(spec, len(names))
    zser = dvol_z30(dvol_file)
    D = {}
    for sym in symbols:
        S, B, F, FU = C.build_symbol(data_dir, sym, use_fut=spec["usa_futuros"], t_end_ms=end_ms)
        arr = C.load_spot(data_dir, sym)
        bars = H.Bars(arr[arr[:, 0] < end_ms], sym)
        i0, i1 = H.bounds(bars, (ms0, end_ms), reason=reason, who="v3_shadow")
        X = np.stack([F[k] for k in names], 1).astype(np.float32)
        X[~np.isfinite(X)] = np.nan
        idx = np.arange(len(X))
        valid = (idx >= W.WARM) & np.isfinite(S["s15"]) & (S["s15"] > 0)
        ridx = np.flatnonzero(valid & (idx >= i0) & (idx < i1))
        Q = C.seq_channels(S, B, FU)[0]
        p = V3.predict(members, X, ridx, Q)
        sig = np.zeros(len(X), bool)
        sig[ridx] = p[ridx] >= thr
        D[sym] = dict(S=S, bars=bars, i0=i0, i1=i1, valid=valid, sig=sig, p=p, ridx=ridx,
                      missing=float(np.mean(F["metrics_missing"][ridx])) if len(ridx) else float("nan"),
                      z30=z_at_open(zser, S["t"]))
    # Compuerta A4, igual que nn_v3_desc.py: otras anclas con senal en las ultimas GATE_W velas (incluida la actual);
    # A18: lo mismo con las otras monedas del universo evaluado (S1)
    tg = np.unique(np.concatenate([D[s]["S"]["t"].astype(np.int64) for s in symbols]))
    roll = {}
    for s in symbols:
        g = np.zeros(len(tg))
        g[np.searchsorted(tg, D[s]["S"]["t"].astype(np.int64))] = D[s]["sig"]
        roll[s] = H.rolling_max(g, V3.GATE_W) > 0
    for s in symbols:
        rows = np.searchsorted(tg, D[s]["S"]["t"].astype(np.int64))
        D[s]["A"] = sum(roll[o][rows].astype(int) for o in ANCHORS if o != s and o in roll)
        D[s]["A18"] = sum(roll[o][rows].astype(int) for o in symbols if o != s)
        D[s]["veto"] = D[s]["z30"] < -1        # NaN no veta
    # Regimen (hipotesis 4.4): cierre de BTC > su media de 30 dias, alineado por open_time (sin BTC: no se calcula)
    if "BTCUSDT" in D:
        bt, bc = D["BTCUSDT"]["S"]["t"].astype(np.int64), D["BTCUSDT"]["S"]["c"]
        up = bc > H.rolling_mean(bc, REGIME_CANDLES)
        for s in symbols:
            j = np.searchsorted(bt, D[s]["S"]["t"].astype(np.int64))
            ok = (j < len(bt)) & (bt[np.minimum(j, len(bt) - 1)] == D[s]["S"]["t"].astype(np.int64))
            D[s]["btc_up"] = ok & up[np.minimum(j, len(bt) - 1)]
    anchors = [s for s in symbols if s in ANCHORS]
    arms = {"P1": (lambda d: d["sig"] & (d["A"] >= 1), anchors),
            "C0": (lambda d: d["sig"], anchors),
            "C0_A0": (lambda d: d["sig"] & (d["A"] == 0), anchors),
            "S3": (lambda d: d["sig"] & (d["A"] >= 1) & ~d["veto"], anchors)}
    if len(symbols) > len(anchors):
        arms["S1"] = (lambda d: d["sig"] & (d["A18"] >= S1_MIN), list(symbols))
    if "BTCUSDT" in D:
        arms["P1+R"] = (lambda d: d["sig"] & (d["A"] >= 1) & d["btc_up"], anchors)
        if "S1" in arms:
            arms["S1+R"] = (lambda d: d["sig"] & (d["A18"] >= S1_MIN) & d["btc_up"], list(symbols))
    return {"spec": spec, "D": D, "arms": arms, "thr": thr, "symbols": list(symbols)}


def tp_limit_net(net, why, exit_px, entry_px, slip):
    """Con el TP como orden limite, la salida por TP no paga deslizamiento: se le devuelve slip * salida/entrada."""
    net = np.array(net, float, copy=True)
    tp = np.asarray(why) == H.TP
    net[tp] += slip * np.asarray(exit_px, float)[tp] / np.asarray(entry_px, float)[tp]
    return net


def simulate_arms(ev: dict) -> dict:
    """Operaciones de cada brazo y costo, y el azar (todas las velas validas, y solo las de A4 >= 1) por moneda y mes."""
    D, arms = ev["D"], ev["arms"]
    ga, gm, gH = C.GEOMS["X5_384"]
    a_, m_, _ = C.GEOMS["X5_384"]
    out = {"trades": {}, "base": {}, "base_A": {}}
    for cost, (fee, slip, tp_limit) in COSTS.items():
        base, base_a = {}, {}
        for sym in D:
            d, S = D[sym], D[sym]["S"]
            netr, why, jx = C.label_all(S, "X5_384", d["i1"], fee=fee, slip=slip)
            if tp_limit:
                sd = S["s15"] * np.sqrt(96)
                netr = np.where(why == H.TP, netr + slip * (1 + a_ * sd), netr)
            mon = np.array([int(iso(x)[:7].replace("-", "")) for x in S["t"]])
            rr = np.zeros(len(S["t"]), bool)
            rr[d["i0"]:d["i1"]] = True
            okr = rr & d["valid"] & np.isfinite(netr)
            for mo in np.unique(mon[okr]):
                s_ = okr & (mon == mo)
                base[(sym, int(mo))] = (float(np.mean(netr[s_] > 0)), float(np.mean(netr[s_])))
                sa = s_ & (d["A"] >= 1)
                base_a[(sym, int(mo))] = ((float(np.mean(netr[sa] > 0)), float(np.mean(netr[sa]))) if sa.any()
                                          else base[(sym, int(mo))])
        out["base"][cost], out["base_A"][cost] = base, base_a
        for arm, (rule, coins) in arms.items():
            trs = []
            for sym in coins:
                d, S = D[sym], D[sym]["S"]
                sd = S["s15"] * np.sqrt(96)
                tp, sl = S["c"] * (1 + ga * sd), S["c"] * (1 - gm * sd)
                tr = H.simulate(d["bars"], rule(d), tp, sl, period=(d["i0"], d["i1"]), max_hold=gH, fee=fee, slip=slip)
                if tp_limit and len(tr):
                    tr.net_ret = tp_limit_net(tr.net_ret, tr.reason, tr.exit_px, tr.entry_px, slip)
                if len(tr):
                    trs.append((sym, tr))
            out["trades"][(arm, cost)] = trs
    return out


def criteria(sim: dict) -> dict:
    """Los criterios de la seccion 8.3 para P1 con lo que hay hasta hoy (no es la decision final: esa se toma al terminar
    la prueba) y la vigilancia por e-proceso."""
    main = arm_stats(sim["trades"][("P1", MAIN_COST)], sim["base"][MAIN_COST], "P1")
    stress = arm_stats(sim["trades"][("P1", "0.30 %")], sim["base"]["0.30 %"], "P1 0.30")
    cond = arm_stats(sim["trades"][("P1", MAIN_COST)], sim["base_A"][MAIN_COST], "P1 vs azar A4")
    out = {"n": main.get("n", 0), "abiertas": main.get("abiertas", 0)}
    if not main.get("n"):
        return out
    done = [t.subset(closed(t)) for _, t in sim["trades"][("P1", MAIN_COST)]]
    c0 = [t.subset(closed(t)) for _, t in sim["trades"][("C0_A0", MAIN_COST)]]
    cat = lambda ts, f: np.concatenate([getattr(t, f) for t in ts]) if ts else np.zeros(0)
    p_boot = boot_diff_days(cat(done, "net_ret"), cat(done, "entry_t") // DAY_MS, cat(c0, "net_ret"),
                            cat(c0, "entry_t") // DAY_MS)
    order = np.argsort(cat(done, "exit_t"), kind="stable")
    M = e_process((cat(done, "net_ret") > 0)[order])
    out.update({
        "1_E_pct": main["E_pct"], "1_t_dia": main["t_day"], "1_E_pct_0.30": stress.get("E_pct"),
        "1_cumple": bool(main["E_pct"] > 0 and main["t_day"] >= 1.645 and (stress.get("E_pct") or -1) > 0),
        "2_wr": main["wr"], "2_wilson": [main["wr_lo"], main["wr_hi"]],
        "2_nivel": next((lvl for lvl in (0.80, 0.75, 0.70) if main["wr_lo"] >= lvl), None),
        "3_dE_pct": main["dE_pct"], "3_t_dE_dia": main["t_dE_day"], "3_dWR": main["dWR"],
        "3_dE_pct_azar_A4": cond["dE_pct"], "3_dWR_azar_A4": cond["dWR"],
        "3_cumple": bool(main["dE_pct"] > 0 and main["t_dE_day"] >= 1.645 and main["dWR"] > 0),
        "4_P_boot_dias": p_boot, "4_cumple": bool(np.isfinite(p_boot) and p_boot <= 0.10),
        "5_episodios_positivos_pct": main["episodios_positivos_pct"], "5_episodios": main["episodios"],
        "5_cumple": bool(main["episodios_positivos_pct"] >= 60),
        "6_hashes": True,
        "e_proceso_M": M[-1] if M else 1.0, "e_proceso_rechaza_wr_70": bool(M and max(M) >= E_STOP),
        "futilidad": bool(main["n"] >= 200 and (main["wr_hi"] < P0)),
        "fin_por_operaciones": bool(main["n"] >= 400),
    })
    return out


def s3_veto(ev: dict) -> dict:
    """Senales de P1 vetadas por D1 y su resultado (el criterio de S3 se mira con >= 150 senales de P1)."""
    trs = []
    D = ev["D"]
    ga, gm, gH = C.GEOMS["X5_384"]
    for sym in [s for s in ANCHORS if s in D]:
        d, S = D[sym], D[sym]["S"]
        sd = S["s15"] * np.sqrt(96)
        tr = H.simulate(d["bars"], d["sig"] & (d["A"] >= 1) & d["veto"], S["c"] * (1 + ga * sd), S["c"] * (1 - gm * sd),
                        period=(d["i0"], d["i1"]), max_hold=gH)
        tr = tr.subset(closed(tr))
        if len(tr):
            trs.append(tr)
    net = np.concatenate([t.net_ret for t in trs]) if trs else np.zeros(0)
    et = np.concatenate([t.entry_t for t in trs]) if trs else np.zeros(0, np.int64)
    anchors = [D[s] for s in ANCHORS if s in D]
    sig_p1 = sum(int((d["sig"] & (d["A"] >= 1))[d["i0"]:d["i1"]].sum()) for d in anchors)
    z_missing = sum(int(np.isnan(d["z30"][d["i0"]:d["i1"]]).sum()) for d in anchors)
    return {"senales_P1": sig_p1, "vetadas_cerradas": int(len(net)),
            "wr_vetadas": float(np.mean(net > 0)) if len(net) else None, "episodios_vetados": len(episodes(et, net)),
            "velas_sin_dvol": z_missing}


# ------------------------------------------------------------------ salidas
def write_outputs(ev: dict, sim: dict, crit: dict, veto: dict, end_ms: int, limits: dict, out_dir: str, start: str,
                  provisional: dict = None):
    os.makedirs(out_dir, exist_ok=True)
    D = ev["D"]
    with open(os.path.join(out_dir, "senales.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["open_time_utc", "symbol", "p", "A4", "A18", "z30_dvol_btc", "P1", "C0", "S3", "S1"])
        for sym in D:
            d, anchor = D[sym], sym in ANCHORS
            for i in np.flatnonzero(d["sig"][d["i0"]:d["i1"]]) + d["i0"]:
                z = d["z30"][i]
                w.writerow([iso(d["S"]["t"][i]), sym, round(float(d["p"][i]), 5), int(d["A"][i]), int(d["A18"][i]),
                            "" if np.isnan(z) else round(float(z), 3), int(anchor and d["A"][i] >= 1), int(anchor),
                            int(anchor and d["A"][i] >= 1 and not d["veto"][i]),
                            int("S1" in ev["arms"] and d["A18"][i] >= S1_MIN)])
    for arm in [a for a in ("P1", "C0", "S3", "S1") if a in ev["arms"]]:
        with open(os.path.join(out_dir, f"operaciones_{arm}.csv"), "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(["symbol", "entrada_utc", "salida_utc", "precio_entrada", "precio_salida", "tp", "sl", "motivo",
                        "neto_pct", "r", "estado"])
            for sym, tr in sim["trades"][(arm, MAIN_COST)]:
                for k in range(len(tr)):
                    end_ = tr.reason[k] == H.END
                    w.writerow([sym, iso(tr.entry_t[k]), "" if end_ else iso(tr.exit_t[k]), tr.entry_px[k],
                                "" if end_ else tr.exit_px[k], tr.tp[k], tr.sl[k], H.REASONS[int(tr.reason[k])],
                                "" if end_ else round(100 * float(tr.net_ret[k]), 4),
                                "" if end_ else round(float(tr.r_mult[k]), 4), "abierta" if end_ else "cerrada"])
    arms = {}
    for (arm, cost), trs in sim["trades"].items():
        if arm != "C0_A0":
            arms[f"{arm} c={cost}"] = arm_stats(trs, sim["base"][cost], arm)
    per_coin = {arm: coin_table(sim["trades"][(arm, MAIN_COST)]) for arm in ("P1", "S1", "S1+R") if (arm, MAIN_COST) in sim["trades"]}
    res = {"generado": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "periodo": [start, iso(end_ms)], "umbral": ev["thr"], "spec": ev["spec"]["nombre"],
           "sha256": {"spec_nn_v2.json": sha(V3.SPEC), "run_daily.py": sha(os.path.abspath(__file__))},
           "preregistro": PREREGISTRO, "datos_hasta_por_serie": {k: iso(v) for k, v in limits.items()},
           "monedas": ev["symbols"], "metrics_faltantes_pct": {s: round(100 * D[s]["missing"], 2) for s in D},
           "criterios_P1": crit, "S3_vetadas": veto, "brazos": arms, "por_moneda": per_coin, "provisional": provisional}
    with open(os.path.join(out_dir, "resumen.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(res, f, ensure_ascii=False, indent=1, default=float)
    with open(os.path.join(out_dir, "resumen.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write(render_md(res))
    return res


def coin_table(trades: list) -> list:
    """PnL individual por moneda (operaciones cerradas, 15 USDT por operacion) y la fila combinada."""
    rows, allnet = [], []
    for sym, tr in trades:
        net = tr.net_ret[closed(tr)]
        if not len(net):
            continue
        allnet.append(net)
        rows.append({"symbol": sym, "n": int(len(net)), "wr": float(np.mean(net > 0)), "E_pct": float(100 * net.mean()),
                     "pnl_usdt": float(15 * net.sum())})
    rows.sort(key=lambda r: -r["pnl_usdt"])
    if allnet:
        net = np.concatenate(allnet)
        rows.append({"symbol": "COMBINADO", "n": int(len(net)), "wr": float(np.mean(net > 0)),
                     "E_pct": float(100 * net.mean()), "pnl_usdt": float(15 * net.sum()),
                     "monedas_ganadoras": sum(1 for r in rows if r["pnl_usdt"] > 0), "monedas": len(rows)})
    return rows


def _f(x, fmt="{:.2f}"):
    return "—" if x is None or (isinstance(x, float) and math.isnan(x)) else fmt.format(x)


def render_md(res: dict) -> str:
    c = res["criterios_P1"]
    prov = res.get("provisional")
    L = [f"# Canal sombra v3: prueba prospectiva{' (PROVISIONAL)' if prov else ''}\n",
         f"Periodo evaluado: **{res['periodo'][0]} a {res['periodo'][1]} UTC** (hasta donde todas las series estan "
         f"completas). Generado {res['generado']}. Umbral θ = {res['umbral']:.4f}. No es la decisión final: el "
         f"pre-registro termina el {PREREGISTRO['fin']}.\n",
         *([f"> **Provisional:** el funding desde el {prov['funding_reconstruido_desde']} UTC se reconstruyó con la prima "
            f"del perpetuo (Binance aún no publica el archivo del mes). Equivalencia con el funding real en "
            f"{prov['equivalencia']['ventana'][0]} a {prov['equivalencia']['ventana'][1]}: señales Jaccard "
            f"{prov['equivalencia']['senales']['jaccard']}, P1 Jaccard {prov['equivalencia']['P1']['jaccard']} "
            f"({'equivalente' if prov['equivalencia']['equivalente'] else 'NO equivalente: no fiarse de estas cifras'}). "
            f"Las cifras definitivas salen cuando se publique el funding real.\n"] if prov else []),
         "| Brazo | Costo | n | Abiertas | WR | Wilson 95 % | E % | t/día | ΔWR azar | ΔE azar % | Episodios + | Meses + |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for key, m in res["brazos"].items():
        arm, cost = key.split(" c=")
        if not m.get("n"):
            L.append(f"| {arm} | {cost} | 0 | {m.get('abiertas', 0)} | — | — | — | — | — | — | — | — |")
            continue
        L.append(f"| {arm} | {cost} | {m['n']} | {m['abiertas']} | {_f(100 * m['wr'], '{:.1f} %')} | "
                 f"[{_f(100 * m['wr_lo'], '{:.1f}')}, {_f(100 * m['wr_hi'], '{:.1f}')}] | {_f(m['E_pct'], '{:+.3f}')} | "
                 f"{_f(m['t_day'])} | {_f(100 * m['dWR'], '{:+.1f} pt')} | {_f(m['dE_pct'], '{:+.3f}')} | "
                 f"{_f(m['episodios_positivos_pct'], '{:.0f} %')} de {m['episodios']} | "
                 f"{m['meses_positivos'][0]}/{m['meses_positivos'][1]} |")
    L.append("\n## Criterios de P1 (sección 8.3), con lo que hay hasta hoy\n")
    if not c.get("n"):
        L.append(f"Sin operaciones cerradas de P1 todavía ({c.get('abiertas', 0)} abiertas).")
    else:
        L += [f"1. E {_f(c['1_E_pct'], '{:+.3f}')} %, t por día {_f(c['1_t_dia'])}; con 0.30 %: "
              f"{_f(c['1_E_pct_0.30'], '{:+.3f}')} %. {'Cumple' if c['1_cumple'] else 'No cumple'}.",
              f"2. WR {_f(100 * c['2_wr'], '{:.1f}')} %, Wilson [{_f(100 * c['2_wilson'][0], '{:.1f}')}, "
              f"{_f(100 * c['2_wilson'][1], '{:.1f}')}]. Nivel: {('aprueba ' + str(int(100 * c['2_nivel']))) if c['2_nivel'] else 'ninguno'}.",
              f"3. ΔE frente al azar {_f(c['3_dE_pct'], '{:+.3f}')} % (t {_f(c['3_t_dE_dia'])}), ΔWR "
              f"{_f(100 * c['3_dWR'], '{:+.1f}')} pt; frente al azar con A4 ≥ 1: ΔE {_f(c['3_dE_pct_azar_A4'], '{:+.3f}')} %, "
              f"ΔWR {_f(100 * c['3_dWR_azar_A4'], '{:+.1f}')} pt. {'Cumple' if c['3_cumple'] else 'No cumple'}.",
              f"4. P(E(P1) − E(C0 con A4 = 0) ≤ 0) = {_f(c['4_P_boot_dias'], '{:.3f}')} (bootstrap por días). "
              f"{'Cumple' if c['4_cumple'] else 'No cumple'}.",
              f"5. Episodios positivos {_f(c['5_episodios_positivos_pct'], '{:.0f}')} % de {c['5_episodios']}. "
              f"{'Cumple' if c['5_cumple'] else 'No cumple'}.",
              "6. Hashes intactos (se verifican antes de evaluar).",
              f"\nE-proceso del WR (p0 = 0.70): M = {_f(c['e_proceso_M'], '{:.3f}')}"
              f"{' (≥ 20: rechaza WR ≤ 70 %)' if c['e_proceso_rechaza_wr_70'] else ''}. "
              f"Futilidad: {'sí' if c['futilidad'] else 'no'}. 400 operaciones: {'sí' if c['fin_por_operaciones'] else 'no'}."]
    v = res["S3_vetadas"]
    L.append(f"\n**S3 (D1):** {v['senales_P1']} señales de P1, {v['vetadas_cerradas']} vetadas y cerradas "
             f"(WR {_f(None if v['wr_vetadas'] is None else 100 * v['wr_vetadas'], '{:.1f} %')}, "
             f"{v['episodios_vetados']} episodios); {v['velas_sin_dvol']} velas sin DVOL.")
    for arm, rows in (res.get("por_moneda") or {}).items():
        if not rows:
            continue
        L.append(f"\n## PnL por moneda: {arm} (0.24 %, 15 USDT por operación)\n")
        L.append("| Moneda | n | WR | E % | PnL USDT |")
        L.append("|---|---|---|---|---|")
        for r in rows:
            name = (f"**COMBINADO** ({r['monedas_ganadoras']}/{r['monedas']} ganan)" if r["symbol"] == "COMBINADO"
                    else r["symbol"])
            L.append(f"| {name} | {r['n']} | {100 * r['wr']:.1f} % | {r['E_pct']:+.3f} | {r['pnl_usdt']:+.2f} |")
    L.append("\n**Datos:** metrics faltantes por moneda (fase 1 pide ≤ 5 %): "
             + ", ".join(f"{s} {p} %" for s, p in res["metrics_faltantes_pct"].items()) + ".")
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", default=RESEARCH, help="carpeta con klines/ y futures/ (por defecto v3_research)")
    ap.add_argument("--start", default=PREREGISTRO["inicio"])
    ap.add_argument("--download", action="store_true", help="descarga antes los datos nuevos (VPN apagada)")
    ap.add_argument("--out", default=OUT_DIR)
    ap.add_argument("--reason", default=None, help="solo si el periodo toca el holdout (queda registrado)")
    ap.add_argument("--dvol", default=DVOL_FILE, help="archivo del DVOL de BTC (por defecto cache/deribit)")
    ap.add_argument("--end", default=None, help="fin exclusivo (AAAA-MM-DD); por defecto, hasta donde haya datos")
    ap.add_argument("--monedas", default=None, help="lista de monedas separadas por comas (incluir las 4 anclas para P1)")
    ap.add_argument("--solo-anclas", action="store_true", help="solo las 4 anclas (sin S1 ni las otras 14 monedas)")
    ap.add_argument("--solo-definitivo", action="store_true",
                    help="no reconstruye el funding del mes en curso: evalua solo hasta el ultimo funding real")
    a = ap.parse_args(argv)
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
    symbols = list(ANCHORS) if a.solo_anclas else (a.monedas.split(",") if a.monedas else UNIVERSE)
    if a.download:
        import feeds
        today = dt.datetime.now(dt.timezone.utc).date()
        since = dt.date.fromisoformat(a.start) - dt.timedelta(days=WARMUP_DAYS)
        print("[V3] Descargando velas spot:", feeds.update_spot(a.data_dir, symbols, since, today - dt.timedelta(days=1)))
        print("[V3] Descargando futuros:", feeds.update_futures(a.data_dir, symbols, since, today - dt.timedelta(days=1)))
        try:
            print("[V3] DVOL nuevo (horas):", feeds.update_dvol())
        except Exception as e:  # el DVOL solo afecta a S3; sin el, D1 no veta y se anota
            print(f"[V3] ⚠️ No se pudo actualizar el DVOL ({e}); S3 no vetara las velas sin dato.")
    cap = to_ms(a.end) if a.end else None
    end_ms, limits = data_end_ms(a.data_dir, symbols)
    provisional = None
    if cap is not None and cap <= end_ms:
        end_ms = cap                                # el corte pedido ya tiene datos completos: no hace falta reconstruir
    elif not a.solo_definitivo and min(limits, key=limits.get).endswith("funding"):
        # El funding (solo mensual) es lo que frena: se reconstruye con la prima, se mide su equivalencia y se avisa
        eq = equivalence(a.data_dir, a.out)
        print(f"[V3] Funding provisional: equivalencia en {eq['ventana'][0]} a {eq['ventana'][1]}: senales Jaccard "
              f"{eq['senales']['jaccard']}, P1 Jaccard {eq['P1']['jaccard']} "
              f"({'equivalente' if eq['equivalente'] else 'NO equivalente'}).")
        real_end = min(int(C.load_fut(a.data_dir, s)["funding"][:, 0].max()) for s in symbols)
        with ProxyFunding():
            end_ms, limits = data_end_ms(a.data_dir, symbols)
        end_ms = min(end_ms, cap) if cap else end_ms
        provisional = {"funding_reconstruido_desde": iso(real_end + FUNDING_MS), "equivalencia": eq}
    if end_ms <= to_ms(a.start):
        print(f"[V3] Aun no hay datos completos despues de {a.start} (corte {iso(end_ms)}): "
              + ", ".join(f"{k} {iso(v)}" for k, v in limits.items() if v == min(limits.values())))
        return None
    if provisional:
        with ProxyFunding():
            ev = evaluate(a.data_dir, a.start, end_ms, a.reason, dvol_file=a.dvol, symbols=symbols)
    else:
        ev = evaluate(a.data_dir, a.start, end_ms, a.reason, dvol_file=a.dvol, symbols=symbols)
    sim = simulate_arms(ev)
    res = write_outputs(ev, sim, criteria(sim), s3_veto(ev), end_ms, limits, a.out, a.start, provisional)
    print(render_md(res))
    print(f"[V3] Salida: {a.out}")
    return res


if __name__ == "__main__":
    main()
