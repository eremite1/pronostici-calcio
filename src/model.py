"""Il motore matematico: forza delle squadre, gol attesi, probabilità di ogni mercato."""
import math
import re

import numpy as np
from scipy.optimize import minimize
from scipy.stats import poisson

from . import config

MAXG = 10


# ------------------------------------------------------------------ forza attacco/difesa

def fit_ratings(matches, current_teams, ref_date, prev_teams=None):
    """Regressione di Poisson pesata nel tempo su un mix di expected goals e gol reali.

    matches: lista di dict con when, home, away, hxg, axg, hg, ag (solo partite giocate)
    Restituisce dict con mu (livello medio), home (vantaggio casa), att/def per squadra.
    """
    teams = sorted(set(current_teams) | {m["home"] for m in matches} | {m["away"] for m in matches})
    idx = {t: i for i, t in enumerate(teams)}
    n = len(teams)
    prev_teams = set(prev_teams or [])
    prior_att = np.zeros(n)
    prior_def = np.zeros(n)
    for t in current_teams:
        if prev_teams and t not in prev_teams:  # neopromossa: nessun dato nel campionato l'anno scorso
            prior_att[idx[t]], prior_def[idx[t]] = config.PROMOTED_PRIOR

    if not matches:
        return dict(mu=math.log(1.35), home=0.2, att={t: prior_att[idx[t]] for t in teams},
                    defe={t: prior_def[idx[t]] for t in teams}, n=0)

    hi = np.array([idx[m["home"]] for m in matches])
    ai = np.array([idx[m["away"]] for m in matches])
    xw = config.XG_WEIGHT
    yh = np.array([xw * m["hxg"] + (1 - xw) * m["hg"] for m in matches])
    ya = np.array([xw * m["axg"] + (1 - xw) * m["ag"] for m in matches])
    age = np.array([max(0.0, (ref_date - m["when"]).total_seconds() / 86400) for m in matches])
    w = 0.5 ** (age / config.HALF_LIFE_DAYS)
    r = config.RIDGE

    def loss(p):
        mu, home = p[0], p[1]
        att, de = p[2:2 + n], p[2 + n:]
        eh = mu + home + att[hi] - de[ai]
        ea = mu + att[ai] - de[hi]
        lh, la = np.exp(eh), np.exp(ea)
        L = np.sum(w * (lh - yh * eh)) + np.sum(w * (la - ya * ea))
        L += 0.5 * r * (np.sum((att - prior_att) ** 2) + np.sum((de - prior_def) ** 2))
        gh, ga = w * (lh - yh), w * (la - ya)
        g = np.zeros_like(p)
        g[0] = gh.sum() + ga.sum()
        g[1] = gh.sum()
        gatt = np.zeros(n)
        gdef = np.zeros(n)
        np.add.at(gatt, hi, gh)
        np.add.at(gatt, ai, ga)
        np.add.at(gdef, ai, -gh)
        np.add.at(gdef, hi, -ga)
        g[2:2 + n] = gatt + r * (att - prior_att)
        g[2 + n:] = gdef + r * (de - prior_def)
        return L, g

    p0 = np.zeros(2 + 2 * n)
    p0[0] = math.log(max(0.5, (yh.mean() + ya.mean()) / 2))
    p0[1] = 0.2
    res = minimize(loss, p0, jac=True, method="L-BFGS-B")
    p = res.x
    return dict(mu=float(p[0]), home=float(p[1]),
                att={t: float(p[2 + idx[t]]) for t in teams},
                defe={t: float(p[2 + n + idx[t]]) for t in teams}, n=len(matches))


def base_lambdas(rt, home, away):
    lh = math.exp(rt["mu"] + rt["home"] + rt["att"].get(home, 0) - rt["defe"].get(away, 0))
    la = math.exp(rt["mu"] + rt["att"].get(away, 0) - rt["defe"].get(home, 0))
    return lh, la


# ------------------------------------------------------------------ matrice dei risultati

def score_matrix(lh, la, rho=config.DC_RHO, maxg=MAXG):
    i = np.arange(maxg + 1)
    ph = poisson.pmf(i, lh)
    pa = poisson.pmf(i, la)
    M = np.outer(ph, pa)
    # correzione Dixon-Coles sui risultati 0-0, 1-0, 0-1, 1-1
    M[0, 0] *= max(0.0, 1 - lh * la * rho)
    M[0, 1] *= max(0.0, 1 + lh * rho)
    M[1, 0] *= max(0.0, 1 + la * rho)
    M[1, 1] *= max(0.0, 1 - rho)
    return M / M.sum()


def p1x2(M):
    return float(np.tril(M, -1).sum()), float(np.trace(M)), float(np.triu(M, 1).sum())


def p_over(M, line):
    i = np.arange(M.shape[0])
    tot = i[:, None] + i[None, :]
    return float(M[tot > line].sum())


def blend_with_market(lh, la, odds, weight=config.MARKET_WEIGHT):
    """Avvicina i gol attesi del modello a quelli impliciti nelle quote reali (se ci sono)."""
    if not odds or not odds.get("H") or not odds.get("D") or not odds.get("A"):
        return lh, la, None
    inv = np.array([1 / odds["H"], 1 / odds["D"], 1 / odds["A"]])
    mk = inv / inv.sum()  # probabilità implicite senza il margine del bookmaker
    mko = None
    if odds.get("O25") and odds.get("U25"):
        io = np.array([1 / odds["O25"], 1 / odds["U25"]])
        mko = float(io[0] / io.sum())
    M0 = score_matrix(lh, la)
    pm = np.array(p1x2(M0))
    target = (1 - weight) * pm + weight * mk
    pmo = p_over(M0, 2.5)
    tgt_o = (1 - weight) * pmo + weight * mko if mko is not None else None

    def err(x):
        M = score_matrix(math.exp(x[0]), math.exp(x[1]))
        e = np.sum((np.array(p1x2(M)) - target) ** 2)
        if tgt_o is not None:
            e += (p_over(M, 2.5) - tgt_o) ** 2
        return e

    res = minimize(err, [math.log(lh), math.log(la)], method="Nelder-Mead",
                   options=dict(xatol=1e-4, fatol=1e-8, maxiter=400))
    market = dict(H=float(mk[0]), D=float(mk[1]), A=float(mk[2]), O25=mko)
    return math.exp(res.x[0]), math.exp(res.x[1]), market


# ------------------------------------------------------------------ effetti di meteo e assenze

def weather_effect(w):
    """Moltiplicatore dei gol attesi e spiegazione in italiano."""
    if not w:
        return 1.0, "Previsioni meteo non disponibili."
    mult, notes = 1.0, []
    rain, snow, wind, temp = w.get("rain") or 0, w.get("snow") or 0, w.get("wind") or 0, w.get("temp")
    if snow > 0.1:
        mult *= 0.92
        notes.append("neve prevista: campo pesante, gioco rallentato")
    if rain >= 4:
        mult *= 0.94
        notes.append(f"pioggia forte ({rain:.1f} mm/h): campo pesante e più errori tecnici")
    elif rain >= 1:
        mult *= 0.97
        notes.append(f"pioggia moderata ({rain:.1f} mm/h): palla più veloce, qualche errore in più")
    elif rain >= 0.2:
        notes.append(f"pioggia debole ({rain:.1f} mm/h), effetto trascurabile")
    if wind >= 45:
        mult *= 0.94
        notes.append(f"vento molto forte ({wind:.0f} km/h): lanci lunghi e cross imprecisi")
    elif wind >= 30:
        mult *= 0.97
        notes.append(f"vento sostenuto ({wind:.0f} km/h): precisione ridotta su lanci e tiri da fuori")
    if temp is not None and temp >= 30:
        mult *= 0.97
        notes.append(f"caldo intenso ({temp:.0f}°C): ritmo più basso")
    elif temp is not None and temp <= -2:
        mult *= 0.98
        notes.append(f"freddo intenso ({temp:.0f}°C)")
    mult = max(0.86, mult)
    base = f"{temp:.0f}°C, vento {wind:.0f} km/h, pioggia {rain:.1f} mm/h" if temp is not None else ""
    if not notes:
        txt = f"Condizioni buone ({base}): nessun effetto sul gioco."
    else:
        eff = (1 - mult) * 100
        txt = f"{base}. " + "; ".join(n[0].upper() + n[1:] for n in notes) + "."
        txt += f" Il modello riduce i gol attesi del {eff:.0f}%." if eff >= 0.5 else " Nessuna correzione."
    return mult, txt


STATUS_WEIGHT = {"OUT": 1.0, "SQUAL": 1.0, "SUS": 1.0, "SUSP": 1.0, "QUES": 0.5, "GTD": 0.5, "DTD": 0.5}


def absence_effect(absent, team_players, team_games):
    """Quanto pesano gli assenti: (moltiplicatore attacco, moltiplicatore gol subiti, dettagli)."""
    from .names import match_player
    tot = sum(float(p["npxG"]) + 0.7 * float(p["xA"]) for p in team_players) or 1.0
    att_loss, def_pen, details = 0.0, 0.0, []
    for a in absent:
        wgt = STATUS_WEIGHT.get(a["status"].upper(), 0.5 if "DOUBT" in a["status"].upper() else 1.0)
        p = match_player(a["name"], team_players)
        if not p:
            details.append(dict(name=a["name"], status=a["status"], desc=a.get("desc", ""), share=None, role=""))
            continue
        share = (float(p["npxG"]) + 0.7 * float(p["xA"])) / tot
        minutes_share = float(p["time"]) / max(1.0, team_games * 90.0)
        pos = (p.get("position") or "").upper()
        role = "portiere" if "GK" in pos else ("difensore" if "D" in pos.split() else (
            "centrocampista" if "M" in pos.split() else ("attaccante" if "F" in pos.split() else "")))
        att_loss += wgt * share
        if minutes_share > 0.55:
            if "GK" in pos:
                def_pen += wgt * 0.07
            elif "D" in pos.split():
                def_pen += wgt * 0.035
            elif "M" in pos.split():
                def_pen += wgt * 0.015
        details.append(dict(name=p["player_name"], status=a["status"], desc=a.get("desc", ""),
                            share=round(share * 100), minutes=round(minutes_share * 100), role=role,
                            goals=int(p["goals"]), xg=round(float(p["xG"]), 1)))
    att_mult = max(0.78, 1 - 0.45 * att_loss)
    def_mult = 1 + min(0.15, def_pen)
    details.sort(key=lambda d: -(d["share"] or 0))
    return att_mult, def_mult, details


# ------------------------------------------------------------------ mercati

MARKETS = []  # (nome, famiglia, funzione(gol_casa, gol_ospite) -> vero/falso)


def _add(name, fam, fn):
    MARKETS.append((name, fam, fn))


def _build():
    _add("1", "1X2", lambda h, a: h > a)
    _add("X", "1X2", lambda h, a: h == a)
    _add("2", "1X2", lambda h, a: h < a)
    _add("1X", "Doppia chance", lambda h, a: h >= a)
    _add("X2", "Doppia chance", lambda h, a: h <= a)
    _add("12", "Doppia chance", lambda h, a: h != a)
    for ln in (0.5, 1.5, 2.5, 3.5, 4.5, 5.5):
        _add(f"Over {ln}", "Under/Over", lambda h, a, ln=ln: h + a > ln)
        _add(f"Under {ln}", "Under/Over", lambda h, a, ln=ln: h + a < ln)
    _add("Goal", "Goal/No Goal", lambda h, a: h > 0 and a > 0)
    _add("No Goal", "Goal/No Goal", lambda h, a: h == 0 or a == 0)
    for lo, hi in [(1, 2), (1, 3), (1, 4), (1, 5), (1, 6), (2, 3), (2, 4), (2, 5), (2, 6), (3, 4), (3, 5),
                   (3, 6), (4, 5), (4, 6), (5, 6)]:
        _add(f"Multigol {lo}-{hi}", "Multigol", lambda h, a, lo=lo, hi=hi: lo <= h + a <= hi)
    _add("Multigol 7+", "Multigol", lambda h, a: h + a >= 7)
    for side, idx, fam in (("casa", 0, "Multigol casa"), ("ospite", 1, "Multigol ospite")):
        for lo, hi in [(0, 1), (1, 2), (1, 3), (1, 4), (2, 3), (2, 4), (3, 4)]:
            _add(f"Multigol {side} {lo}-{hi}", fam,
                 lambda h, a, lo=lo, hi=hi, idx=idx: lo <= (h, a)[idx] <= hi)
        fam2 = "Gol " + side
        for ln in (0.5, 1.5, 2.5):
            _add(f"{side.capitalize()} Over {ln}", fam2, lambda h, a, ln=ln, idx=idx: (h, a)[idx] > ln)
            _add(f"{side.capitalize()} Under {ln}", fam2, lambda h, a, ln=ln, idx=idx: (h, a)[idx] < ln)
    esiti = {"1": lambda h, a: h > a, "X": lambda h, a: h == a, "2": lambda h, a: h < a,
             "1X": lambda h, a: h >= a, "X2": lambda h, a: h <= a, "12": lambda h, a: h != a}
    seconds = {"Over 1.5": lambda h, a: h + a > 1.5, "Over 2.5": lambda h, a: h + a > 2.5,
               "Under 2.5": lambda h, a: h + a < 2.5, "Under 3.5": lambda h, a: h + a < 3.5,
               "Under 4.5": lambda h, a: h + a < 4.5, "Goal": lambda h, a: h > 0 and a > 0,
               "No Goal": lambda h, a: h == 0 or a == 0, "Multigol 1-3": lambda h, a: 1 <= h + a <= 3,
               "Multigol 2-4": lambda h, a: 2 <= h + a <= 4, "Multigol 1-4": lambda h, a: 1 <= h + a <= 4}
    for e, fe in esiti.items():
        for s, fs in seconds.items():
            _add(f"{e} + {s}", "Combo", lambda h, a, fe=fe, fs=fs: fe(h, a) and fs(h, a))
    for s1, f1 in (("Goal", seconds["Goal"]), ("No Goal", seconds["No Goal"])):
        for s2, f2 in (("Over 2.5", seconds["Over 2.5"]), ("Under 2.5", seconds["Under 2.5"]),
                       ("Under 3.5", seconds["Under 3.5"]), ("Over 1.5", seconds["Over 1.5"])):
            _add(f"{s1} + {s2}", "Combo", lambda h, a, f1=f1, f2=f2: f1(h, a) and f2(h, a))
    _add("Pari", "Pari/Dispari", lambda h, a: (h + a) % 2 == 0)
    _add("Dispari", "Pari/Dispari", lambda h, a: (h + a) % 2 == 1)


_build()

HT_MARKETS = [
    ("1° tempo 1", "1° tempo", lambda h, a: h > a),
    ("1° tempo X", "1° tempo", lambda h, a: h == a),
    ("1° tempo 2", "1° tempo", lambda h, a: h < a),
    ("1° tempo Over 0.5", "1° tempo", lambda h, a: h + a > 0.5),
    ("1° tempo Under 1.5", "1° tempo", lambda h, a: h + a < 1.5),
    ("1° tempo Over 1.5", "1° tempo", lambda h, a: h + a > 1.5),
]

MARGIN = {"1X2": 0.05, "Doppia chance": 0.05, "Under/Over": 0.06, "Goal/No Goal": 0.06,
          "Gol casa": 0.08, "Gol ospite": 0.08, "Multigol": 0.10, "Multigol casa": 0.10,
          "Multigol ospite": 0.10, "Combo": 0.10, "Pari/Dispari": 0.06, "1° tempo": 0.08}

_MASKS = {}


def _mask(fn, size):
    key = (id(fn), size)
    if key not in _MASKS:
        _MASKS[key] = np.array([[1.0 if fn(h, a) else 0.0 for a in range(size)] for h in range(size)])
    return _MASKS[key]


def all_markets(M, Mht):
    out = []
    for name, fam, fn in MARKETS:
        out.append(dict(name=name, fam=fam, p=float((M * _mask(fn, M.shape[0])).sum())))
    for name, fam, fn in HT_MARKETS:
        out.append(dict(name=name, fam=fam, p=float((Mht * _mask(fn, Mht.shape[0])).sum())))
    return out


def market_outcome(name, hg, ag, hthg=None, htag=None):
    if not name.startswith("1° tempo"):
        fn = outcome_fn(name)
        return bool(fn(hg, ag)) if fn else None
    for n, _, fn in HT_MARKETS:
        if n == name:
            if hthg is None or htag is None:
                return None
            return bool(fn(int(hthg), int(htag)))
    return None


def goal_range(lmbda_row):
    """Intervallo di gol più stretto che copre almeno il 70% delle probabilità."""
    p = np.asarray(lmbda_row)
    best = None
    for lo in range(len(p)):
        for hi in range(lo, len(p)):
            s = p[lo:hi + 1].sum()
            if s >= 0.70:
                if best is None or (hi - lo) < (best[1] - best[0]) or ((hi - lo) == (best[1] - best[0]) and s > best[2]):
                    best = (lo, hi, s)
                break
    return best


# ------------------------------------------------------------------ mercati generici (per i pronostici dei tipster)

def outcome_fn(name):
    """Funzione (gol casa, gol ospite) -> vero/falso per qualunque nome di mercato del sistema, anche combinato."""
    for n, _, fn in MARKETS:
        if n == name:
            return fn
    if " o " in name:
        fs = [outcome_fn(x) for x in name.split(" o ")]
        if all(fs):
            return lambda h, a, fs=fs: any(f(h, a) for f in fs)
        return None
    if " + " in name:
        fs = [outcome_fn(x) for x in name.split(" + ")]
        if all(fs):
            return lambda h, a, fs=fs: all(f(h, a) for f in fs)
        return None
    m = re.match(r"^Multigol (casa |ospite )?(\d)-(\d)$", name)
    if m:
        lo, hi, side = int(m.group(2)), int(m.group(3)), (m.group(1) or "").strip()
        if side == "casa":
            return lambda h, a: lo <= h <= hi
        if side == "ospite":
            return lambda h, a: lo <= a <= hi
        return lambda h, a: lo <= h + a <= hi
    m = re.match(r"^(Casa |Ospite )?(Over|Under) (\d\.5)$", name)
    if m:
        ln, ou, side = float(m.group(3)), m.group(2), (m.group(1) or "").strip()
        val = (lambda h, a: h) if side == "Casa" else ((lambda h, a: a) if side == "Ospite" else (lambda h, a: h + a))
        return (lambda h, a: val(h, a) > ln) if ou == "Over" else (lambda h, a: val(h, a) < ln)
    return None


def prob_of(name, M, Mht=None):
    if name.startswith("1° tempo"):
        if name in ("1° tempo Under 0.5",):
            return float(Mht[0, 0]) if Mht is not None else None
        for n, _, fn in HT_MARKETS:
            if n == name and Mht is not None:
                return float((Mht * _mask(fn, Mht.shape[0])).sum())
        return None
    fn = outcome_fn(name)
    if not fn:
        return None
    return float((M * _mask(fn, M.shape[0])).sum())
