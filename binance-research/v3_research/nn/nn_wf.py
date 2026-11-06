"""Walk-forward en DISENO (tests trimestrales 2024Q1..2025Q2) para un modelo / geometria / con o sin futuros.

Guarda, por pliegue, las puntuaciones crudas en validacion (ultimos 3 meses antes del test, con purga) y en test.
La calibracion, el umbral y la simulacion se hacen en nn_report.py (sin tocar el test para elegir nada).

Uso: python -I nn_wf.py --model lgb|mlp|cnn --geom G1 --fut 1 [--seed 0]
"""
import argparse, os, sys, time, datetime as dt
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nn_common as C
H = C.H

CACHE = os.environ.get("NN_CACHE") or os.path.join(C.RESEARCH, "tmp", "nn_cache")
PRED = os.path.join(C.RESEARCH, "tmp", "nn_preds")
os.makedirs(PRED, exist_ok=True)
FUT_PREFIX = ("oi_", "top_", "glob_", "fut_", "funding", "premium", "basis", "metrics_")
SEQ_L = 96
WARM = 800  # velas de calentamiento (sigma de 7 dias, z de 672)


def ms(y, m):
    return int(dt.datetime(y, m, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)


TESTS = [((2024, 1), (2024, 4)), ((2024, 4), (2024, 7)), ((2024, 7), (2024, 10)), ((2024, 10), (2025, 1)),
         ((2025, 1), (2025, 4)), ((2025, 4), (2025, 7))]


def add_months(y, m, k):
    z = y * 12 + (m - 1) + k
    return z // 12, z % 12 + 1


def load_pool(geom, use_fut):
    rows = []
    for ci, sym in enumerate(H.SYMBOLS):
        z = np.load(os.path.join(CACHE, f"{sym}.npz"))
        names = list(z["names"])
        keep = [k for k, n in enumerate(names) if use_fut or not n.startswith(FUT_PREFIX)]
        X = z["X"][:, keep]
        Q = z["Q"] if use_fut else z["Q"][:, :6]
        net = z[f"net_{geom}"]
        n = len(net)
        idx = np.arange(n)
        ok = (idx >= WARM) & np.isfinite(net)
        rows.append(dict(sym=sym, ci=ci, X=X, Q=Q, net=net, t=z["t"], ok=ok, names=[names[k] for k in keep]))
    return rows


# ------------------------------------------------------------------ modelos
def fit_lgb(Xf, yf, Xv, yv, seed):
    import lightgbm as lgb
    params = dict(objective="binary", learning_rate=0.03, num_leaves=15, min_data_in_leaf=1000,
                  feature_fraction=0.7, bagging_fraction=0.5, bagging_freq=1, lambda_l2=10.0, max_bin=63,
                  num_threads=6, verbose=-1, seed=seed, metric="auc")
    dtr = lgb.Dataset(Xf, yf); dva = lgb.Dataset(Xv, yv, reference=dtr)
    m = lgb.train(params, dtr, num_boost_round=1500, valid_sets=[dva],
                  callbacks=[lgb.early_stopping(150, verbose=False)])
    it = max(m.best_iteration, 50)   # minimo 50 arboles (la AUC de validacion es ruidosa)
    return m, it


def standardize_fit(X):
    mu = np.nanmean(X, 0); sd = np.nanstd(X, 0)
    sd = np.where(sd > 1e-12, sd, 1.0)
    return mu, sd


def standardize(X, mu, sd):
    Z = (X - mu) / sd
    Z = np.nan_to_num(Z, nan=0.0, posinf=0.0, neginf=0.0)
    return np.clip(Z, -5, 5).astype(np.float32)


def torch_model(kind, n_tab, n_ch):
    import torch.nn as nn
    import torch

    class MLP(nn.Module):
        def __init__(s):
            super().__init__()
            s.f = nn.Sequential(nn.Linear(n_tab, 128), nn.GELU(), nn.Dropout(0.3), nn.Linear(128, 64), nn.GELU(),
                                nn.Dropout(0.3), nn.Linear(64, 1))

        def forward(s, xt, xs=None):
            return s.f(xt).squeeze(-1)

    class CNN(nn.Module):
        def __init__(s):
            super().__init__()
            L = []
            cin = n_ch
            for d in (1, 2, 4, 8):
                L += [nn.Conv1d(cin, 24, 5, dilation=d, padding=2 * d), nn.GELU()]
                cin = 24
            s.conv = nn.Sequential(*L)
            s.drop_in = nn.Dropout(0.1)
            s.tab = nn.Sequential(nn.Linear(n_tab, 64), nn.GELU(), nn.Dropout(0.3))
            s.head = nn.Sequential(nn.Linear(72 + 64, 64), nn.GELU(), nn.Dropout(0.3), nn.Linear(64, 1))

        def forward(s, xt, xs):
            h = s.conv(s.drop_in(xs))
            pooled = torch.cat([h.mean(-1), h.amax(-1), h[:, :, -1]], 1)
            return s.head(torch.cat([pooled, s.tab(xt)], 1)).squeeze(-1)

    return MLP() if kind == "mlp" else CNN()


class SeqGetter:
    """Ventanas causales de SEQ_L velas que terminan en la vela i (incluida)."""

    def __init__(self, pool):
        self.Q = [p["Q"] for p in pool]

    def __call__(self, ci, ii):
        out = np.zeros((len(ii), self.Q[0].shape[1], SEQ_L), np.float32)
        for c in np.unique(ci):
            m = ci == c
            idx = ii[m][:, None] + np.arange(-SEQ_L + 1, 1)[None, :]
            out[m] = self.Q[c][idx].transpose(0, 2, 1)
        return out


def auc_score(s, yy):
    from scipy.stats import rankdata
    r = rankdata(s); n1 = yy.sum(); n0 = len(yy) - n1
    return float((r[yy == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def fit_torch(kind, Xf, yf, cf, if_, Xv, yv, cv, iv, seq, seed, max_epochs=12, patience=3, bs=512):
    import torch
    torch.manual_seed(seed); np.random.seed(seed)
    torch.set_num_threads(6)
    model = torch_model(kind, Xf.shape[1], seq.Q[0].shape[1] if seq else 0)
    opt = torch.optim.AdamW(model.parameters(), lr=5e-4, weight_decay=1e-3)
    lossf = torch.nn.BCEWithLogitsLoss()

    def batches(X, y, c, i, shuffle):
        n = len(y)
        order = np.random.permutation(n) if shuffle else np.arange(n)
        for k in range(0, n, bs):
            b = order[k:k + bs]
            xt = torch.from_numpy(X[b])
            xs = torch.from_numpy(seq(c[b], i[b])) if seq else None
            yield xt, xs, torch.from_numpy(y[b].astype(np.float32))

    def predict(X, c, i):
        model.eval(); out = []
        with torch.no_grad():
            for xt, xs, _ in batches(X, np.zeros(len(X)), c, i, False):
                out.append(model(xt, xs).numpy())
        return np.concatenate(out)

    best, best_state, bad, ep_best = np.inf, None, 0, 0
    for ep in range(max_epochs):
        model.train()
        for xt, xs, yb in batches(Xf, yf, cf, if_, True):
            opt.zero_grad(); loss = lossf(model(xt, xs), yb); loss.backward(); opt.step()
        sv = predict(Xv, cv, iv)
        vl = -auc_score(sv, yv)          # parada temprana por AUC de validacion (Platt corrige la escala)
        if vl < best - 1e-4:
            best, bad, ep_best = vl, 0, ep + 1
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
        else:
            bad += 1
            if bad >= patience:
                break
    model.load_state_dict(best_state)
    return model, predict, ep_best


# ------------------------------------------------------------------ walk-forward
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--geom", required=True)
    ap.add_argument("--fut", type=int, default=1)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--stride", type=int, default=1, help="submuestreo del conjunto de ajuste (velas)")
    ap.add_argument("--tagx", default="", help="sufijo de version en el nombre de salida")
    a = ap.parse_args()
    Hh = C.GEOMS[a.geom][2]
    pool = load_pool(a.geom, bool(a.fut))
    ci = np.concatenate([np.full(len(p["net"]), p["ci"]) for p in pool])
    ii = np.concatenate([np.arange(len(p["net"])) for p in pool])
    X = np.concatenate([p["X"] for p in pool]).astype(np.float32)
    net = np.concatenate([p["net"] for p in pool])
    t = np.concatenate([p["t"] for p in pool]).astype(np.int64)
    ok = np.concatenate([p["ok"] for p in pool])
    y = (net > 0).astype(np.float32)
    seq = SeqGetter(pool) if a.model == "cnn" else None
    tag = f"{a.model}{a.tagx}_{a.geom}_f{a.fut}_s{a.seed}"
    res = {"names": np.array(pool[0]["names"])}
    t_start = time.time()
    for k, (te0, te1) in enumerate(TESTS):
        T0, T1 = ms(*te0), ms(*te1)
        V0 = ms(*add_months(*te0, -3))
        purge = (Hh + 1) * C.MS15
        fit = ok & (t < V0 - purge)
        val = ok & (t >= V0) & (t < T0 - purge)
        tst = ok & (t >= T0) & (t < T1)
        fit_idx = np.flatnonzero(fit)
        if a.stride > 1:
            fit_idx = fit_idx[(ii[fit_idx] % a.stride) == 0]
        if a.model == "lgb":
            m, it = fit_lgb(X[fit_idx], y[fit_idx], X[val], y[val], a.seed + k)
            sv, st = m.predict(X[val], raw_score=True, num_iteration=it), m.predict(X[tst], raw_score=True, num_iteration=it)
            info = it
            if k == len(TESTS) - 1:
                imp = m.feature_importance("gain"); res["importance"] = imp
        else:
            mu, sd = standardize_fit(X[fit_idx])
            Zf, Zv, Zt = standardize(X[fit_idx], mu, sd), standardize(X[val], mu, sd), standardize(X[tst], mu, sd)
            model, predict, info = fit_torch(a.model, Zf, y[fit_idx], ci[fit_idx], ii[fit_idx], Zv, y[val],
                                             ci[val], ii[val], seq, a.seed + k)
            sv, st = predict(Zv, ci[val], ii[val]), predict(Zt, ci[tst], ii[tst])
        res[f"f{k}_val_rows"] = np.flatnonzero(val); res[f"f{k}_val_s"] = sv.astype(np.float32)
        res[f"f{k}_tst_rows"] = np.flatnonzero(tst); res[f"f{k}_tst_s"] = st.astype(np.float32)
        from scipy.stats import rankdata
        def auc(s, yy):
            r = rankdata(s); n1 = yy.sum(); n0 = len(yy) - n1
            return (r[yy == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)
        print(f"{tag} pliegue {k} test {te0} fit {len(fit_idx)} val {val.sum()} test {tst.sum()} it/ep {info} "
              f"AUCval {auc(sv, y[val]):.4f} AUCtest {auc(st, y[tst]):.4f} {time.time()-t_start:.0f}s", flush=True)
    res.update(ci=ci, ii=ii, t=t, net=net)
    np.savez(os.path.join(PRED, f"{tag}.npz"), **res)


if __name__ == "__main__":
    main()
