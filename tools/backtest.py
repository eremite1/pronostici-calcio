"""Taratura e verifica del modello sulle stagioni passate (walk-forward: solo dati disponibili prima di ogni partita).

Uso: python -m tools.backtest CARTELLA_ARCHIVIO
"""
import csv
import datetime as dt
import io
import itertools
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src import config, model, names  # noqa: E402

UTC = dt.timezone.utc
LEAGUES = {"Serie_A": "I1", "EPL": "E0", "La_liga": "SP1", "Bundesliga": "D1", "Ligue_1": "F1"}


def f(x):
    try:
        return float(x) if x not in (None, "") else None
    except ValueError:
        return None


def load(arch):
    data = {}
    for lg, fd in LEAGUES.items():
        seasons = {}
        for y in range(2019, 2027):
            p = os.path.join(arch, f"us_{lg}_{y}.json")
            if not os.path.exists(p):
                continue
            d = json.load(open(p))
            ms = []
            for m in d.get("dates", []):
                if not m.get("isResult"):
                    continue
                ms.append(dict(when=dt.datetime.strptime(m["datetime"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC),
                               home=m["h"]["title"], away=m["a"]["title"], hg=int(m["goals"]["h"]),
                               ag=int(m["goals"]["a"]), hxg=float(m["xG"]["h"]), axg=float(m["xG"]["a"])))
            teams = sorted(t["title"] for t in d["teams"].values())
            # quote
            odds = {}
            pf = os.path.join(arch, f"fd_{fd}_{y}.csv")
            if os.path.exists(pf):
                txt = open(pf, encoding="utf-8", errors="replace").read().replace("ï»¿", "").lstrip("﻿")
                for r in csv.DictReader(io.StringIO(txt)):
                    if not r.get("HomeTeam"):
                        continue
                    h, a = names.match_team(r["HomeTeam"], teams), names.match_team(r["AwayTeam"], teams)
                    if not h or not a:
                        continue
                    g = lambda *ks: next((f(r.get(k)) for k in ks if f(r.get(k))), None)
                    odds[(h, a)] = dict(
                        H=g("AvgH", "BbAvH", "B365H"), D=g("AvgD", "BbAvD", "B365D"), A=g("AvgA", "BbAvA", "B365A"),
                        O=g("Avg>2.5", "BbAv>2.5", "B365>2.5"), U=g("Avg<2.5", "BbAv<2.5", "B365<2.5"),
                        mH=g("MaxH", "BbMxH"), mD=g("MaxD", "BbMxD"), mA=g("MaxA", "BbMxA"),
                        mO=g("Max>2.5", "BbMx>2.5"), mU=g("Max<2.5", "BbMx<2.5"),
                        cH=g("AvgCH", "B365CH"), cD=g("AvgCD", "B365CD"), cA=g("AvgCA", "B365CA"),
                        cO=g("AvgC>2.5", "B365C>2.5"), cU=g("AvgC<2.5", "B365C<2.5"))
            seasons[y] = dict(matches=ms, teams=teams, odds=odds)
        data[lg] = seasons
    return data


def predict_season(seasons, y, params):
    """Previsioni per tutte le partite della stagione y (fit una volta a settimana)."""
    cur, prev = seasons[y], seasons.get(y - 1)
    ms = sorted(cur["matches"], key=lambda m: m["when"])
    out = []
    old = dict(XG_WEIGHT=config.XG_WEIGHT, HALF_LIFE_DAYS=config.HALF_LIFE_DAYS, RIDGE=config.RIDGE)
    for k, v in params.items():
        if k in old:
            setattr(config, k, v)
    try:
        weeks = {}
        for m in ms:
            weeks.setdefault(m["when"].isocalendar()[:2], []).append(m)
        for wk, group in sorted(weeks.items()):
            ref = min(m["when"] for m in group) - dt.timedelta(hours=1)
            hist = [m for m in ms if m["when"] < ref] + (prev["matches"] if prev else [])
            rt = model.fit_ratings(hist, cur["teams"], ref, prev["teams"] if prev else [])
            for m in group:
                lh, la = model.base_lambdas(rt, m["home"], m["away"])
                out.append(dict(m, lh=lh, la=la, nplayed=sum(1 for x in ms if x["when"] < ref),
                                odds=cur["odds"].get((m["home"], m["away"]))))
    finally:
        for k, v in old.items():
            setattr(config, k, v)
    return out


def probs(lh, la, rho):
    M = model.score_matrix(lh, la, rho=rho)
    p1, px, p2 = model.p1x2(M)
    return np.array([p1, px, p2]), model.p_over(M, 2.5), M


def implied(o, keys):
    vals = [o.get(k) for k in keys]
    if not all(vals):
        return None
    inv = np.array([1 / v for v in vals])
    return inv / inv.sum()


def scores(preds, rho=config.DC_RHO, market_w=0.0, min_played=4):
    ll1, llo, llm1, llmo, n = 0.0, 0.0, 0.0, 0.0, 0
    for p in preds:
        o = p["odds"]
        if p["nplayed"] < min_played or not o:
            continue
        mk = implied(o, ["H", "D", "A"])
        mo = implied(o, ["O", "U"])
        if mk is None or mo is None:
            continue
        lh, la = p["lh"], p["la"]
        if market_w > 0:
            lh, la, _ = model.blend_with_market(lh, la, o and dict(H=o["H"], D=o["D"], A=o["A"], O25=o["O"], U25=o["U"]),
                                                weight=market_w)
        pr, po, _ = probs(lh, la, rho)
        res = 0 if p["hg"] > p["ag"] else (1 if p["hg"] == p["ag"] else 2)
        ov = (p["hg"] + p["ag"]) > 2.5
        ll1 -= math.log(max(1e-9, pr[res]))
        llo -= math.log(max(1e-9, po if ov else 1 - po))
        llm1 -= math.log(max(1e-9, mk[res]))
        llmo -= math.log(max(1e-9, mo[0] if ov else mo[1]))
        n += 1
    return dict(n=n, ll1x2=ll1 / n, llou=llo / n, mk_ll1x2=llm1 / n, mk_llou=llmo / n)


def main(arch):
    data = load(arch)
    test_years = [2023, 2024, 2025]
    print("Partite per stagione:", {lg: {y: len(s["matches"]) for y, s in ss.items()} for lg, ss in data.items()})
    grid = dict(XG_WEIGHT=[0.5, 0.7, 0.85, 1.0], HALF_LIFE_DAYS=[90, 150, 250, 400], RIDGE=[2.0, 4.0, 8.0])
    results = []
    cache = {}
    for combo in itertools.product(*grid.values()):
        params = dict(zip(grid.keys(), combo))
        preds = []
        for lg, ss in data.items():
            for y in test_years:
                if y in ss:
                    preds += predict_season(ss, y, params)
        sc = scores(preds)
        results.append((sc["ll1x2"] + sc["llou"], params, sc))
        cache[combo] = preds
        print(params, {k: round(v, 4) if isinstance(v, float) else v for k, v in sc.items()}, flush=True)
    results.sort(key=lambda r: r[0])
    best = results[0]
    print("\nMIGLIORE:", best[1], best[2])
    cur = (config.XG_WEIGHT, config.HALF_LIFE_DAYS, config.RIDGE)
    print("ATTUALE:", [r for r in results if tuple(r[1].values()) == cur][0][2])
    preds = cache[tuple(best[1].values())]
    out = dict(best=best[1], best_scores=best[2], grid=[(r[1], r[2]) for r in results])
    for rho in [0.0, -0.03, -0.06, -0.1, -0.13]:
        s = scores(preds, rho=rho)
        print("rho", rho, round(s["ll1x2"], 4), round(s["llou"], 4))
    for w in [0.0, 0.3, 0.5, 0.7, 0.85, 1.0]:
        s = scores(preds, market_w=w)
        print("peso quote", w, round(s["ll1x2"], 4), round(s["llou"], 4), "| mercato", round(s["mk_ll1x2"], 4),
              round(s["mk_llou"], 4))
    with open(os.path.join(arch, "..", "backtest_preds.json"), "w") as fh:
        json.dump([dict(p, when=p["when"].isoformat()) for p in preds], fh)
    with open(os.path.join(arch, "..", "backtest_grid.json"), "w") as fh:
        json.dump(out, fh, indent=1)


if __name__ == "__main__":
    main(sys.argv[1])
