#!/usr/bin/env python3
"""Validation : prix Polymarket ~10 min avant le coup d'envoi vs clôture Pinnacle (football-data).
Usage : python tools/pm_collect.py 10188 epl.json   (10188 = série Premier League 2025)
Requêtes publiques (Gamma + CLOB prices-history), 4 fils, pause 0,2 s."""
import json, time, urllib.request, sys
from datetime import datetime
def get(u):
    req=urllib.request.Request(u, headers={"User-Agent":"autonome/0.2"})
    with urllib.request.urlopen(req, timeout=15) as r: return json.load(r)
series=sys.argv[1]; out=sys.argv[2]
evs=[]; off=0
while True:
    d=get(f"https://gamma-api.polymarket.com/events?series_id={series}&closed=true&limit=100&offset={off}")
    if not d: break
    evs+=d; off+=100; time.sleep(0.5)
    if off>1500: break
games=[e for e in evs if ' vs. ' in e['title'] and '2025-08-01'<=e.get('startTime','')<'2026-01-15' and len(e['markets'])==3]
print(len(evs), 'games', len(games), file=sys.stderr)
from concurrent.futures import ThreadPoolExecutor
def one(e):
    st=int(datetime.fromisoformat(e['startTime'].replace('Z','+00:00')).timestamp())
    row={"title":e['title'],"start":e['startTime'],"sel":{}}
    for m in e['markets']:
        tok=json.loads(m['clobTokenIds'])[0]
        try:
            h=get(f"https://clob.polymarket.com/prices-history?market={tok}&startTs={st-6*3600}&endTs={st}&fidelity=5")["history"]
        except Exception:
            h=[]
        time.sleep(0.2)
        pts=[p for p in h if p['t']<=st-300]
        row["sel"][m.get('groupItemTitle') or m['question']]={"close":pts[-1]['p'] if pts else None,"close_t":pts[-1]['t'] if pts else None,"q":m['question']}
    return row
with ThreadPoolExecutor(4) as ex:
    res=list(ex.map(one,games))
json.dump(res,open(out,'w'))
print('done',len(res),file=sys.stderr)
