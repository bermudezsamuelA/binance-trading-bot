"""riesgo_sizing.py - dimensionamiento y supervivencia sobre operaciones MEDIDAS en diseno.
Uso: PYTHONIOENCODING=utf-8 python -I riesgo_sizing.py "MR:48:2.0|ATR:a=0.5,m=2.0,H=48" [...mas specs]
Para cada spec: Kelly binario y empirico, g(f), rachas, Monte Carlo (bootstrap por semanas, 10 000 trayectorias
de 1 ano) con y sin tope de nocional spot, correlacion entre monedas y concurrencia de posiciones.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from scipy.optimize import minimize_scalar
import riesgo_sim as S

rng = np.random.default_rng(12345)
WEEK = 7 * 86400000


def parse(spec):
    tf, e, c = spec.split("|")
    t, n, k = e.split(":")
    entry = (t, int(n), float(k))
    fam, ps = c.split(":") if ":" in c else (c, "")
    cfg = dict(fam=fam)
    for kv in filter(None, ps.split(",")):
        kk, vv = kv.split("=")
        cfg[kk] = float(vv) if kk != "H" else int(vv)
    return {"15m": 1, "1h": 4}[tf], entry, cfg


def p_streak(L, N, q):
    """P(al menos una racha de >= L perdidas seguidas en N operaciones independientes), cadena de Markov exacta."""
    st = np.zeros(L); st[0] = 1.0; absorbed = 0.0
    for _ in range(N):
        new = np.zeros(L)
        new[0] = st.sum() * (1 - q)
        new[1:] = st[:-1] * q
        absorbed += st[-1] * q
        st = new
    return absorbed


def kelly_emp(X):
    lo = -1 / X.min() if X.min() < 0 else 10
    res = minimize_scalar(lambda f: -np.mean(np.log1p(f * X)), bounds=(0, lo * 0.999), method="bounded")
    return res.x, -res.fun


def mc(weeks_X, weeks_R, f, cap=None, n_paths=10000, n_weeks=52):
    """Trayectorias de 1 ano remuestreando semanas completas (conserva la correlacion entre monedas dentro de la semana)."""
    W = len(weeks_X)
    mdd = np.empty(n_paths); fin = np.empty(n_paths); ruin = np.zeros(n_paths, bool)
    for p in range(n_paths):
        ws = rng.integers(0, W, n_weeks)
        X = np.concatenate([weeks_X[w] for w in ws])
        R = np.concatenate([weeks_R[w] for w in ws])
        fe = np.full(len(X), f) if cap is None else np.minimum(f, cap * R)
        eq = np.cumprod(1 + fe * X)
        pk = np.maximum.accumulate(np.r_[1.0, eq])[1:]
        dd = 1 - eq / pk
        mdd[p] = dd.max() if len(dd) else 0
        fin[p] = eq[-1] if len(eq) else 1
        ruin[p] = (eq.min() if len(eq) else 1) < 0.5
    return mdd, fin, ruin


def concurrency(tr):
    t0, t1 = tr["t_in"].min(), tr["t_out"].max()
    grid = np.arange(t0, t1, 900000)
    open_ = np.zeros((4, len(grid)), bool)
    for c in range(4):
        m = tr["coin"] == c
        a = np.searchsorted(grid, tr["t_in"][m]); b = np.searchsorted(grid, tr["t_out"][m])
        for x, y in zip(a, b):
            open_[c, x:y] = True
    k = open_.sum(0)
    return np.bincount(k, minlength=5) / len(k)


def overlap_corr(tr):
    """Correlacion de los R-multiplos entre operaciones de monedas distintas que se solapan en el tiempo."""
    X = tr["net"] / tr["R"]
    o = np.argsort(tr["t_in"]); ti, to, co, Xo = tr["t_in"][o], tr["t_out"][o], tr["coin"][o], X[o]
    a, b = [], []
    for i in range(len(o)):
        j = i + 1
        while j < len(o) and ti[j] < to[i]:
            if co[j] != co[i]:
                a.append(Xo[i]); b.append(Xo[j])
            j += 1
    if len(a) < 10:
        return np.nan, len(a), np.nan
    a, b = np.array(a), np.array(b)
    both_loss = np.mean((a < 0) & (b < 0))
    return np.corrcoef(a, b)[0, 1], len(a), both_loss


def returns_corr():
    R15, Rd = [], []
    for s in S.SYMS:
        d = S.load(s)
        lr = np.diff(np.log(d["c"]))
        R15.append(lr)
        n = len(lr) // 96 * 96
        Rd.append(lr[:n].reshape(-1, 96).sum(1))
    return np.corrcoef(np.array(R15)), np.corrcoef(np.array(Rd))


if __name__ == "__main__":
    DSS = {}
    c15, cd = returns_corr()
    iu = np.triu_indices(4, 1)
    print("Correlacion de retornos 15m (BTC,ETH,SOL,DOGE) pares:", np.round(c15[iu], 2), "media", round(c15[iu].mean(), 2))
    print("Correlacion de retornos diarios pares:", np.round(cd[iu], 2), "media", round(cd[iu].mean(), 2))
    for spec in sys.argv[1:]:
        agg, entry, cfg = parse(spec)
        if agg not in DSS:
            DSS[agg] = S.datasets(agg)
        tr = S.pooled_trades(DSS[agg], entry, [cfg])[0]
        X = tr["net"] / tr["R"]
        m = S.metrics(tr)
        p = m["WR"]; b = m["b_eff"]
        # b y p en unidades de R (para Kelly binario se usa el pago medio en R de ganadoras y perdedoras)
        bw = X[X > 0].mean(); bl = -X[X <= 0].mean(); bR = bw / bl
        fK = p - (1 - p) / bR  # fraccion de capital ARRIESGADA (perdida esperada al tocar SL = f*bl)
        fK_risk = fK / bl
        fE, gE = kelly_emp(X)
        print(f"\n=== {spec}  N={m['N']}  WR={p*100:.1f}%  b_eff={b:.3f}  E_R={m['E_R']:+.4f}  t_mes={m['t_month']:+.2f}")
        print(f" R-multiplos: ganadora media +{bw:.3f}R, perdedora media -{bl:.3f}R, min {X.min():+.2f}R, max {X.max():+.2f}R")
        print(f" Kelly binario f* = p-(1-p)/b = {fK:+.4f} (en unidades de 'perdida media'); como riesgo hasta SL: {fK_risk:+.4f}")
        print(f" Kelly empirico (max E[ln(1+fX)]) f* = {fE:.4f} del capital por R; g* = {gE:.6f} por operacion")
        se = X.std(ddof=1) / np.sqrt(len(X)); m2 = np.mean(X ** 2)
        print(f" Aprox. continua f* ~ E[X]/E[X^2] = {X.mean()/m2:+.4f}; con E rebajada 1.645 EE: {(X.mean()-1.645*se)/m2:+.4f}; "
              f"con E rebajada al umbral Bonferroni (4.18 EE): {(X.mean()-4.18*se)/m2:+.4f}")
        Ny = int(round(m["N"] / 2.5))
        for f in [0.0025, 0.005, 0.01, 0.02, fE / 4, fE / 2, fE]:
            if f > 0:
                print(f"   f={f:.4f}: g = {np.mean(np.log1p(f * X)):+.6f}/op, g anual (N/ano={m['N']/2.5:.0f}) = {np.mean(np.log1p(f*X))*m['N']/2.5:+.4f}")
        q = 1 - p
        Ny = int(round(m["N"] / 2.5))
        for L in (3, 5, 8, 10):
            print(f"   P(racha >= {L} perdidas en {Ny} ops/ano) = {p_streak(L, Ny, q):.3f}")
        print(f"   racha esperada mas larga ~ ln(N*p)/ln(1/q) = {np.log(Ny*p)/np.log(1/q):.1f}")
        # rachas observadas (por orden de salida, monedas mezcladas)
        Lseq = (X[np.argsort(tr['t_out'])] <= 0).astype(int)
        mx, cur = 0, 0
        for v in Lseq:
            cur = cur + 1 if v else 0; mx = max(mx, cur)
        print(f"   racha maxima observada en diseno: {mx}")
        wk = (tr["t_out"] // WEEK).astype(np.int64)
        o = np.argsort(tr["t_out"])
        weeks = np.arange(wk.min(), wk.max() + 1)
        wX = [X[o][wk[o] == w] for w in weeks]; wR = [tr["R"][o][wk[o] == w].astype(float) for w in weeks]
        for f, cap in [(0.005, None), (0.01, None), (0.02, None), (fE / 4, None), (fE / 2, None), (fE, None), (0.01, 0.25), (0.02, 0.25)]:
            if f <= 1e-4:
                continue
            mdd, fin, ruin = mc(wX, wR, f, cap, n_paths=4000)
            print(f"   MC f={f:.4f} tope_nocional={cap}: MDD mediana {np.median(mdd)*100:.1f}% p95 {np.percentile(mdd,95)*100:.1f}%, "
                  f"P(MDD>20%)={np.mean(mdd>0.2):.3f}, P(ruina: cae <50%)={ruin.mean():.4f}, retorno 1 ano mediana {np.median(fin)*100-100:+.1f}% "
                  f"[p5 {np.percentile(fin,5)*100-100:+.1f}%, p95 {np.percentile(fin,95)*100-100:+.1f}%]")
        conc = concurrency(tr)
        rho, npair, bl2 = overlap_corr(tr)
        print(f"   concurrencia (fraccion del tiempo con k=0..4 posiciones abiertas): {np.round(conc, 3)}")
        print(f"   corr. de R-multiplos entre operaciones solapadas de monedas distintas: rho={rho:.3f} (pares={npair}), P(ambas pierden)={bl2:.3f} vs indep {(X<=0).mean()**2:.3f}")
        R_notional = np.median(tr["R"])
        print(f"   R mediano {R_notional*100:.2f}% -> nocional por 1% de riesgo = {0.01/R_notional:.2f}x capital")
