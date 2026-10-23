"""Entrena el candidato CONGELADO con la misma receta del walk-forward, aplicada una vez mas:
ajuste = todo el DISENO hasta 2025-04-01 (menos purga), validacion = 2025-04..2025-06 (menos purga).
Platt por miembro y umbral elegidos SOLO en esa validacion. Guarda modelos en nn/models y escribe spec_nn.json.

Uso: python -I nn_final.py --members lgb:0,lgb:1,lgb:2,mlp:0,mlp:1,mlp:2 --geom G3 --fut 1
"""
import argparse, hashlib, json, os, sys, datetime as dt
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nn_common as C
import nn_wf as W
import nn_report as R
H = C.H

MODELS = os.path.join(C.HERE, "models")
OUTD = os.path.join(C.RESEARCH, "output", "constructor")


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def script_hashes():
    return {os.path.basename(p): sha(p) for p in [os.path.join(C.HERE, f) for f in
            ("nn_common.py", "nn_wf.py", "nn_report.py", "nn_final.py", "nn_eval.py", "nn_download_futures.py")]
            + [os.path.join(C.RESEARCH, "scripts", "harness.py")] if os.path.exists(p)}


def rehash():
    """Actualiza solo los hashes de los scripts en spec_nn.json (los modelos y el umbral no cambian)."""
    path = os.path.join(OUTD, "spec_nn.json")
    spec = json.load(open(path, encoding="utf-8"))
    spec["sha256_scripts"] = script_hashes()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(spec, f, ensure_ascii=False, indent=1)
    print("hashes actualizados")


def main():
    if "--rehash" in sys.argv:
        return rehash()
    ap = argparse.ArgumentParser()
    ap.add_argument("--members", required=True)
    ap.add_argument("--geom", required=True)
    ap.add_argument("--fut", type=int, default=1)
    ap.add_argument("--rule", default="wr70")
    a = ap.parse_args()
    os.makedirs(MODELS, exist_ok=True)
    Hh = C.GEOMS[a.geom][2]
    pool = W.load_pool(a.geom, bool(a.fut))
    names = pool[0]["names"]
    ci = np.concatenate([np.full(len(p["net"]), p["ci"]) for p in pool])
    ii = np.concatenate([np.arange(len(p["net"])) for p in pool])
    X = np.concatenate([p["X"] for p in pool]).astype(np.float32)
    net = np.concatenate([p["net"] for p in pool])
    t = np.concatenate([p["t"] for p in pool]).astype(np.int64)
    ok = np.concatenate([p["ok"] for p in pool])
    y = (net > 0).astype(np.float32)
    T0 = W.ms(2025, 7); V0 = W.ms(2025, 4)
    purge = (Hh + 1) * C.MS15
    fit = np.flatnonzero(ok & (t < V0 - purge))
    val = np.flatnonzero(ok & (t >= V0) & (t < T0 - purge))
    members = []
    pv = np.zeros(len(val))
    mlist = [m.split(":") for m in a.members.split(",")]
    for kind, seed in mlist:
        seed = int(seed)
        tag = f"{kind}_{a.geom}_f{a.fut}_s{seed}"
        if kind == "lgb":
            m, it = W.fit_lgb(X[fit], y[fit], X[val], y[val], seed + 6)   # semilla = la del pliegue siguiente (k=6)
            path = os.path.join(MODELS, f"{tag}.txt")
            m.save_model(path, num_iteration=it)
            import lightgbm as lgb
            m2 = lgb.Booster(model_file=path)
            sv = m2.predict(X[val], raw_score=True)
            info = {"kind": kind, "seed": seed, "file": os.path.basename(path), "iterations": int(it)}
            files = [path]
        else:
            import torch
            mu, sd = W.standardize_fit(X[fit])
            Zf, Zv = W.standardize(X[fit], mu, sd), W.standardize(X[val], mu, sd)
            model, predict, ep = W.fit_torch(kind, Zf, y[fit], ci[fit], ii[fit], Zv, y[val], ci[val], ii[val],
                                             None, seed + 6)
            path = os.path.join(MODELS, f"{tag}.pt")
            torch.save(model.state_dict(), path)
            spath = os.path.join(MODELS, f"{tag}_scaler.npz")
            np.savez(spath, mu=mu, sd=sd)
            sv = predict(Zv, ci[val], ii[val])
            info = {"kind": kind, "seed": seed, "file": os.path.basename(path), "scaler": os.path.basename(spath),
                    "epochs": int(ep)}
            files = [path, spath]
        ab = R.platt_fit(sv, y[val])
        pv += R.platt_apply(sv, ab) / len(mlist)
        info["platt"] = [float(ab[0]), float(ab[1])]
        info["sha256"] = {os.path.basename(f): sha(f) for f in files}
        info["auc_val"] = float(W.auc_score(sv, y[val]))
        members.append(info)
        print(info, flush=True)
    ch = R.choose_threshold(pv, net[val], a.rule, day=t[val] // 86_400_000)
    print("umbral elegido en validacion 2025Q2:", ch)
    scripts = script_hashes()
    ga, gm, gH = C.GEOMS[a.geom]
    spec = {
        "nombre": f"NN-meta {a.geom} ensamble {'+'.join(k for k, _ in mlist)} {'con' if a.fut else 'sin'} futuros",
        "creado_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "agente": "constructor",
        "geometria": {"id": a.geom, "tp": f"c*(1+{ga}*sd)", "sl": f"c*(1-{gm}*sd)", "max_hold_velas": gH,
                      "sd": "std(log-ret 15m, 672 velas, ddof=1) * sqrt(96)", "b": ga / gm,
                      "entrada": "cierre de la vela de senal; barreras desde la vela siguiente; empate TP/SL = SL; hueco = apertura",
                      "una_posicion_por_moneda": True, "costos_ida_vuelta": 0.0024, "estres": 0.0030},
        "variables": names, "usa_futuros": bool(a.fut),
        "datos_necesarios": {
            "spot": "klines/{SYM}_15m.npy y klines/BTCUSDT_15m.npy (N x 7: open_time_ms, o, h, l, c, v, taker_buy_base), "
                    "formato de scripts/download_klines.py; desde >= 35 dias antes de --start",
            "futuros": "futures/{SYM}_metrics.npy, _funding.npy, _premium15m.npy, _fut15m.npy generados por "
                       "nn/nn_download_futures.py --symbols SYM --start (inicio-35 dias) --end (fin) --out <data-dir>/futures"},
        "alineacion_metrics": "create_time T se conoce en T+5m; se usa T <= t_i + 5 min (vela i abre en t_i); relleno hacia adelante <= 30 min por columna",
        "entrenamiento": {"ajuste": f"[2023-01-01 + 800 velas, 2025-04-01 - {Hh + 1} velas)", "validacion": f"[2025-04-01, 2025-07-01 - {Hh + 1} velas)",
                          "n_ajuste": int(len(fit)), "n_validacion": int(len(val)),
                          "etiqueta": "neto > 0 con la geometria (triple barrera, costos 0.24 %)",
                          "lgb": "binary, lr 0.03, 15 hojas, min_data_in_leaf 1000, feature_fraction 0.7, bagging 0.5, l2 10, max_bin 63, parada por AUC val (150), min 50 arboles",
                          "mlp": "74->128->64->1 GELU, dropout 0.3, AdamW lr 5e-4 wd 1e-3, lote 512, parada por AUC val (paciencia 3, max 12 epocas); estandarizacion con media/desv del ajuste, NaN->0, recorte +-5"},
        "calibracion": "Platt por miembro en validacion; p = media de probabilidades calibradas",
        "regla": {"tipo": a.rule, "descripcion": "comprar al cierre si p >= umbral (umbral = cuantil de p en validacion que maximiza E con WR>=0.70, >=150 velas y >=15 dias)",
                  "umbral": None if ch is None else float(ch[0]), "cuantil_val": None if ch is None else float(ch[4]),
                  "wr_val": None if ch is None else float(ch[1]), "E_val": None if ch is None else float(ch[2]),
                  "n_val_velas": None if ch is None else int(ch[3])},
        "miembros": members,
        "sha256_scripts": scripts,
    }
    os.makedirs(OUTD, exist_ok=True)
    with open(os.path.join(OUTD, "spec_nn.json"), "w", encoding="utf-8") as f:
        json.dump(spec, f, ensure_ascii=False, indent=1)
    print("spec escrita")


if __name__ == "__main__":
    main()
