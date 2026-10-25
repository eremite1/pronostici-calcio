"""Selezione dei pronostici migliori e costruzione delle schedine."""
import itertools

from . import config
from .model import MARGIN

REAL_KEYS = {"1": "H", "X": "D", "2": "A", "Over 2.5": "O25", "Under 2.5": "U25"}


def price(market, odds):
    """Quota da usare: reale se disponibile, altrimenti stimata dalla probabilità."""
    p = market["p"]
    fair = 1 / p if p > 0 else 999
    real = None
    if odds:
        k = REAL_KEYS.get(market["name"])
        if k and odds.get(k):
            real = odds[k]
        elif market["name"] in ("1X", "X2", "12") and odds.get("H") and odds.get("D") and odds.get("A"):
            a, b = {"1X": ("H", "D"), "X2": ("D", "A"), "12": ("H", "A")}[market["name"]]
            real = round(1 / (1 / odds[a] + 1 / odds[b]), 2)
    est = round(max(1.01, fair * (1 - MARGIN.get(market["fam"], 0.08))), 2)
    return dict(fair=round(fair, 2), real=real, est=est, used=real or est, is_real=real is not None)


def top_picks(markets, odds, n=8):
    """I pronostici più probabili della partita, vari (massimo 2 per tipo di mercato)."""
    cand = [m for m in markets if 0.50 <= m["p"] <= 0.90]
    cand.sort(key=lambda m: -m["p"])
    out, per_fam = [], {}
    for m in cand:
        if per_fam.get(m["fam"], 0) >= 2:
            continue
        pr = price(m, odds)
        if pr["used"] < 1.25:
            continue
        per_fam[m["fam"]] = per_fam.get(m["fam"], 0) + 1
        out.append(dict(m, **pr))
        if len(out) >= n:
            break
    return out


def slip_candidates(match, k=8):
    """Pronostici di una partita adatti alla schedina."""
    out = []
    for m in match["markets"]:
        if m["p"] < config.PICK_MIN_PROB or m["fam"] == "1° tempo":
            continue
        pr = price(m, match.get("odds"))
        if pr["used"] < config.PICK_MIN_ODDS:
            continue
        out.append(dict(m, **pr))
    out.sort(key=lambda m: -m["p"])
    # elimina doppioni "inutili": se un pronostico è contenuto in uno più probabile con quota simile, tieni il più probabile
    return out[:k]


def build_slips(matches, n_best=3):
    pool = [m for m in matches if m["reliability"] >= config.MIN_RELIABILITY and not m.get("started")]
    cands = {m["id"]: slip_candidates(m) for m in pool}
    pool = [m for m in pool if cands[m["id"]]]
    found = []
    for size in (2, 3):
        kk = 8 if size == 2 else 5
        for combo in itertools.combinations(pool, size):
            lists = [cands[m["id"]][:kk] for m in combo]
            for picks in itertools.product(*lists):
                q = 1.0
                for p in picks:
                    q *= p["used"]
                if not (config.SLIP_MIN_ODDS <= q <= config.SLIP_MAX_ODDS):
                    continue
                prob = 1.0
                for p in picks:
                    prob *= p["p"]
                found.append((prob, q, combo, picks))
    found.sort(key=lambda x: (-x[0], -x[1]))
    slips, used_sets = [], []
    for prob, q, combo, picks in found:
        ids = frozenset(m["id"] for m in combo)
        # schedine alternative: non ripetere esattamente le stesse partite
        # le alternative usano partite diverse dalle schedine già scelte
        if used_sets and ids & set().union(*used_sets):
            continue
        used_sets.append(ids)
        slips.append(dict(prob=prob, odds=round(q, 2), fair=round(1 / prob, 2), legs=[
            dict(match_id=m["id"], league=m["league"], flag=m["flag"], home=m["home"], away=m["away"],
                 kickoff=m["kickoff_local"], pick=p["name"], p=p["p"], odds=p["used"], is_real=p["is_real"])
            for m, p in zip(combo, picks)]))
        if len(slips) >= n_best:
            break
    return slips


def global_best(matches, n=15):
    rows = []
    for m in matches:
        if m.get("started"):
            continue
        for p in m["top"]:
            if p["used"] >= 1.30:
                rows.append(dict(p, match_id=m["id"], home=m["home"], away=m["away"], league=m["league"],
                                 flag=m["flag"], kickoff=m["kickoff_local"], reliability=m["reliability"]))
    rows.sort(key=lambda r: -r["p"])
    seen, out = {}, []
    for r in rows:
        if seen.get(r["match_id"], 0) >= 1:
            continue
        seen[r["match_id"]] = 1
        out.append(r)
        if len(out) >= n:
            break
    return out
