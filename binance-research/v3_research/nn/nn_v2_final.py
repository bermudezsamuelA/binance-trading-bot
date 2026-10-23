"""v2: entrena el candidato CONGELADO v2 con la receta del walk-forward aplicada una vez mas.
Modelos entrenados con la etiqueta G3 (como en la v1); se opera con la geometria de salida v2 y el umbral se elige
SOLO en la validacion 2025-04..2025-06 con las etiquetas de esa geometria (max E sujeto a WR_val >= wr_min).

Uso: python -I nn_v2_final.py --members lgb:0,...,mlp:5[,cnn:0] --exit X5 --wrmin 0.75
     python -I nn_v2_final.py --rehash
"""
import argparse, hashlib, json, os, sys, datetime as dt
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nn_common as C
import nn_wf as W
import nn_report as R
import nn_v2_report as V
H = C.H

MODELS = os.path.join(C.HERE, "models_v2")
OUTD = os.path.join(C.RESEARCH, "output", "constructor")
SPEC = os.path.join(OUTD, "spec_nn_v2.json")
SCRIPTS = ("nn_common.py", "nn_wf.py", "nn_report.py", "nn_v2_report.py", "nn_v2_final.py", "nn_v2_eval.py",
           "nn_download_futures.py")


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def script_hashes():
    out = {f: sha(os.path.join(C.HERE, f)) for f in SCRIPTS if os.path.exists(os.path.join(C.HERE, f))}
    out["harness.py"] = sha(os.path.join(C.RESEARCH, "scripts", "harness.py"))
    return out


def main():
    if "--rehash" in sys.argv:
        spec = json.load(open(SPEC, encoding="utf-8"))
        spec["sha256_scripts"] = script_hashes()
        json.dump(spec, open(SPEC, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("hashes actualizados"); return
    ap = argparse.ArgumentParser()
    ap.add_argument("--members", required=True)
    ap.add_argument("--exit", required=True)
    ap.add_argument("--wrmin", type=float, default=0.75)
    a = ap.parse_args()
    os.makedirs(MODELS, exist_ok=True)
    LG = "G3"; Hh = C.GEOMS[LG][2]
    pool = W.load_pool(LG, True)
    names = pool[0]["names"]
    ci = np.concatenate([np.full(len(p["net"]), p["ci"]) for p in pool])
    ii = np.concatenate([np.arange(len(p["net"])) for p in pool])
    X = np.concatenate([p["X"] for p in pool]).astype(np.float32)
    net = np.concatenate([p["net"] for p in pool])
    t = np.concatenate([p["t"] for p in pool]).astype(np.int64)
    ok = np.concatenate([p["ok"] for p in pool])
    y = (net > 0).astype(np.float32)
    cache = V.load_cache(a.exit)
    netX = np.concatenate([cache[s][f"net_{a.exit}"] for s in H.SYMBOLS])
    T0 = W.ms(2025, 7); V0 = W.ms(2025, 4)
    purge = (max(Hh, C.GEOMS[a.exit][2]) + 1) * C.MS15
    fit = np.flatnonzero(ok & (t < V0 - (Hh + 1) * C.MS15))
    val = np.flatnonzero(ok & (t >= V0) & (t < T0 - purge) & np.isfinite(netX))
    seq = W.SeqGetter(pool)
    members, pv = [], np.zeros(len(val))
    mlist = [m.split(":") for m in a.members.split(",")]
    for kind, seed in mlist:
        seed = int(seed)
        tag = f"{kind}_{LG}_s{seed}"
        if kind == "lgb":
            m, it = W.fit_lgb(X[fit], y[fit], X[val], y[val], seed + 6)
            path = os.path.join(MODELS, f"{tag}.txt")
            m.save_model(path, num_iteration=it)
            import lightgbm as lgb
            sv = lgb.Booster(model_file=path).predict(X[val], raw_score=True)
            info = {"kind": kind, "seed": seed, "file": os.path.basename(path), "iterations": int(it)}
            files = [path]
        else:
            import torch
            f_idx = fit if kind == "mlp" else fit[(ii[fit] % 4) == 0]
            mu, sd = W.standardize_fit(X[f_idx])
            Zf, Zv = W.standardize(X[f_idx], mu, sd), W.standardize(X[val], mu, sd)
            model, predict, ep = W.fit_torch(kind, Zf, y[f_idx], ci[f_idx], ii[f_idx], Zv, y[val], ci[val], ii[val],
                                             seq if kind == "cnn" else None, seed + 6)
            path = os.path.join(MODELS, f"{tag}.pt"); torch.save(model.state_dict(), path)
            spath = os.path.join(MODELS, f"{tag}_scaler.npz"); np.savez(spath, mu=mu, sd=sd)
            sv = predict(Zv, ci[val], ii[val])
            info = {"kind": kind, "seed": seed, "file": os.path.basename(path), "scaler": os.path.basename(spath),
                    "epochs": int(ep)}
            files = [path, spath]
        ab = R.platt_fit(sv, y[val])
        pv += R.platt_apply(sv, ab) / len(mlist)
        info.update(platt=[float(ab[0]), float(ab[1])], auc_val=float(W.auc_score(sv, y[val])),
                    sha256={os.path.basename(f): sha(f) for f in files})
        members.append(info)
        print({k: info[k] for k in ("kind", "seed", "auc_val")}, flush=True)
    V.OBJ["v"] = "E"
    ch = V.choose(pv, netX[val], t[val] // 86_400_000, a.wrmin)
    print("umbral elegido en validacion 2025Q2:", ch)
    ga, gm, gH = C.GEOMS[a.exit]
    spec = {
        "nombre": f"NN-meta v2: ensamble {len(mlist)} modelos (etiqueta G3) operado con salida {a.exit}",
        "creado_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), "agente": "constructor",
        "etiqueta_entrenamiento": {"id": LG, "a_m_H": list(C.GEOMS[LG]), "clase": "neto > 0 con costos 0.24 %"},
        "geometria_salida": {"id": a.exit, "tp": f"c*(1+{ga}*sd)", "sl": f"c*(1-{gm}*sd)", "max_hold_velas": gH,
                             "b": ga / gm, "sd": "std(log-ret 15m, 672 velas, ddof=1) * sqrt(96)",
                             "entrada": "cierre de la vela; barreras desde la siguiente; empate TP/SL = SL; hueco = apertura",
                             "una_posicion_por_moneda": True, "costos": 0.0024, "estres": 0.0030},
        "variables": names, "usa_futuros": True,
        "alineacion_metrics": "create_time T se conoce en T+5m; se usa T <= t_i + 5 min; relleno <= 30 min por columna",
        "entrenamiento": {"ajuste": f"[2023-01-01 + 800 velas, 2025-04-01 - {Hh + 1} velas)",
                          "validacion": f"[2025-04-01, 2025-07-01 - {max(Hh, gH) + 1} velas)",
                          "n_ajuste": int(len(fit)), "n_validacion": int(len(val)),
                          "hiperparametros": "identicos a la v1 (spec_nn.json); CNN: 96 velas x 10 canales, 4 conv dilatadas de 24 filtros, 1 de cada 4 velas"},
        "calibracion": "Platt por miembro con la etiqueta G3 en validacion; p = media de las probabilidades calibradas",
        "regla": {"descripcion": f"comprar al cierre si p >= umbral; umbral = cuantil de p en validacion que maximiza E (salida {a.exit}) con WR_val >= {a.wrmin}, >=150 velas, >=15 dias",
                  "wr_min": a.wrmin, "umbral": None if ch is None else float(ch[0]),
                  "cuantil_val": None if ch is None else float(ch[4]), "wr_val": None if ch is None else float(ch[1]),
                  "E_val": None if ch is None else float(ch[2]), "n_val_velas": None if ch is None else int(ch[3])},
        "miembros": members, "sha256_scripts": script_hashes(),
        "como_evaluar": "python -I nn/nn_v2_eval.py --symbols S1,S2 --start AAAA-MM-DD --end AAAA-MM-DD --data-dir <dir> [--reason ...]; "
                        "datos: <dir>/klines/{SYM,BTCUSDT}_15m.npy y <dir>/futures/{SYM}_*.npy (nn_download_futures.py) desde >= 35 dias antes de --start",
    }
    json.dump(spec, open(SPEC, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("spec v2 escrita")


if __name__ == "__main__":
    main()
