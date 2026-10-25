"""Statistiche delle squadre e analisi scritta di ogni partita."""
from . import names


def _avg(vals):
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


def team_stats(team, history, fd_rows, fd_name):
    """Statistiche di una squadra nella stagione in corso."""
    h = history or []
    last5 = h[-5:]
    res_map = {"w": "V", "d": "N", "l": "P"}
    s = dict(team=team, played=len(h))
    s["form"] = "".join(res_map.get(x["result"], "?") for x in last5)
    s["pts5"] = sum(3 if x["result"] == "w" else 1 if x["result"] == "d" else 0 for x in last5)
    s["gf5"] = sum(x["scored"] for x in last5)
    s["ga5"] = sum(x["missed"] for x in last5)
    s["xg"] = _avg([x["xg"] for x in h])
    s["xga"] = _avg([x["xga"] for x in h])
    s["xg5"] = _avg([x["xg"] for x in last5])
    s["xga5"] = _avg([x["xga"] for x in last5])
    s["gf"] = _avg([x["scored"] for x in h])
    s["ga"] = _avg([x["missed"] for x in h])
    for side in ("h", "a"):
        hs = [x for x in h if x["h_a"] == side]
        s[f"xg_{side}"] = _avg([x["xg"] for x in hs])
        s[f"xga_{side}"] = _avg([x["xga"] for x in hs])
        s[f"gf_{side}"] = _avg([x["scored"] for x in hs])
        s[f"ga_{side}"] = _avg([x["missed"] for x in hs])
        s[f"n_{side}"] = len(hs)
    s["ppda"] = _avg([x["ppda"] for x in h])
    s["deep"] = _avg([x["deep"] for x in h])
    s["clean"] = sum(1 for x in h if x["missed"] == 0)
    # tiri da football-data
    shots, sot, shots_ag, corners = [], [], [], []
    for r in fd_rows or []:
        if r["home"] == fd_name:
            shots.append(r["hs"]); sot.append(r["hst"]); shots_ag.append(r["as_"]); corners.append(r["hc"])
        elif r["away"] == fd_name:
            shots.append(r["as_"]); sot.append(r["ast"]); shots_ag.append(r["hs"]); corners.append(r["ac"])
    s["shots"] = _avg(shots)
    s["sot"] = _avg(sot)
    s["shots_ag"] = _avg(shots_ag)
    s["corners"] = _avg(corners)
    if s["sot"] and s["gf"] is not None and s["sot"] > 0:
        s["conv"] = s["gf"] / s["sot"] * 100
    else:
        s["conv"] = None
    return s


def form_word(pts5, n):
    if n < 3:
        return "inizio di stagione"
    if pts5 >= 12:
        return "ottima forma"
    if pts5 >= 9:
        return "buona forma"
    if pts5 >= 6:
        return "forma altalenante"
    return "momento difficile"


def f2(x, d=2):
    return "–" if x is None else f"{x:.{d}f}"


def write_analysis(m):
    """Analisi breve ma dettagliata, generata dai numeri."""
    H, A = m["home"], m["away"]
    sh, sa = m["stats_home"], m["stats_away"]
    out = []

    def form_sentence(team, s, where):
        if not s["played"]:
            return f"{team}: nessuna partita di campionato giocata finora."
        V, N, P = s["form"].count("V"), s["form"].count("N"), s["form"].count("P")
        t = f"{team} in {form_word(s['pts5'], s['played'])} ({V}V {N}N {P}P nelle ultime {len(s['form'])}, " \
            f"{s['gf5']} gol fatti e {s['ga5']} subiti)"
        if s["xg5"] is not None and s["xg"] is not None:
            diff5 = (s["xg5"] - s["xga5"])
            diffs = (s["xg"] - s["xga"])
            if diff5 > diffs + 0.3:
                t += ", prestazioni in crescita secondo gli expected goals"
            elif diff5 < diffs - 0.3:
                t += ", prestazioni in calo secondo gli expected goals"
        if s["n_" + where] >= 2 and s["xg_" + where] is not None:
            luogo = "in casa" if where == "h" else "in trasferta"
            t += f". {luogo.capitalize()} crea {f2(s['xg_' + where])} xG e ne concede {f2(s['xga_' + where])} a partita"
        return t + "."

    out.append(form_sentence(H, sh, "h"))
    out.append(form_sentence(A, sa, "a"))

    bits = []
    for team, s in ((H, sh), (A, sa)):
        if s.get("shots"):
            b = f"{team} {f2(s['shots'], 1)} tiri a partita ({f2(s['sot'], 1)} in porta)"
            if m.get("possession", {}).get(team):
                b += f", possesso medio {m['possession'][team]:.0f}%"
            if s.get("ppda"):
                b += f", pressing PPDA {f2(s['ppda'], 1)}"
            bits.append(b)
    if bits:
        out.append("Numeri: " + "; ".join(bits) + ". (PPDA basso = pressing più aggressivo.)")

    for team, key in ((H, "abs_home"), (A, "abs_away")):
        det = m.get(key, {}).get("details") or []
        heavy = [d for d in det if d.get("share") and d["share"] >= 8]
        if heavy:
            names_txt = ", ".join(f"{d['name']} ({d['share']}% della produzione offensiva)" for d in heavy[:3])
            out.append(f"Assenze pesanti per {team}: {names_txt}. "
                       f"Attacco stimato al {m[key]['att_mult'] * 100:.0f}% del normale.")
        elif m.get(key, {}).get("def_mult", 1) > 1.04:
            out.append(f"{team} perde titolari in difesa: il modello alza i gol subiti del "
                       f"{(m[key]['def_mult'] - 1) * 100:.0f}%.")
    out.append("Meteo: " + m["weather_text"])

    lh, la = m["lh"], m["la"]
    tot = lh + la
    tipo = "chiusa, da pochi gol" if tot < 2.2 else ("equilibrata nei gol" if tot < 3.0 else "aperta, da molti gol")
    p1, px, p2 = m["p1x2"]
    if max(p1, p2) < 0.40:
        fav = "nessuna favorita netta"
    elif p1 > p2:
        fav = f"{H} favorita ({p1 * 100:.0f}%)"
    else:
        fav = f"{A} favorita ({p2 * 100:.0f}%)"
    out.append(f"Sintesi: gol attesi {lh:.2f} – {la:.2f}, partita {tipo}, {fav}. "
               f"Risultato più probabile {m['exact'][0]['score']}.")
    mk = m.get("market")
    if mk:
        mod = m["p1x2_model"]
        for lab, i, k in (("1", 0, "H"), ("X", 1, "D"), ("2", 2, "A")):
            if mod[i] - mk[k] >= 0.06:
                out.append(f"Il modello vede il segno {lab} più probabile di quanto dicano le quote "
                           f"({mod[i] * 100:.0f}% contro {mk[k] * 100:.0f}% dei bookmaker): possibile valore.")
    return out


def lineup_side(game, side, team, us_team_names):
    """Estrae dalla partita trovata la parte relativa alla squadra."""
    if not game:
        return None
    return game["sides"].get(side)


def find_game(games, home, away, teams):
    for g in games or []:
        if names.match_team(g["home"], teams) == home and names.match_team(g["away"], teams) == away:
            return g
    return None
