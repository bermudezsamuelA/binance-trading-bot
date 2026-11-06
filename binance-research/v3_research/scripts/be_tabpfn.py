"""E10 - TabPFN v2 (modelo fundacional tabular, aprendizaje en contexto, CPU) frente al ensamble ENS13 sobre
VELAS CANDIDATAS (regla fija sin ajuste: ret_4 <= -1.5 o (bar_range >= 2.5 y ret_1 < 0)). DISENO, 6 pliegues.

TabPFN se ajusta en contexto con hasta 3000 candidatas de entrenamiento (t < inicio de validacion - purga, igual que
el ensamble) con la etiqueta G3; se compara dentro de las candidatas de prueba: AUC (G3 y X5) y WR / E (X5, por
vela) del 10 % y 5 % superior segun cada puntuacion, y de su promedio de rangos.
Paquetes aislados en E:/tmp/be_pkgs (tabpfn 2.2.1, scikit-learn 1.6.1); telemetria desactivada con un stub.
"""
import os, sys, json, time
os.environ["TABPFN_DISABLE_TELEMETRY"] = "1"
os.environ["HF_HOME"] = r"E:\hf-cache"
sys.path.insert(0, r"E:\tmp\be_pkgs")
sys.path.insert(0, r"E:\tmp")
import be_tabpfn_stub  # noqa: F401
import numpy as np
from scipy.stats import rankdata
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import be_common as B
from tabpfn import TabPFNClassifier
H = B.H
C = B.C

D = B.load_ens()
P0 = np.load(os.path.join(B.R.PRED, f"{B.ENS13[0]}.npz"))
ci_all, ii_all, t_all, netG3_all = P0["ci"], P0["ii"], P0["t"].astype(np.int64), P0["net"]
names = list(D["cache"]["BTCUSDT"]["names"])
X_all = np.concatenate([D["cache"][s]["X"] for s in H.SYMBOLS]).astype(np.float32)
netX_all = np.concatenate([D["cache"][s]["net_X5"] for s in H.SYMBOLS])
r4, br, r1 = (X_all[:, names.index(k)] for k in ("ret_4", "bar_range", "ret_1"))
cand_all = (np.nan_to_num(r4) <= -1.5) | ((np.nan_to_num(br) >= 2.5) & (np.nan_to_num(r1) < 0))
ok_all = np.isfinite(netG3_all) & (ii_all >= 800)
print("fraccion de candidatas:", cand_all[ok_all].mean())


def ms(y, m):
    return H.ms(y, m, 1)


def auc(s, y):
    r = rankdata(s); n1 = y.sum(); n0 = len(y) - n1
    return float((r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


rng = np.random.default_rng(0)
rows_out = []
lines = ["# E10 TabPFN v2 frente a ENS13 sobre velas candidatas (diseno)\n",
         "| Pliegue | cand. prueba | AUC G3 ENS / TabPFN | AUC X5 ENS / TabPFN | top 10 %: WR X5 ENS / TabPFN / mezcla | top 10 %: E X5 % ENS / TabPFN / mezcla | top 5 %: WR ENS / TabPFN / mezcla | top 5 %: E % ENS / TabPFN / mezcla |",
         "|---|---|---|---|---|---|---|---|"]
agg = {k: [] for k in ("ens", "tab", "mix")}
t0 = time.time()
pos = {int(r): k for k, r in enumerate(D["rows"])}
for k, (te0, te1) in enumerate(B.TESTS):
    T0, T1 = ms(*te0), ms(*te1)
    V0 = ms(*B.V.add_months(*te0, -3)) if hasattr(B.V, "add_months") else None
    if V0 is None:
        y_, m_ = te0
        z = y_ * 12 + (m_ - 1) - 3
        V0 = ms(z // 12, z % 12 + 1)
    purge = 193 * C.MS15
    tr = np.flatnonzero(ok_all & cand_all & (t_all < V0 - purge))
    if len(tr) > 3000:
        tr = np.sort(rng.choice(tr, 3000, replace=False))
    te = np.flatnonzero(ok_all & cand_all & (t_all >= T0) & (t_all < T1) & np.isfinite(netX_all))
    Xtr = np.nan_to_num(X_all[tr], nan=0.0, posinf=0.0, neginf=0.0)
    Xte = np.nan_to_num(X_all[te], nan=0.0, posinf=0.0, neginf=0.0)
    ytr = (netG3_all[tr] > 0).astype(int)
    clf = TabPFNClassifier(device="cpu", n_estimators=4, ignore_pretraining_limits=True, random_state=k)
    clf.fit(Xtr, ytr)
    pt = np.concatenate([clf.predict_proba(Xte[j:j + 2000])[:, 1] for j in range(0, len(Xte), 2000)])
    pe = np.array([D["p"][pos[int(r)]] if int(r) in pos else np.nan for r in te])
    good = np.isfinite(pe)
    te, pt, pe = te[good], pt[good], pe[good]
    yG = (netG3_all[te] > 0).astype(int); yX = (netX_all[te] > 0).astype(int); nx = netX_all[te]
    mix = rankdata(pt) + rankdata(pe)
    cells = []
    res_k = {}
    for q in (0.90, 0.95):
        for nm, s in (("ens", pe), ("tab", pt), ("mix", mix)):
            sel = s >= np.quantile(s, q)
            res_k[(q, nm)] = (float(np.mean(nx[sel] > 0)), float(np.mean(nx[sel]) * 100), int(sel.sum()))
            if q == 0.95:
                agg[nm].append(nx[sel])
    lines.append(f"| {k} | {len(te)} | {auc(pe, yG):.3f} / {auc(pt, yG):.3f} | {auc(pe, yX):.3f} / {auc(pt, yX):.3f} | "
                 + " / ".join(f"{res_k[(0.90, n)][0]*100:.1f}" for n in ("ens", "tab", "mix")) + " | "
                 + " / ".join(f"{res_k[(0.90, n)][1]:+.2f}" for n in ("ens", "tab", "mix")) + " | "
                 + " / ".join(f"{res_k[(0.95, n)][0]*100:.1f}" for n in ("ens", "tab", "mix")) + " | "
                 + " / ".join(f"{res_k[(0.95, n)][1]:+.2f}" for n in ("ens", "tab", "mix")) + " |")
    print(lines[-1], f"{time.time()-t0:.0f}s", flush=True)
lines.append("\nAgregado top 5 % de candidatas (6 pliegues, por vela): " + "; ".join(
    f"{nm}: n={len(np.concatenate(v))} WR={np.mean(np.concatenate(v)>0)*100:.1f} % E={np.mean(np.concatenate(v))*100:+.2f} %"
    for nm, v in agg.items()))
print(lines[-1])
B.log_once("tabpfn", 2, "E10 TabPFN v2 sobre candidatas (top 10/5 %), y mezcla de rangos con ENS13 (diseno)")
with open(os.path.join(B.OUT, "be_tabpfn.md"), "w", encoding="utf-8") as fh:
    fh.write("\n".join(lines) + "\n")
