import numpy as np, datetime as dt
K = "../klines/"
SPLIT = int(dt.datetime(2025,7,1,tzinfo=dt.timezone.utc).timestamp()*1000)
for s in ["BTCUSDT","ETHUSDT","SOLUSDT","DOGEUSDT"]:
    a = np.load(K+s+"_15m.npy")
    t = a[:,0]; d = np.diff(t)
    nd = (t < SPLIT).sum()
    o,h,l,c = a[:nd,1],a[:nd,2],a[:nd,3],a[:nd,4]
    tr = np.maximum(h[1:]-l[1:], np.maximum(abs(h[1:]-c[:-1]), abs(l[1:]-c[:-1])))
    atrp = np.convolve(tr, np.ones(14)/14, 'valid')/c[14:]
    print(s, a.shape, "design bars", nd, "gaps>15m:", (d!=900000).sum(), "max gap h", d.max()/3.6e6,
          "ATR14%% pctl 10/50/90: %.3f %.3f %.3f" % tuple(np.percentile(atrp*100,[10,50,90])),
          "price %.4f -> %.4f" % (c[0], c[-1]))
