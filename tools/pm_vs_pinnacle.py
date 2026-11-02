#!/usr/bin/env python3
"""Analyse : python tools/pm_vs_pinnacle.py epl.json E0.csv  (nécessite .cache/footballdata/2526.zip)."""
import json, sys, zipfile, io, csv, math
from datetime import datetime, timezone, timedelta
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.abspath(__file__))))
from autonome.match import sim
from autonome.devig import shin
pm = json.load(open(sys.argv[1]))
z = zipfile.ZipFile('.cache/footballdata/2526.zip')
fd = list(csv.DictReader(io.TextIOWrapper(z.open(sys.argv[2]), 'utf-8-sig')))
def fdt(r):
    d = datetime.strptime(r['Date'], '%d/%m/%Y')
    return d
rows = []
for g in pm:
    home, away = g['title'].split(' vs. ')
    st = datetime.fromisoformat(g['start'].replace('Z', '+00:00'))
    best = None
    for r in fd:
        if abs((fdt(r).date() - st.date()).days) > 1: continue
        s = sim(home, r['HomeTeam']) + sim(away, r['AwayTeam'])
        if s > 1.3 and (best is None or s > best[0]): best = (s, r)
    if not best or not best[1].get('PSCH'): continue
    r = best[1]
    sel = g['sel']
    def find(k):
        for name, v in sel.items():
            if k == 'draw' and name.lower().startswith('draw'): return v
            if k == 'home' and name == home: return v
            if k == 'away' and name == away: return v
    h, d, a = find('home'), find('draw'), find('away')
    if not all(x and x['close'] is not None for x in (h, d, a)): continue
    p = [h['close'], d['close'], a['close']]; s = sum(p); p = [x / s for x in p]
    ps = shin([float(r['PSCH']), float(r['PSCD']), float(r['PSCA'])])
    res = {'H': 0, 'D': 1, 'A': 2}[r['FTR']]
    lag = (st.timestamp() - max(h['close_t'], d['close_t'], a['close_t'])) / 60
    rows.append((p, ps, res, lag, s))
n = len(rows)
mad = sum(abs(a - b) for p, ps, *_ in rows for a, b in zip(p, ps)) / (3 * n)
ll = lambda q, y: -math.log(max(q[y], 1e-9))
br = lambda q, y: sum((q[i] - (1 if i == y else 0)) ** 2 for i in range(3))
print(f"matchs appariés {n} ; écart absolu moyen proba PM vs Pinnacle clôture {mad:.4f}")
print(f"log-loss PM {sum(ll(p, y) for p, ps, y, *_ in rows) / n:.5f} | Pinnacle {sum(ll(ps, y) for p, ps, y, *_ in rows) / n:.5f}")
print(f"Brier PM {sum(br(p, y) for p, ps, y, *_ in rows) / n:.5f} | Pinnacle {sum(br(ps, y) for p, ps, y, *_ in rows) / n:.5f}")
lags = sorted(r[3] for r in rows); print(f"délai dernier prix PM avant coup d'envoi : médiane {lags[n // 2]:.0f} min")
sums = sorted(r[4] for r in rows); print(f"somme des prix PM : médiane {sums[n // 2]:.3f}")
# différence de log-loss appariée + IC95
diffs = [ll(p, y) - ll(ps, y) for p, ps, y, *_ in rows]
m = sum(diffs) / n; sd = (sum((x - m) ** 2 for x in diffs) / (n - 1)) ** .5
print(f"Δlog-loss PM−PS = {m:+.5f} IC95 [{m - 1.96 * sd / n ** .5:+.5f} ; {m + 1.96 * sd / n ** .5:+.5f}]")
