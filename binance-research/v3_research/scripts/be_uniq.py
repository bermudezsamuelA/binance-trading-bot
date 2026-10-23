"""E11 - Ponderacion por UNICIDAD de la etiqueta (Lopez de Prado), con concurrencia ENTRE monedas, para LightGBM.
Mismo walk-forward, variables, etiqueta G3 e hiperparametros que lgbv4 (nn_wf.fit_lgb), 3 semillas, pero con
pesos u_i = media sobre t en (i, salida_i] de 1/c_t, donde c_t = etiquetas activas en t sumando las 4 monedas.
Compara ENS3-LGB ponderado frente a ENS3-LGB sin ponderar (lgbv4 s0-s2 ya guardados) con la salida X5 y la regla v2.
Las predicciones se guardan en output/bleeding_edge/preds/ (no toca tmp/nn_preds). DISENO.
"""
import os, sys, json, time
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "nn"))
import be_common as B
import nn_wf as W
H = B.H
C = B.C
PD = os.path.join(B.OUT, "preds")
os.makedirs(PD, exist_ok=True)


def uniqueness(pool):
    """Concurrencia sobre la malla temporal comun (open_time) sumando monedas."""
    tg = np.unique(np.concatenate([p["t"] for p in pool]).astype(np.int64))
    conc = np.zeros(len(tg) + 1)
    spans = []
    for p in pool:
        z = np.load(os.path.join(W.CACHE, f"{p['sym']}.npz"))
        jx = z["jx_G3"].astype(np.int64)
        t = p["t"].astype(np.int64)
        i = np.arange(len(t))
        ok = p["ok"] & (jx > i)
        a = np.searchsorted(tg, t[i[ok]] + C.MS15)           # primera vela del horizonte (i+1)
        b = np.searchsorted(tg, t[np.minimum(jx[ok], len(t) - 1)]) + 1
        np.add.at(conc, a, 1); np.add.at(conc, b, -1)
        spans.append((ok, a, b))
    c = np.cumsum(conc)[:-1]
    inv = np.where(c > 0, 1.0 / np.maximum(c, 1), 0.0)
    cs = np.concatenate([[0.0], np.cumsum(inv)])
    ws = []
    for p, (ok, a, b) in zip(pool, spans):
        w = np.zeros(len(p["t"]))
        w[ok] = (cs[b] - cs[a]) / np.maximum(b - a, 1)
        ws.append(w)
    return ws


def main():
    pool = W.load_pool("G3", True)
    ws = uniqueness(pool)
    wall = np.concatenate(ws)
    ci = np.concatenate([np.full(len(p["net"]), p["ci"]) for p in pool])
    ii = np.concatenate([np.arange(len(p["net"])) for p in pool])
    X = np.concatenate([p["X"] for p in pool]).astype(np.float32)
    net = np.concatenate([p["net"] for p in pool])
    t = np.concatenate([p["t"] for p in pool]).astype(np.int64)
    ok = np.concatenate([p["ok"] for p in pool])
    y = (net > 0).astype(np.float32)
    print("peso medio", wall[ok].mean(), "mediana", np.median(wall[ok]), flush=True)
    import lightgbm as lgb
    for seed in range(3):
        tag = f"lgbuniq_G3_f1_s{seed}"
        res = {"names": np.array(pool[0]["names"])}
        for k, (te0, te1) in enumerate(W.TESTS):
            T0, T1 = W.ms(*te0), W.ms(*te1)
            V0 = W.ms(*W.add_months(*te0, -3))
            purge = (193) * C.MS15
            fit = ok & (t < V0 - purge); val = ok & (t >= V0) & (t < T0 - purge); tst = ok & (t >= T0) & (t < T1)
            params = dict(objective="binary", learning_rate=0.03, num_leaves=15, min_data_in_leaf=1000,
                          feature_fraction=0.7, bagging_fraction=0.5, bagging_freq=1, lambda_l2=10.0, max_bin=63,
                          num_threads=6, verbose=-1, seed=seed + k, metric="auc")
            wf = wall[fit] / wall[fit].mean()
            dtr = lgb.Dataset(X[fit], y[fit], weight=wf)
            dva = lgb.Dataset(X[val], y[val], reference=dtr)
            m = lgb.train(params, dtr, num_boost_round=1500, valid_sets=[dva],
                          callbacks=[lgb.early_stopping(150, verbose=False)])
            it = max(m.best_iteration, 50)
            res[f"f{k}_val_rows"] = np.flatnonzero(val); res[f"f{k}_val_s"] = m.predict(X[val], raw_score=True, num_iteration=it).astype(np.float32)
            res[f"f{k}_tst_rows"] = np.flatnonzero(tst); res[f"f{k}_tst_s"] = m.predict(X[tst], raw_score=True, num_iteration=it).astype(np.float32)
            print(tag, k, it, flush=True)
        res.update(ci=ci, ii=ii, t=t, net=net)
        np.savez(os.path.join(PD, f"{tag}.npz"), **res)
    lines = ["# E11 ponderacion por unicidad (LightGBM x3 semillas, diseno, salida X5, regla v2)\n"] + list(B.MD_HEAD)
    out = {}
    for lab, tags in (("LGB x3 sin ponderar (lgbv4 s0-s2)", [f"lgbv4_G3_f1_s{k}" for k in range(3)]),
                      ("LGB x3 ponderado por unicidad", [f"lgbuniq_G3_f1_s{k}" for k in range(3)])):
        D = B.load_ens(tags, pred_dirs=[PD])
        T, s = B.simulate_entries(D, D["p"] >= D["thr"])
        r = B.summarize_trades(T, s, D, label=lab)
        # brecha validacion-prueba: WR de validacion en el umbral elegido vs WR realizado
        gaps = []
        for k in range(6):
            Vk = D["vals"][k]
            if np.isfinite(Vk["thr"]):
                sv = Vk["p"] >= Vk["thr"]
                st = (D["fold"] == k) & (D["p"] >= D["thr"]) & np.isfinite(D["netX"])
                if st.any():
                    gaps.append(np.mean(Vk["netX"][sv] > 0) - np.mean(D["netX"][st] > 0))
        r["val_test_gap_pt"] = float(np.mean(gaps) * 100) if gaps else None
        lines.append(B.md_row(r) + f" brecha val−prueba (WR por vela): {r['val_test_gap_pt']:+.1f} pt")
        print(B.fmt(r), r["val_test_gap_pt"]); out[lab] = r
    B.log_once("uniq", 1, "E11 LightGBM ponderado por unicidad entre monedas, 3 semillas (diseno)")
    with open(os.path.join(B.OUT, "be_uniq.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    with open(os.path.join(B.OUT, "be_uniq.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, default=float, indent=1)


if __name__ == "__main__":
    main()
