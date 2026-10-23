"""Ronda 1 - Paso 11: t del candidato con errores agrupados (las monedas caen juntas): suma neta por DÍA y por
MES como unidad independiente. Candidato: MR20 + ridge h96 decil superior (lambda=0.1N), geometrías T48/G2H96/G3H96."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import analista_common as ac
import analista_features as af
import analista_09_robustez as rb
import harness as Hh
lines = []
P = lambda s: (print(s), lines.append(s))
data = {s: ac.load(s) for s in ac.SYMS}
Fs = af.add_cross({s: af.build(data[s], 20) for s in ac.SYMS}, ac.SYMS)
bars = {s: Hh.load(s) for s in ac.SYMS}
S, I, take = rb.scores(data, Fs, 96, rb.FULL, 0.1)
for g in ("T48", "G2H96", "G3H96"):
    out = rb.run(bars, S, I, take, g)
    for part in ("A", "B", "A+B"):
        T = Hh.Trades.concat(out["A"] + out["B"]) if part == "A+B" else Hh.Trades.concat(out[part])
        x = T.net_ret
        day = T.entry_t // 86400000
        mon = T.entry_t.astype("datetime64[ms]").astype("datetime64[M]")
        res = []
        for lab, key in (("día", day), ("mes", mon)):
            u = np.unique(key)
            sums = np.array([x[key == k].sum() for k in u])
            # t de la media por operación con varianza agrupada (estimador sándwich por clúster)
            n = len(x); mu = x.mean()
            resid = np.array([(x[key == k] - mu).sum() for k in u])
            se = np.sqrt((resid ** 2).sum()) / n * np.sqrt(len(u) / (len(u) - 1))
            res.append(f"t_cluster_{lab}={mu/se:+.2f} ({len(u)} clústeres)")
        bs = Hh.bootstrap(x, B=4000, block=10, seed=1)
        P(f"{g:6s} {part:3s}: N={len(x)} E={x.mean()*100:+.3f}% t_iid={x.mean()/(x.std(ddof=1)/np.sqrt(len(x))):+.2f} "
          + " ".join(res) + f" | bootstrap bloques(10) IC95 E=[{bs['lo']*100:+.3f},{bs['hi']*100:+.3f}]% P(E<=0)={bs['p_le0']:.3f}")
with open(os.path.join(ac.OUTDIR, "11_cluster.txt"), "w", encoding="utf-8") as fh:
    fh.write("\n".join(lines))
