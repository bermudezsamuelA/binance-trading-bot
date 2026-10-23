"""riesgo_r2_wf_bo.py - Ronda 2: protocolo del Validador (walk-forward 12/3/3 con purga) aplicado a MI familia 1h
(las mismas 3 447 configuraciones de la ronda 1). Regla de seleccion declarada: en cada pliegue elegir la config con
mayor E_R en los 12 meses de entrenamiento (N_train >= 30, solo operaciones que SALEN antes del inicio del test);
medir en los 3 meses de test (operaciones que ENTRAN en el test). Se reporta el OOS concatenado (18 meses).
Tambien se reporta, por pliegue, el candidato fijo BO(96,2.5) CHAN m=3 H=192 (elegido con todo el diseno: in-sample)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import riesgo_sim as S

A_GRID = [0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0]; M_GRID = [0.5, 1.0, 1.5, 2.0, 3.0, 4.0]; H_GRID = [16, 48, 96]
def cfgs_for(typ):
    c = [dict(fam="ATR", a=a, m=m, H=H) for a in A_GRID for m in M_GRID for H in H_GRID]
    if typ == "MR":
        c += [dict(fam="PATH", f=f, m=m, H=H) for f in [0.25, 0.5, 0.75, 1.0] for m in M_GRID for H in H_GRID]
        c += [dict(fam="MEAN", m=m, H=H) for m in [1.0, 2.0, 3.0, 4.0, 6.0] for H in H_GRID]
    c += [dict(fam="CHAN", m=m, H=H) for m in [1.0, 2.0, 3.0] for H in [48, 96, 192]]
    c += [dict(fam="PART", a1=a1, a2=a2, m=m, H=96) for a1 in [0.5, 1.0] for a2 in [2.0, 3.0] for m in [1.5, 2.0, 3.0]]
    return c
ENTRIES = [(t, n, k) for t in ("MR", "BO") for n in (20, 48, 96) for k in (1.5, 2.0, 2.5)]
DS = S.datasets(4)
store = []
for e in ENTRIES:
    groups = [cfgs_for(e[0]), [dict(fam="BOT_MR" if e[0] == "MR" else "BOT_BO", H=960)]]
    for cfgs in groups:
        res = S.pooled_trades(DS, e, cfgs, 1500 if cfgs[0]["H"] == 960 else 6000)
        for cfg, tr in zip(cfgs, res):
            store.append((e, cfg, tr["net"].astype(float), tr["R"].astype(float), tr["t_in"], tr["t_out"]))
print("configs:", len(store))
folds = []
for k in range(6):
    m0 = 12 + 3 * k  # meses desde 2023-01
    tr0 = S.ms(2023 + (m0 - 12) // 12, (m0 - 12) % 12 + 1, 1); te0 = S.ms(2023 + m0 // 12, m0 % 12 + 1, 1)
    m1 = m0 + 3
    te1 = S.ms(2023 + m1 // 12, m1 % 12 + 1, 1)
    folds.append((tr0, te0, te1))
oos_X, oos_net, rows = [], [], []
cand = [i for i, s in enumerate(store) if s[0] == ("BO", 96, 2.5) and s[1] == dict(fam="CHAN", m=3.0, H=192)][0]
for (tr0, te0, te1) in folds:
    best, bE = None, -9
    for i, (e, cfg, net, R, ti, to) in enumerate(store):
        mtr = (ti >= tr0) & (to < te0)
        if mtr.sum() < 30:
            continue
        E = (net[mtr] / R[mtr]).mean()
        if E > bE:
            bE, best = E, i
    e, cfg, net, R, ti, to = store[best]
    mte = (ti >= te0) & (ti < te1)
    X = net[mte] / R[mte]
    oos_X.append(X); oos_net.append(net[mte])
    c = store[cand]; mc = (c[4] >= te0) & (c[4] < te1); Xc = c[2][mc] / c[3][mc]
    rows.append((S.dt.datetime.utcfromtimestamp(te0 / 1000).strftime("%Y-%m"), e, cfg, bE, len(X), X.mean() if len(X) else np.nan, len(Xc), Xc.mean() if len(Xc) else np.nan))
for r in rows:
    print(f" test {r[0]}: elegida {r[1]} {r[2]} E_R_train={r[3]:+.3f} -> test N={r[4]} E_R={r[5]:+.3f} | candidato fijo N={r[6]} E_R={r[7]:+.3f}")
X = np.concatenate(oos_X); nt = np.concatenate(oos_net)
print(f"OOS concatenado (seleccion WF): N={len(X)} WR={np.mean(nt>0)*100:.1f}% E={nt.mean()*100:+.3f}% E_R={X.mean():+.3f} t={X.mean()/X.std(ddof=1)*np.sqrt(len(X)):+.2f} pliegues E_R>0: {sum(np.mean(x)>0 for x in oos_X if len(x))}/6")
print(f"   con costos 0.30 %: E={(nt-0.0006).mean()*100:+.3f}%")
c = store[cand]
for (tr0, te0, te1) in folds[:1]:
    pass
mo = (c[4] >= folds[0][1])
Xc = c[2][mo] / c[3][mo]
print(f"Candidato fijo en los 18 meses OOS (NO es fuera de muestra: se eligio con todo el diseno): N={len(Xc)} E_R={Xc.mean():+.3f} t={Xc.mean()/Xc.std(ddof=1)*np.sqrt(len(Xc)):+.2f}")
