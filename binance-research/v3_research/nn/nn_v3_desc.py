"""Medicion DESCRIPTIVA del candidato v3 congelado (P1 = v2 + compuerta A4 >= 1, W = 48 + salida X5 con 384 velas)
sobre las 4 monedas originales en el periodo posterior a su entrenamiento. Sin parametros libres: todo sale de
spec_nn_v2.json (modelos, Platt, umbral) y de la seccion 2 de doc/estrategia-v3-hacia-el-80.md (compuerta y salida).

Ese periodo de las 4 originales ya estaba gastado (holdout_log.csv: desc_v2_originales), asi que esto NO es la prueba
prospectiva pre-registrada (seccion 8.2), no decide nada y no cambia la spec. Comprobacion de paridad: el brazo
"v2 X5 288" debe reproducir verificador/runs/desc_v2_originales (n = 203, WR 72.9 %, E +0.122 %).

Uso (desde binance-research):
  .venv\\Scripts\\python -I data\\research\\nn\\nn_v3_desc.py --start 2025-07-01 --end 2026-10-01 \
      --data-dir data\\research --reason "..."
"""
import argparse, datetime as dt, hashlib, json, os, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import nn_common as C
import nn_wf as W
import nn_report as R
import nn_v2_report as V  # noqa: F401  registra las geometrias v2 (X5) en C.GEOMS
H = C.H
SPEC = os.path.join(C.RESEARCH, "output", "constructor", "spec_nn_v2.json")
MODELS = os.path.join(HERE, "models_v2")
ANCHORS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT"]
GATE_W = 48                      # 12 h, incluye la vela actual (seccion 2.9)
C.GEOMS["X5_384"] = (0.7, 1.75, 384)


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def to_ms(s):
    return int(dt.datetime.fromisoformat(s).replace(tzinfo=dt.timezone.utc).timestamp() * 1000)


def check_hashes(spec):
    bad = []
    for f, hv in spec["sha256_scripts"].items():
        if f == "nn_v2_eval.py":
            continue
        p = os.path.join(C.RESEARCH, "scripts", f) if f == "harness.py" else os.path.join(HERE, f)
        if not os.path.exists(p) or sha(p) != hv:
            bad.append(f)
    for m in spec["miembros"]:
        for f, hv in m["sha256"].items():
            if sha(os.path.join(MODELS, f)) != hv:
                bad.append(f)
    if bad:
        raise SystemExit(f"HASH DISTINTO: {bad}")


def load_members(spec, n_vars):
    import lightgbm as lgb
    import torch
    members = []
    for m in spec["miembros"]:
        if m["kind"] == "lgb":
            members.append(("lgb", lgb.Booster(model_file=os.path.join(MODELS, m["file"])), None, m["platt"]))
        else:
            sc = np.load(os.path.join(MODELS, m["scaler"]))
            net_ = W.torch_model(m["kind"], n_vars, 10)
            net_.load_state_dict(torch.load(os.path.join(MODELS, m["file"])))
            net_.eval()
            members.append((m["kind"], net_, (sc["mu"], sc["sd"]), m["platt"]))
    return members


def predict(members, X, ridx, Q):
    """p calibrada (media de los 13 miembros con Platt), igual que nn_v2_eval.py."""
    import torch
    p = np.zeros(len(X))
    for kind, mod, sc, ab in members:
        s = np.zeros(len(X))
        if kind == "lgb":
            s[ridx] = mod.predict(X[ridx], raw_score=True)
        else:
            Z = W.standardize(X[ridx], sc[0], sc[1])
            out = []
            for k0 in range(0, len(ridx), 4096):
                rr_ = ridx[k0:k0 + 4096]
                xt = torch.from_numpy(Z[k0:k0 + 4096])
                xs = None
                if kind == "cnn":
                    w = rr_[:, None] + np.arange(-W.SEQ_L + 1, 1)[None, :]
                    xs = torch.from_numpy(Q[w].transpose(0, 2, 1).copy())
                with torch.no_grad():
                    out.append(mod(xt, xs).numpy())
            s[ridx] = np.concatenate(out) if out else np.zeros(0)
        p += R.platt_apply(s, ab) / len(members)
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True, help="exclusivo")
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--reason", required=True)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    spec = json.load(open(SPEC, encoding="utf-8"))
    check_hashes(spec)
    names, thr = spec["variables"], spec["regla"]["umbral"]
    ms0, ms1 = to_ms(a.start), to_ms(a.end)
    members = load_members(spec, len(names))
    out_dir = a.out or os.path.join(C.RESEARCH, "output", "constructor",
                                    "desc_v3_" + dt.datetime.now().strftime("%Y%m%d_%H%M%S"))
    os.makedirs(out_dir, exist_ok=True)

    D = {}
    for sym in ANCHORS:
        S, B, F, FU = C.build_symbol(a.data_dir, sym, use_fut=spec["usa_futuros"], t_end_ms=ms1)
        arr = C.load_spot(a.data_dir, sym)
        bars = H.Bars(arr[arr[:, 0] < ms1], sym)
        i0, i1 = H.bounds(bars, (ms0, ms1), reason=a.reason, who="nn_v3_desc")
        X = np.stack([F[k] for k in names], 1).astype(np.float32)
        X[~np.isfinite(X)] = np.nan
        idx = np.arange(len(X))
        valid = (idx >= W.WARM) & np.isfinite(S["s15"]) & (S["s15"] > 0)
        ridx = np.flatnonzero(valid & (idx >= i0) & (idx < i1))
        Q = C.seq_channels(S, B, FU)[0]
        p = predict(members, X, ridx, Q)
        sig = np.zeros(len(X), bool)
        sig[ridx] = p[ridx] >= thr
        D[sym] = dict(S=S, bars=bars, i0=i0, i1=i1, valid=valid, sig=sig, p=p)
        print(f"{sym}: {len(ridx)} velas evaluadas, {int(sig.sum())} con p >= theta", flush=True)

    # Compuerta A4: otras anclas con senal en las ultimas GATE_W velas (incluida la actual), por open_time
    tg = np.unique(np.concatenate([D[s]["S"]["t"].astype(np.int64) for s in ANCHORS]))
    roll = {}
    for s in ANCHORS:
        g = np.zeros(len(tg))
        g[np.searchsorted(tg, D[s]["S"]["t"].astype(np.int64))] = D[s]["sig"]
        roll[s] = H.rolling_max(g, GATE_W) > 0
    for s in ANCHORS:
        rows = np.searchsorted(tg, D[s]["S"]["t"].astype(np.int64))
        D[s]["A"] = sum(roll[o][rows].astype(int) for o in ANCHORS if o != s)

    arms = [("v2 X5 288 (paridad con desc_v2_originales)", "X5", lambda d: d["sig"]),
            ("C0 = v2 sin compuerta, X5 384", "X5_384", lambda d: d["sig"]),
            ("P1 = v3 (v2 + A4 >= 1, X5 384)", "X5_384", lambda d: d["sig"] & (d["A"] >= 1)),
            ("v2 aislada (A4 = 0), X5 384", "X5_384", lambda d: d["sig"] & (d["A"] == 0))]
    res = {"spec": spec["nombre"], "periodo": [a.start, a.end], "umbral": thr, "compuerta_W": GATE_W, "brazos": {}}
    for label, g, rule in arms:
        ga, gm, gH = C.GEOMS[g]
        for fee_lab, fee in (("0.24 %", H.FEE), ("0.30 %", 0.0013)):
            trs, base = [], {}
            for sym in ANCHORS:
                d = D[sym]; S = d["S"]
                sd = S["s15"] * np.sqrt(96)
                tp, sl = S["c"] * (1 + ga * sd), S["c"] * (1 - gm * sd)
                tr = H.simulate(d["bars"], rule(d), tp, sl, period=(d["i0"], d["i1"]), max_hold=gH, fee=fee)
                netr, _, _ = C.label_all(S, g, d["i1"], fee=fee)
                mon = np.array([int(dt.datetime.fromtimestamp(x / 1000, dt.timezone.utc).strftime("%Y%m"))
                                for x in S["t"]])
                rr = np.zeros(len(S["t"]), bool); rr[d["i0"]:d["i1"]] = True
                okr = rr & d["valid"] & np.isfinite(netr)
                for mo in np.unique(mon[okr]):
                    s_ = okr & (mon == mo)
                    base[(sym, int(mo))] = (float(np.mean(netr[s_] > 0)), float(np.mean(netr[s_])))
                if len(tr):
                    trs.append((sym, tr))
            if not trs:
                print(f"{label} c={fee_lab}: sin operaciones"); continue
            m, T, syms = R.summarize(trs, base, 1, f"{label} c={fee_lab}")
            mon = [int(dt.datetime.fromtimestamp(x / 1000, dt.timezone.utc).strftime("%Y%m")) for x in T.entry_t]
            u, inv = np.unique(mon, return_inverse=True)
            mp = np.bincount(inv, weights=T.net_ret)
            m["meses_positivos"] = [int((mp > 0).sum()), len(u)]
            m["pnl_15usdt"] = float(np.sum(T.net_ret) * 15)
            res["brazos"][f"{label} c={fee_lab}"] = m
            print(R.fmt(m), "| meses+", m["meses_positivos"], f"| PnL con 15 USDT/op {m['pnl_15usdt']:+.2f}", flush=True)
            if fee_lab == "0.24 %" and label.startswith("P1"):
                for sym, tr in trs:
                    tr.to_csv(os.path.join(out_dir, f"trades_P1_{sym}.csv"))
    with open(os.path.join(out_dir, "metrics.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1, default=float)
    print("salida:", out_dir)


if __name__ == "__main__":
    main()
