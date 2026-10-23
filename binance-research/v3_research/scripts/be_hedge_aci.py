"""E27 - COBERTURA beta con BTC (corto en margen spot) sobre las operaciones v2 de ETH, SOL y DOGE, y
E26 - UMBRAL ADAPTATIVO EN LINEA tipo ACI sobre la precision (theta <- theta + eta (1[perdida] - alpha)). DISENO.

E27: retorno combinado = neto_alt - h*beta*(BTC_salida/BTC_entrada - 1) - h*beta*0.24 % - h*beta*interes(3 %/anio).
     (aprox.: la pata de BTC se cierra al cierre de la vela de salida). Azar con la misma cobertura (1 de cada 9 velas).
E26: eventos en orden temporal (4 monedas); una posicion por moneda; resultado y salida de la geometria X5 por vela;
     theta se reinicia al umbral v2 al inicio de cada pliegue y se actualiza al CERRAR cada operacion.
"""
import os, sys, json
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import be_common as B
H = B.H
C = B.C

D = B.load_ens()
names = list(D["cache"]["BTCUSDT"]["names"])
kb = names.index("beta_btc")
btc_c = D["cache"]["BTCUSDT"]["c"]
lines = ["# E27 cobertura beta con BTC y E26 umbral adaptativo ACI (diseno, ENS13, X5)\n"]
res = {}
# ---------------- E27
T, s = B.simulate_entries(D, D["p"] >= D["thr"])
alt = s != "BTCUSDT"
beta = np.array([D["cache"][sy]["X"][int(i), kb] for sy, i in zip(s, T.sig_idx)])
beta = np.clip(np.nan_to_num(beta, nan=1.0), 0.3, 2.0)
hold_days = (T.exit_t - T.entry_t) / B.DAY
rb = btc_c[T.exit_idx] / btc_c[T.entry_idx] - 1
lines += ["## E27 cobertura con BTC (solo operaciones en ETH, SOL y DOGE)\n",
          "| Variante | n | WR % [Wilson] | E % | t día | σ por op % | peor op % | Azar con la misma cobertura: WR % / E % |",
          "|---|---|---|---|---|---|---|---|"]
# azar con la misma cobertura
rows = np.flatnonzero((D["ci"] > 0) & np.isfinite(D["netX"]))[::9]
P0 = np.load(os.path.join(B.R.PRED, f"{B.ENS13[0]}.npz"))
labs = {}
for ci_, sy in enumerate(H.SYMBOLS):
    if ci_ == 0:
        continue
    S = C.spot_core(np.load(C.find_file(C.RESEARCH, "klines", f"{sy}_15m.npy"))[:len(D["cache"][sy]["c"])])
    net_, why_, jx_ = C.label_all(S, "X5", len(S["c"]))
    labs[ci_] = (net_, jx_)
for h in (0.0, 0.5, 1.0):
    x = T.net_ret[alt] - h * beta[alt] * (rb[alt] + 0.0024 + 0.03 * hold_days[alt] / 365)
    day = (T.entry_t // B.DAY)[alt]
    wr, lo, hi = B.wilson(int(np.sum(x > 0)), len(x))
    xr = []
    for r in rows:
        ci_ = int(D["ci"][r]); i = int(D["ii"][r])
        net_, jx_ = labs[ci_]
        if not np.isfinite(net_[i]) or jx_[i] < 0:
            continue
        bt = np.clip(np.nan_to_num(D["cache"][H.SYMBOLS[ci_]]["X"][i, kb], nan=1.0), 0.3, 2.0)
        hd = (jx_[i] - i) / 96
        xr.append(net_[i] - h * bt * (btc_c[jx_[i]] / btc_c[i] - 1 + 0.0024 + 0.03 * hd / 365))
    xr = np.array(xr)
    lab = f"h = {h} x beta" + (" (sin cobertura)" if h == 0 else "")
    lines.append(f"| {lab} | {len(x)} | {wr*100:.1f} [{lo*100:.1f}, {hi*100:.1f}] | {x.mean()*100:+.2f} | {B.cluster_t(x, day):.2f} | "
                 f"{x.std()*100:.2f} | {x.min()*100:.1f} | {np.mean(xr>0)*100:.1f} / {xr.mean()*100:+.2f} |")
    res[f"E27 {lab}"] = dict(n=len(x), wr=wr, E=float(x.mean() * 100), sd=float(x.std() * 100), rand_wr=float(np.mean(xr > 0)),
                             rand_E=float(xr.mean() * 100))
    print(lines[-1])
# ---------------- E26 ACI
labs[0] = None
S0 = C.spot_core(np.load(C.find_file(C.RESEARCH, "klines", "BTCUSDT_15m.npy"))[:len(D["cache"]["BTCUSDT"]["c"])])
n0, w0, j0 = C.label_all(S0, "X5", len(S0["c"]))
labs[0] = (n0, j0)
# fin de pliegue por moneda: la salida no puede pasar del fin del periodo (como harness): aproximamos usando el
# resultado por vela X5 de label_all hasta el fin de DISENO (diferencia minima; las mismas reglas para todas)
order = np.argsort(D["t"], kind="stable")


def run_aci(alpha, eta, fixed=False):
    theta = None; cur_fold = -1
    busy = {c: -1 for c in range(4)}
    pending = []           # (t_salida, gano)
    out = []
    for r in order:
        t = int(D["t"][r]); k = int(D["fold"][r]); ci_ = int(D["ci"][r]); i = int(D["ii"][r])
        if k != cur_fold:
            cur_fold = k; theta = D["thr"][r]
        # cerrar operaciones vencidas y actualizar theta
        still = []
        for (tx, win) in pending:
            if tx <= t:
                if not fixed and np.isfinite(theta):
                    theta = theta + eta * ((0 if win else 1) - alpha)
            else:
                still.append((tx, win))
        pending = still
        if not np.isfinite(theta) or i <= busy[ci_] or D["p"][r] < theta:
            continue
        net_, jx_ = labs[ci_]
        if not np.isfinite(net_[i]) or jx_[i] < 0:
            continue
        busy[ci_] = int(jx_[i])
        tx = t + (int(jx_[i]) - i) * C.MS15
        pending.append((tx, net_[i] > 0))
        out.append((net_[i], int(D["day"][r]), k))
    return np.array(out, float)


lines += ["\n## E26 umbral adaptativo en linea (ACI sobre la tasa de perdidas)\n",
          "| Variante | n | WR % [Wilson] | E % | t día | WR por pliegue (%) |", "|---|---|---|---|---|---|"]
for lab, a, e, fx in (("theta fijo v2 (referencia, mismo motor)", 0.25, 0.0, True), ("ACI alpha 0.25, eta 0.005", 0.25, 0.005, False),
                      ("ACI alpha 0.25, eta 0.02", 0.25, 0.02, False), ("ACI alpha 0.20, eta 0.005", 0.20, 0.005, False),
                      ("ACI alpha 0.20, eta 0.02", 0.20, 0.02, False)):
    a_ = run_aci(a, e, fx)
    x, day, fk = a_[:, 0], a_[:, 1], a_[:, 2]
    wr, lo, hi = B.wilson(int(np.sum(x > 0)), len(x))
    pf = [f"{np.mean(x[fk==k]>0)*100:.0f} ({int((fk==k).sum())})" if (fk == k).any() else "–" for k in range(6)]
    lines.append(f"| {lab} | {len(x)} | {wr*100:.1f} [{lo*100:.1f}, {hi*100:.1f}] | {x.mean()*100:+.2f} | {B.cluster_t(x, day):.2f} | {', '.join(pf)} |")
    res[f"E26 {lab}"] = dict(n=len(x), wr=wr, E=float(x.mean() * 100))
    print(lines[-1])
B.log_once("hedge_aci", 6, "E27 cobertura BTC h{0.5,1}; E26 ACI alpha{0.20,0.25} x eta{0.005,0.02} (diseno)")
with open(os.path.join(B.OUT, "be_hedge_aci.md"), "w", encoding="utf-8") as fh:
    fh.write("\n".join(lines) + "\n")
with open(os.path.join(B.OUT, "be_hedge_aci.json"), "w", encoding="utf-8") as fh:
    json.dump(res, fh, default=float, indent=1)
