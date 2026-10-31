"""Verifica sul passato: pronostici di Pengwin da soli e incrociati con il nostro modello.

Uso: python -m tools.backtest_pengwin ARCHIVIO_PENGWIN.jsonl PREVISIONI_BACKTEST.json
"""
import collections
import datetime as dt
import itertools
import json
import sys

from src import model, tipster

PATH2US = {"serie-a": "Serie_A", "premier-league": "EPL", "la-liga": "La_liga", "bundesliga": "Bundesliga",
           "ligue-1": "Ligue_1"}


def roi(rows):
    rows = [r for r in rows if r["odds"]]
    if not rows:
        return dict(n=0)
    prof = sum((r["odds"] - 1) if r["ok"] else -1 for r in rows)
    return dict(n=len(rows), hit=round(sum(r["ok"] for r in rows) / len(rows) * 100, 1),
                odds=round(sum(r["odds"] for r in rows) / len(rows), 2), roi=round(prof / len(rows) * 100, 1),
                exp=round(sum(r["p"] for r in rows) / len(rows) * 100, 1) if all(r.get("p") for r in rows) else None)


def main(tips_file, preds_file):
    preds = json.load(open(preds_file))
    by_league = collections.defaultdict(list)
    lg_of = {}
    for p in preds:
        p["dt"] = dt.datetime.fromisoformat(p["when"])
        key = (p["home"], p["away"])
        by_league[key].append(p)
    teams_all = sorted({p["home"] for p in preds} | {p["away"] for p in preds})
    tips = [json.loads(l) for l in open(tips_file, encoding="utf-8")]
    stats = collections.Counter()
    rows = []
    for t in tips:
        stats["articoli"] += 1
        lg = next((v for k, v in PATH2US.items() if f"/calcio/{k}/" in t["url"]), None)
        ht = tipster.split_title(t.get("title", ""), teams_all)
        if not ht:
            stats["titolo non abbinato"] += 1
            continue
        pub = t.get("published") or t["lastmod"][:10]
        try:
            pubd = dt.date.fromisoformat(pub)
        except ValueError:
            continue
        cands = [p for p in by_league.get(ht, []) if -2 <= (p["dt"].date() - pubd).days <= 10]
        if not cands:
            stats["partita fuori dal periodo verificabile"] += 1
            continue
        p = min(cands, key=lambda x: abs((x["dt"].date() - pubd).days))
        mk, odds = tipster.parse_tip(t.get("tip", ""), t.get("bold", []), p["home"], p["away"])
        if not mk:
            stats["pronostico non calcolabile (corner, cartellini...)"] += 1
            continue
        if not odds or not (1.05 <= odds <= 10):
            stats["quota mancante"] += 1
            continue
        ok = model.market_outcome(mk, p["hg"], p["ag"])
        if ok is None:
            stats["esito non verificabile (1° tempo)"] += 1
            continue
        o = p.get("odds") or {}
        lh, la = p["lh"], p["la"]
        if o.get("H") and o.get("D") and o.get("A"):
            lh, la, _ = model.blend_with_market(lh, la, dict(H=o["H"], D=o["D"], A=o["A"], O25=o.get("O"),
                                                             U25=o.get("U")), weight=0.85)
        M = model.score_matrix(lh, la, rho=-0.10)
        prob = model.prob_of(mk, M)
        if prob is None:
            stats["mercato non calcolabile"] += 1
            continue
        stats["verificati"] += 1
        rows.append(dict(day=p["when"][:10], match=f"{p['home']}-{p['away']}", id=p["home"] + p["away"] + p["when"],
                         pick=mk, odds=odds, ok=bool(ok), p=prob, league=lg))
    print("Riepilogo lettura:", dict(stats))
    print("\nPENGWIN, tutti i pronostici verificabili:", roi(rows))
    for lab, lo, hi in (("modello contrario (<50%)", 0, 0.5), ("tiepido (50-60%)", 0.5, 0.6),
                        ("d'accordo (60-70%)", 0.6, 0.7), ("molto d'accordo (>=70%)", 0.7, 1.01)):
        print(f"  {lab:28s}", roi([r for r in rows if lo <= r["p"] < hi]))
    print("  con valore secondo il modello (p x quota > 1):", roi([r for r in rows if r["p"] * r["odds"] > 1]))
    print("\nPer campionato:")
    for lg in sorted({r["league"] for r in rows}):
        print(f"  {lg:12s}", roi([r for r in rows if r["league"] == lg]))
    print("\nPer stagione:")
    for y in ("2023", "2024", "2025", "2026"):
        rr = [r for r in rows if (r["day"][:4] == y and r["day"][5:7] >= "07") or (r["day"][:4] == str(int(y) + 1) and r["day"][5:7] < "07")]
        print(f"  {y}-{int(y) + 1}", roi(rr))
    # schedine incrociate: ogni giorno la combinazione più probabile di 2-3 pronostici approvati, quota 2-3
    byday = collections.defaultdict(list)
    for r in rows:
        if r["p"] >= 0.60:
            byday[r["day"]].append(r)
    for label, filt in (("incrociata (p>=60%)", lambda r: True), ("solo Pengwin, migliori quote basse", None)):
        slips = []
        for d, rs in sorted(byday.items()) if filt else []:
            best = None
            for k in (2, 3):
                for c in itertools.combinations(rs, k):
                    if len({x["id"] for x in c}) < k:
                        continue
                    q = 1
                    pr = 1
                    for x in c:
                        q *= x["odds"]
                        pr *= x["p"]
                    if 2 <= q <= 3 and (not best or pr > best[0]):
                        best = (pr, q, all(x["ok"] for x in c))
            if best:
                slips.append(dict(p=best[0], odds=best[1], ok=best[2]))
        if slips:
            print(f"\nSchedine {label}:", roi(slips))
    json.dump(rows, open("pengwin_backtest_rows.json", "w"))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
