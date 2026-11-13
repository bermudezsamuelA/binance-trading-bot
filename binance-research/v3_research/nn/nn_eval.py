"""Evaluacion del candidato CONGELADO (spec_nn.json) sobre cualquier moneda y periodo. Sin parametros libres.

Uso:
  python -I nn_eval.py --symbols XRPUSDT,BNBUSDT --start 2025-07-01 --end 2026-10-01 --data-dir <dir> \
      [--reason "prueba final del Verificador"] [--out <carpeta>]

<dir> debe contener klines/{SYM}_15m.npy y klines/BTCUSDT_15m.npy (o en la raiz) y futures/{SYM}_{metrics,funding,
premium15m,fut15m}.npy (nn_download_futures.py), con >= 35 dias de datos antes de --start (calentamiento).
Senales solo en [start, end); las salidas nunca usan velas >= end (cierre END). Una posicion por moneda.
Comparacion contra el azar: todas las velas validas de la misma moneda y mes, con la misma geometria.
"""
import argparse, datetime as dt, hashlib, json, os, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import nn_common as C
import nn_wf as W
import nn_report as R
H = C.H
SPEC = os.path.join(C.RESEARCH, "output", "constructor", "spec_nn.json")
MODELS = os.path.join(HERE, "models")


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def to_ms(s):
    return int(dt.datetime.fromisoformat(s).replace(tzinfo=dt.timezone.utc).timestamp() * 1000)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", required=True)
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True, help="exclusivo")
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--reason", default=None, help="obligatorio si el rango toca el holdout 2025-07-01..2026-10-01")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    spec = json.load(open(SPEC, encoding="utf-8"))
    # verificacion de hashes
    bad = []
    for f, hv in spec["sha256_scripts"].items():
        p = os.path.join(C.RESEARCH, "scripts", f) if f == "harness.py" else os.path.join(HERE, f)
        if f != "nn_eval.py" and (not os.path.exists(p) or sha(p) != hv):
            bad.append(f)
    if sha(os.path.abspath(__file__)) != spec["sha256_scripts"].get("nn_eval.py"):
        bad.append("nn_eval.py")
    for m in spec["miembros"]:
        for f, hv in m["sha256"].items():
            if sha(os.path.join(MODELS, f)) != hv:
                bad.append(f)
    if bad:
        raise SystemExit(f"HASH DISTINTO: {bad}")
    import lightgbm as lgb
    import torch
    g = spec["geometria"]["id"]
    ga, gm, gH = C.GEOMS[g]
    names = spec["variables"]
    thr = spec["regla"]["umbral"]
    ms0, ms1 = to_ms(a.start), to_ms(a.end)
    members = []
    for m in spec["miembros"]:
        if m["kind"] == "lgb":
            members.append(("lgb", lgb.Booster(model_file=os.path.join(MODELS, m["file"])), None, m["platt"]))
        else:
            sc = np.load(os.path.join(MODELS, m["scaler"]))
            net_ = W.torch_model(m["kind"], len(names), 0)
            net_.load_state_dict(torch.load(os.path.join(MODELS, m["file"])))
            net_.eval()
            members.append((m["kind"], net_, (sc["mu"], sc["sd"]), m["platt"]))
    out_dir = a.out or os.path.join(C.RESEARCH, "output", "constructor",
                                    "eval_" + dt.datetime.now().strftime("%Y%m%d_%H%M%S"))
    os.makedirs(out_dir, exist_ok=True)
    all_tr, all_tr_s, base, rows = [], [], {}, []
    for sym in a.symbols.split(","):
        S, B, F, FU = C.build_symbol(a.data_dir, sym, use_fut=spec["usa_futuros"], t_end_ms=ms1)
        arr = C.load_spot(a.data_dir, sym)
        arr = arr[arr[:, 0] < ms1]
        bars = H.Bars(arr, sym)
        i0, i1 = H.bounds(bars, (ms0, ms1), reason=a.reason, who="nn_eval")
        X = np.stack([F[k] for k in names], 1).astype(np.float32)
        X[~np.isfinite(X)] = np.nan
        p = np.zeros(len(X))
        for kind, mod, sc, ab in members:
            if kind == "lgb":
                s = mod.predict(X, raw_score=True)
            else:
                Z = torch.from_numpy(W.standardize(X, sc[0], sc[1]))
                with torch.no_grad():
                    s = mod(Z).numpy()
            p += R.platt_apply(s, ab) / len(members)
        idx = np.arange(len(X))
        valid = (idx >= W.WARM) & np.isfinite(S["s15"]) & (S["s15"] > 0)
        ent = valid & (p >= thr) if thr is not None else np.zeros(len(X), bool)
        sd = S["s15"] * np.sqrt(96)
        tp, sl = S["c"] * (1 + ga * sd), S["c"] * (1 - gm * sd)
        tr = H.simulate(bars, ent, tp, sl, period=(i0, i1), max_hold=gH)
        tr_s = H.simulate(bars, ent, tp, sl, period=(i0, i1), max_hold=gH, fee=0.0013, slip=0.0002)
        # azar: todas las velas validas del mes (misma moneda y geometria), salidas dentro de [i0, i1)
        netr, _, _ = C.label_all(S, g, i1)
        mon = np.array([int(dt.datetime.fromtimestamp(x / 1000, dt.timezone.utc).strftime("%Y%m")) for x in S["t"]])
        rr = np.zeros(len(X), bool); rr[i0:i1] = True
        okr = rr & valid & np.isfinite(netr)
        for mo in np.unique(mon[okr]):
            s_ = okr & (mon == mo)
            base[(sym, int(mo))] = (float(np.mean(netr[s_] > 0)), float(np.mean(netr[s_])))
        if len(tr):
            all_tr.append((sym, tr)); all_tr_s.append((sym, tr_s))
            tr.to_csv(os.path.join(out_dir, f"trades_{sym}.csv"))
        n_years = (ms1 - max(ms0, int(S["t"][W.WARM]))) / (365.25 * 86400e3)
        rows.append({"symbol": sym, "n": len(tr), "trades_per_year": len(tr) / n_years if n_years > 0 else None,
                     "frac_velas_senal": float(ent[i0:i1].mean()),
                     "wr": float(np.mean(tr.net_ret > 0)) if len(tr) else None,
                     "E_pct": float(np.mean(tr.net_ret) * 100) if len(tr) else None})
        print(rows[-1], flush=True)
    res = {"spec": spec["nombre"], "symbols": a.symbols, "start": a.start, "end": a.end, "por_moneda": rows}
    if all_tr:
        m, T, syms = R.summarize(all_tr, base, 1, "candidato c=0.24%")
        ms_, _, _ = R.summarize(all_tr_s, base, 1, "candidato c=0.30%")
        res["total"] = m; res["estres_030"] = ms_
        print(R.fmt(m)); print(R.fmt(ms_))
    else:
        print("sin operaciones")
    with open(os.path.join(out_dir, "metrics.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1, default=float)
    print("salida:", out_dir)


if __name__ == "__main__":
    main()
