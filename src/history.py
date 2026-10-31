"""Registro storico: salva i pronostici e li verifica quando le partite sono finite."""
import datetime as dt
import glob
import json
import os

from . import config
from .model import market_outcome

PRED_DIR = os.path.join(config.DATA, "predictions")
SLIP_DIR = os.path.join(config.DATA, "schedine")


def _load(p, default):
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return default


def _save(p, obj):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def save_predictions(matches, now):
    """Per ogni partita conserva l'ultima previsione fatta PRIMA del calcio d'inizio."""
    by_day = {}
    for m in matches:
        if m.get("started"):
            continue
        by_day.setdefault(m["date_local"], []).append(m)
    for day, ms in by_day.items():
        p = os.path.join(PRED_DIR, f"{day}.json")
        d = _load(p, {})
        for m in ms:
            d[m["id"]] = dict(generated=now.isoformat(), league=m["league"], flag=m["flag"], home=m["home"],
                              away=m["away"], kickoff=m["kickoff_utc"], lh=round(m["lh"], 3), la=round(m["la"], 3),
                              fd_home=m.get("fd_home"), fd_away=m.get("fd_away"),
                              top=[dict(name=t["name"], p=round(t["p"], 4), odds=t["used"]) for t in m["top"]],
                              markets={x["name"]: round(x["p"], 4) for x in m["markets"]},
                              pengwin=({k: m["pengwin"].get(k) for k in ("market", "odds", "p", "url")}
                                       if m.get("pengwin") else None))
        _save(p, d)


def save_official_slips(slips_day, slips_window, today_local, now, slips_cross=None):
    """La schedina ufficiale di ogni tipo è la prima generata nella giornata (non si cambia dopo)."""
    p = os.path.join(SLIP_DIR, f"{today_local}.json")
    d = _load(p, None)
    if d is None:
        if not slips_day and not slips_window and not slips_cross:
            return
        d = dict(generated=now.isoformat(), giorno=slips_day[:1], prossimi=slips_window[:1])
    if slips_cross and not d.get("incrociata"):
        d["incrociata"] = slips_cross[:1]
        d["generated_incrociata"] = now.isoformat()
    _save(p, d)


def evaluate(results_by_id, ht_lookup, now=None, live_ids=()):
    """Confronta i pronostici con i risultati veri. results_by_id: id -> (gol casa, gol ospite)."""
    picks_rows, slips_rows, pengwin_rows = [], [], []
    kick = {}
    for p in sorted(glob.glob(os.path.join(PRED_DIR, "*.json")))[-120:]:
        d = _load(p, {})
        for mid, pr in d.items():
            kick[mid] = pr.get("kickoff")
            if mid not in results_by_id:
                continue
            hg, ag = results_by_id[mid]
            ht = ht_lookup(pr)
            pw = pr.get("pengwin")
            if pw and pw.get("market"):
                ok = market_outcome(pw["market"], hg, ag, *(ht or (None, None)))
                if ok is not None:
                    pengwin_rows.append(dict(day=os.path.basename(p)[:10], match=f"{pr['home']} - {pr['away']}",
                                             pick=pw["market"], odds=pw.get("odds"), p=pw.get("p"), ok=ok,
                                             score=f"{hg}-{ag}", url=pw.get("url")))
            for i, t in enumerate(pr.get("top", [])):
                ok = market_outcome(t["name"], hg, ag, *(ht or (None, None)))
                if ok is None:
                    continue
                picks_rows.append(dict(day=os.path.basename(p)[:10], match=f"{pr['home']} - {pr['away']}",
                                       league=pr["league"], pick=t["name"], p=t["p"], odds=t["odds"], ok=ok,
                                       score=f"{hg}-{ag}", first=(i == 0)))
    for p in sorted(glob.glob(os.path.join(SLIP_DIR, "*.json")))[-120:]:
        d = _load(p, {})
        day = os.path.basename(p)[:10]
        for kind in ("giorno", "prossimi", "incrociata"):
            for s in d.get(kind, [])[:1]:
                legs, done, won = [], True, True
                for leg in s["legs"]:
                    r = results_by_id.get(leg["match_id"])
                    if not r:
                        done = False
                        ko = kick.get(leg["match_id"])
                        started = False
                        if ko and now is not None:
                            try:
                                started = dt.datetime.fromisoformat(ko) <= now
                            except ValueError:
                                pass
                        if leg["match_id"] in live_ids:
                            state = "in corso"
                        elif started:
                            state = "in attesa del risultato"
                        else:
                            state = "da giocare"
                        legs.append(dict(leg, ok=None, score=None, state=state))
                        continue
                    ok = market_outcome(leg["pick"], r[0], r[1])
                    won = won and bool(ok)
                    legs.append(dict(leg, ok=ok, score=f"{r[0]}-{r[1]}", state="finita"))
                lost = any(l["ok"] is False for l in legs)
                slips_rows.append(dict(day=day, kind=kind, odds=s["odds"], prob=s["prob"], legs=legs,
                                       done=done or lost, won=(False if lost else (won if done else None))))
    # schedine identiche (giorno = prossimi) contate una volta sola
    seen, uniq = set(), []
    for s in slips_rows:
        key = (s["day"], tuple((l["match_id"], l["pick"]) for l in s["legs"]))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(s)
    return picks_rows, uniq, pengwin_rows


def _slip_stats(rows):
    done = [s for s in rows if s["done"]]
    won = [s for s in done if s["won"]]
    profit = sum((s["odds"] - 1) if s["won"] else -1 for s in done)
    return dict(n=len(done), won=len(won), rate=(len(won) / len(done) * 100) if done else None,
                exp=(sum(s["prob"] for s in done) / len(done) * 100) if done else None,
                profit=profit, roi=(profit / len(done) * 100) if done else None)


def _tip_stats(rows):
    rows = [r for r in rows if r.get("odds")]
    if not rows:
        return dict(n=0, rate=None, roi=None, profit=0)
    profit = sum((r["odds"] - 1) if r["ok"] else -1 for r in rows)
    return dict(n=len(rows), rate=sum(r["ok"] for r in rows) / len(rows) * 100, profit=profit,
                roi=profit / len(rows) * 100, avg_odds=sum(r["odds"] for r in rows) / len(rows))


def summarize(picks_rows, slips_rows, pengwin_rows=()):
    buckets = [(0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.01)]
    cal = []
    for lo, hi in buckets:
        rows = [r for r in picks_rows if lo <= r["p"] < hi]
        if rows:
            cal.append(dict(label=f"{int(lo * 100)}-{min(100, int(hi * 100))}%", n=len(rows),
                            expected=sum(r["p"] for r in rows) / len(rows) * 100,
                            actual=sum(r["ok"] for r in rows) / len(rows) * 100))
    cross = [s for s in slips_rows if s["kind"] == "incrociata"]
    slips_rows = [s for s in slips_rows if s["kind"] != "incrociata"]
    done = [s for s in slips_rows if s["done"]]
    won = [s for s in done if s["won"]]
    profit = sum((s["odds"] - 1) if s["won"] else -1 for s in done)
    firsts = [r for r in picks_rows if r["first"]]
    return dict(cal=cal, n_picks=len(picks_rows), n_slips=len(done), won=len(won),
                rate=(len(won) / len(done) * 100) if done else None,
                exp_rate=(sum(s["prob"] for s in done) / len(done) * 100) if done else None,
                profit=profit, roi=(profit / len(done) * 100) if done else None,
                first_rate=(sum(r["ok"] for r in firsts) / len(firsts) * 100) if firsts else None,
                n_first=len(firsts),
                recent_slips=list(reversed(slips_rows))[:30], recent_picks=list(reversed(picks_rows))[:60],
                cross=_slip_stats(cross), recent_cross=list(reversed(cross))[:20],
                pengwin=_tip_stats(pengwin_rows),
                pengwin_agree=_tip_stats([r for r in pengwin_rows if (r.get("p") or 0) >= 0.60]),
                pengwin_disagree=_tip_stats([r for r in pengwin_rows if r.get("p") is not None and r["p"] < 0.50]),
                recent_pengwin=list(reversed(list(pengwin_rows)))[:40])
