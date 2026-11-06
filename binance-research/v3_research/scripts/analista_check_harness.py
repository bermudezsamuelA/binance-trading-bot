"""Verificación cruzada: simulador del Analista vs harness.py del Validador (DISEÑO, MR 20/2, R>=0.5%)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import analista_common as ac
import harness as H
for s in ac.SYMS:
    for m_sl, mh in ((1.0, None), (2.0, 96)):
        b = H.load(s); i0, i1 = H.bounds(b, "design")
        mu, sd = H.rolling_mean(b.c, 20), H.rolling_std(b.c, 20)
        R = mu - b.c
        with np.errstate(invalid="ignore"):
            sig = (b.c < mu - 2 * sd) & (R >= 0.005 * b.c)
        tr = H.simulate(b, sig, mu, b.c - m_sl * R, period=(i0, i1), max_hold=mh)
        mH = H.metrics(tr)
        d = ac.load(s)
        idx = np.where(sig[i0:i1])[0]
        mine = ac.run_trades(d, idx, mu[i0:i1][idx], (b.c - m_sl * R)[i0:i1][idx], H=mh)
        mm = ac.metrics(mine["r_net"], mine["R"])
        print(f"{s} SL={m_sl}R H={mh}: harness N={mH['n']} WR={mH['wr']*100:.2f} E%={mH['E_pct']:+.4f} E_R={mH['E_R']:+.4f} | "
              f"analista N={mm['N']} WR={mm['WR']*100:.2f} E%={mm['E_pct']:+.4f} E_R={mm['E_R']:+.4f}")
