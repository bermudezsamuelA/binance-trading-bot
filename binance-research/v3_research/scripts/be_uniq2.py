"""E11b - Replica de la ponderacion por unicidad: LightGBM con otras 3 semillas (s3-s5) y MLP con 6 semillas
(perdida BCE ponderada), mismo walk-forward e hiperparametros que lgbv4/mlpv4. Compara, con salida X5 y regla v2:
  LGB x3 (s3-s5) sin / con pesos; ENS6 (LGB s0-2 + MLP s0-2) sin / con pesos; ENS12 (6 + 6) sin / con pesos.
Predicciones en output/bleeding_edge/preds/. DISENO."""
import os, sys, json
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "nn"))
import be_common as B
import be_uniq as U
import nn_wf as W
H = B.H
C = B.C
PD = U.PD


def fit_torch_w(Xf, yf, wf, Xv, yv, seed, max_epochs=12, patience=3, bs=512):
    import torch
    torch.manual_seed(seed); np.random.seed(seed); torch.set_num_threads(6)
    model = W.torch_model("mlp", Xf.shape[1], 0)
    opt = torch.optim.AdamW(model.parameters(), lr=5e-4, weight_decay=1e-3)
    lossf = torch.nn.BCEWithLogitsLoss(reduction="none")

    def predict(X):
        model.eval(); out = []
        with torch.no_grad():
            for k in range(0, len(X), 4096):
                out.append(model(torch.from_numpy(X[k:k + 4096])).numpy())
        return np.concatenate(out)
    best, best_state, bad = np.inf, None, 0
    for ep in range(max_epochs):
        model.train()
        order = np.random.permutation(len(yf))
        for k in range(0, len(yf), bs):
            b = order[k:k + bs]
            xt = torch.from_numpy(Xf[b]); yb = torch.from_numpy(yf[b]); wb = torch.from_numpy(wf[b].astype(np.float32))
            opt.zero_grad(); loss = (lossf(model(xt), yb) * wb).sum() / wb.sum(); loss.backward(); opt.step()
        vl = -W.auc_score(predict(Xv), yv)
        if vl < best - 1e-4:
            best, bad = vl, 0
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
        else:
            bad += 1
            if bad >= patience:
                break
    model.load_state_dict(best_state)
    return predict


def main():
    pool = W.load_pool("G3", True)
    ws = U.uniqueness(pool)
    wall = np.concatenate(ws)
    ci = np.concatenate([np.full(len(p["net"]), p["ci"]) for p in pool])
    ii = np.concatenate([np.arange(len(p["net"])) for p in pool])
    X = np.concatenate([p["X"] for p in pool]).astype(np.float32)
    net = np.concatenate([p["net"] for p in pool])
    t = np.concatenate([p["t"] for p in pool]).astype(np.int64)
    ok = np.concatenate([p["ok"] for p in pool])
    y = (net > 0).astype(np.float32)
    import lightgbm as lgb
    jobs = [("lgb", s) for s in (3, 4, 5)] + [("mlp", s) for s in range(6)]
    for kind, seed in jobs:
        tag = f"{kind}uniq_G3_f1_s{seed}"
        if os.path.exists(os.path.join(PD, f"{tag}.npz")):
            continue
        res = {"names": np.array(pool[0]["names"])}
        for k, (te0, te1) in enumerate(W.TESTS):
            T0, T1 = W.ms(*te0), W.ms(*te1)
            V0 = W.ms(*W.add_months(*te0, -3))
            purge = 193 * C.MS15
            fit = ok & (t < V0 - purge); val = ok & (t >= V0) & (t < T0 - purge); tst = ok & (t >= T0) & (t < T1)
            wf = wall[fit] / wall[fit].mean()
            if kind == "lgb":
                params = dict(objective="binary", learning_rate=0.03, num_leaves=15, min_data_in_leaf=1000,
                              feature_fraction=0.7, bagging_fraction=0.5, bagging_freq=1, lambda_l2=10.0, max_bin=63,
                              num_threads=6, verbose=-1, seed=seed + k, metric="auc")
                dtr = lgb.Dataset(X[fit], y[fit], weight=wf); dva = lgb.Dataset(X[val], y[val], reference=dtr)
                m = lgb.train(params, dtr, num_boost_round=1500, valid_sets=[dva],
                              callbacks=[lgb.early_stopping(150, verbose=False)])
                it = max(m.best_iteration, 50)
                sv = m.predict(X[val], raw_score=True, num_iteration=it); st = m.predict(X[tst], raw_score=True, num_iteration=it)
            else:
                mu, sd = W.standardize_fit(X[fit])
                Zf, Zv, Zt = W.standardize(X[fit], mu, sd), W.standardize(X[val], mu, sd), W.standardize(X[tst], mu, sd)
                pred = fit_torch_w(Zf, y[fit], wf, Zv, y[val], seed + k)
                sv, st = pred(Zv), pred(Zt)
            res[f"f{k}_val_rows"] = np.flatnonzero(val); res[f"f{k}_val_s"] = np.asarray(sv, np.float32)
            res[f"f{k}_tst_rows"] = np.flatnonzero(tst); res[f"f{k}_tst_s"] = np.asarray(st, np.float32)
            print(tag, k, flush=True)
        res.update(ci=ci, ii=ii, t=t, net=net)
        np.savez(os.path.join(PD, f"{tag}.npz"), **res)
    lines = ["# E11b replica de la ponderacion por unicidad (diseno, salida X5, regla v2)\n"] + list(B.MD_HEAD)
    out = {}
    L = lambda kind, ss, u: [f"{kind}{'uniq' if u else 'v4'}_G3_f1_s{s}" for s in ss]
    combos = [("LGB x3 s3-s5 sin ponderar", L("lgb", (3, 4, 5), 0)), ("LGB x3 s3-s5 ponderado", L("lgb", (3, 4, 5), 1)),
              ("MLP x3 s0-s2 sin ponderar", L("mlp", (0, 1, 2), 0)), ("MLP x3 s0-s2 ponderado", L("mlp", (0, 1, 2), 1)),
              ("ENS6 sin ponderar", L("lgb", (0, 1, 2), 0) + L("mlp", (0, 1, 2), 0)),
              ("ENS6 ponderado", L("lgb", (0, 1, 2), 1) + L("mlp", (0, 1, 2), 1)),
              ("ENS12 sin ponderar", L("lgb", range(6), 0) + L("mlp", range(6), 0)),
              ("ENS12 ponderado", L("lgb", range(6), 1) + L("mlp", range(6), 1))]
    for lab, tags in combos:
        D = B.load_ens(tags, pred_dirs=[PD])
        T, s = B.simulate_entries(D, D["p"] >= D["thr"])
        r = B.summarize_trades(T, s, D, label=lab)
        gaps = []
        for k in range(6):
            Vk = D["vals"][k]
            if np.isfinite(Vk["thr"]):
                sv = Vk["p"] >= Vk["thr"]
                st = (D["fold"] == k) & (D["p"] >= D["thr"]) & np.isfinite(D["netX"])
                if st.any():
                    gaps.append(np.mean(Vk["netX"][sv] > 0) - np.mean(D["netX"][st] > 0))
        r["gap"] = float(np.mean(gaps) * 100) if gaps else None
        fold = []
        for te0, te1 in B.TESTS:
            m_ = (T.entry_t >= H.ms(*te0, 1)) & (T.entry_t < H.ms(*te1, 1))
            fold.append(f"{int(m_.sum())}/{np.mean(T.net_ret[m_]>0)*100:.0f}/{np.mean(T.net_ret[m_])*100:+.2f}" if m_.any() else "0")
        r["folds"] = fold
        lines.append(B.md_row(r) + f" brecha val−prueba {r['gap']:+.1f} pt | pliegues (n/WR/E) {', '.join(fold)}")
        print(lines[-1], flush=True); out[lab] = r
    B.log_once("uniq2", 3, "E11b unicidad: LGB s3-s5, MLP x6 ponderados; ENS6 y ENS12 ponderados (diseno)")
    with open(os.path.join(B.OUT, "be_uniq2.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    with open(os.path.join(B.OUT, "be_uniq2.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, default=float, indent=1)


if __name__ == "__main__":
    main()
