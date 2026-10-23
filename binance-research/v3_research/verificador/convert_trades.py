"""Une los trades_{SYM}.csv de nn_eval.py en un CSV para verify.py (anade symbol, H y entry_mode)."""
import csv, glob, os, sys
src, dst, H = sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "192"
rows = []
for p in sorted(glob.glob(os.path.join(src, "trades_*.csv"))):
    sym = os.path.basename(p)[7:-4]
    with open(p, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append([sym, r["entry_t"], r["exit_t"], r["entry_px"], r["exit_px"], r["tp"], r["sl"], H, "close"])
with open(dst, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["symbol", "entry_t", "exit_t", "entry_px", "exit_px", "tp", "sl", "H", "entry_mode"]); w.writerows(rows)
print(len(rows), "operaciones ->", dst)
