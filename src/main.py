"""Programma principale: raccoglie i dati, calcola i pronostici e crea la pagina web."""
import datetime as dt
import json
import os
import sys
import traceback
from zoneinfo import ZoneInfo

import numpy as np

from . import analysis, config, history, model, names, picks, report, sources
from .fetch import WARNINGS, warn

ROME = ZoneInfo(config.TZ)
GIORNI = ["lun", "mar", "mer", "gio", "ven", "sab", "dom"]


def local_label(when):
    l = when.astimezone(ROME)
    return f"{GIORNI[l.weekday()]} {l:%d/%m %H:%M}"


def players_by_team(data):
    out = {}
    for p in (data or {}).get("players", []):
        for t in str(p.get("team_title", "")).split(","):
            out.setdefault(t.strip(), []).append(p)
    return out


def run():
    now = dt.datetime.now(dt.timezone.utc)
    today_local = now.astimezone(ROME).date()
    season = config.season_start_year(today_local)
    horizon = now + dt.timedelta(days=config.DAYS_AHEAD)
    all_matches, results_by_id, fd_index, league_status = [], {}, {}, []
    possession_budget = [300]

    for L in config.LEAGUES:
        print(f"\n=== {L['name']}")
        st = dict(name=L["name"], flag=L["flag"], ok=True, notes=[])
        league_status.append(st)
        try:
            cur = sources.understat_league(L["understat"], season)
            if not cur:
                warn(f"{L['name']}: dati Understat non disponibili, campionato saltato")
                st["ok"] = False
                continue
            prev = sources.understat_league(L["understat"], season - 1, use_cache=True)
            cur_m = sources.understat_matches(cur)
            prev_m = sources.understat_matches(prev)
            teams = sorted(t["title"] for t in cur["teams"].values())
            prev_teams = sorted(t["title"] for t in (prev or {}).get("teams", {}).values())
            played = [m for m in cur_m + prev_m if m["played"]]
            for m in cur_m:
                if m["played"]:
                    results_by_id[m["id"]] = (m["hg"], m["ag"])
            rt = model.fit_ratings(played, teams, now, prev_teams)
            print(f"  forza squadre calcolata su {rt['n']} partite (vantaggio casa {np.exp(rt['home']):.2f}x)")
            hist = sources.understat_team_history(cur)
            pl = players_by_team(cur)

            fd_rows = sources.fd_season(L["fd"], season)
            fd_names = sorted({r["home"] for r in fd_rows} | {r["away"] for r in fd_rows})
            us2fd = {}
            for n in fd_names:
                t = names.match_team(n, teams)
                if t:
                    us2fd[t] = n
            for r in fd_rows:
                fd_index.setdefault((r["home"], r["away"]), []).append(r)
            if not fd_rows:
                st["notes"].append("tiri non disponibili")

            odds_rows = sources.fd_fixture_odds(L["fd"])
            for r in odds_rows:
                r["us_home"] = names.match_team(r["home"], teams)
                r["us_away"] = names.match_team(r["away"], teams)

            fixtures = [m for m in cur_m if not m["played"] and now < m["when"] <= horizon]
            print(f"  partite nella finestra: {len(fixtures)}")
            if not fixtures:
                continue

            # ESPN: stadio e città
            espn_ev = []
            days = sorted({(m["when"] - dt.timedelta(hours=6)).date() for m in fixtures} |
                          {m["when"].date() for m in fixtures})
            for d in days:
                espn_ev += sources.espn_events(L["espn"], d)
            for e in espn_ev:
                e["us_home"] = names.match_team(e["home"], teams)
                e["us_away"] = names.match_team(e["away"], teams)

            # formazioni e assenze
            rw = sources.rotowire(L["rotowire"], teams)
            if rw is None:
                st["notes"].append("RotoWire non disponibile")
            fc = sources.fantacalcio() if L["key"] == "serie_a" else None
            if L["key"] == "serie_a" and fc is None:
                st["notes"].append("Fantacalcio.it non disponibile")

            for fx in fixtures:
                try:
                    all_matches.append(build_match(L, fx, rt, hist, pl, fd_rows, us2fd, odds_rows, espn_ev,
                                                   rw, fc, teams, now, possession_budget))
                except Exception:
                    traceback.print_exc()
                    warn(f"Errore nell'analisi di {fx['home']} - {fx['away']}")
        except Exception:
            traceback.print_exc()
            warn(f"{L['name']}: errore imprevisto, campionato saltato")
            st["ok"] = False

    all_matches.sort(key=lambda m: m["kickoff_utc"])
    today_matches = [m for m in all_matches if m["date_local"] == today_local.isoformat()]
    slips_day = picks.build_slips(today_matches) if today_matches else []
    day_ids = [l["match_id"] for l in slips_day[0]["legs"]] if slips_day else []
    slips_window = picks.build_slips(all_matches, exclude_ids=day_ids)
    best = picks.global_best(all_matches)

    history.save_predictions(all_matches, now)
    history.save_official_slips(slips_day, slips_window, today_local.isoformat(), now)

    def ht_lookup(pr):
        rows = fd_index.get((pr.get("fd_home"), pr.get("fd_away"))) or []
        for r in rows:
            if r["hthg"] is not None:
                return (r["hthg"], r["htag"])
        return None

    picks_rows, slip_rows = history.evaluate(results_by_id, ht_lookup)
    summary = history.summarize(picks_rows, slip_rows)

    ctx = dict(generated=now.astimezone(ROME).strftime("%d/%m/%Y alle %H:%M"), today=local_label(now)[:9],
               matches=all_matches, slips_day=slips_day, slips_window=slips_window, best=best,
               leagues=league_status, warnings=WARNINGS, summary=summary,
               days_ahead=config.DAYS_AHEAD)
    report.render(ctx)
    print(f"\nFatto: {len(all_matches)} partite, {len(slips_window)} schedine, avvisi: {len(WARNINGS)}")


def build_match(L, fx, rt, hist, pl, fd_rows, us2fd, odds_rows, espn_ev, rw, fc, teams, now, budget):
    H, A = fx["home"], fx["away"]
    m = dict(id=fx["id"], league=L["name"], league_key=L["key"], flag=L["flag"], home=H, away=A,
             kickoff_utc=fx["when"].isoformat(), kickoff_local=local_label(fx["when"]),
             date_local=fx["when"].astimezone(ROME).date().isoformat(), started=False,
             fd_home=us2fd.get(H), fd_away=us2fd.get(A))
    lh0, la0 = model.base_lambdas(rt, H, A)
    m["rating"] = dict(att_h=rt["att"].get(H, 0), def_h=rt["defe"].get(H, 0),
                       att_a=rt["att"].get(A, 0), def_a=rt["defe"].get(A, 0))

    # statistiche
    m["stats_home"] = analysis.team_stats(H, hist.get(H), fd_rows, us2fd.get(H))
    m["stats_away"] = analysis.team_stats(A, hist.get(A), fd_rows, us2fd.get(A))

    # formazioni e assenze
    g_fc = analysis.find_game(fc, H, A, teams) if fc else None
    g_rw = analysis.find_game(rw, H, A, teams) if rw else None
    src_name = "Fantacalcio.it" if g_fc else ("RotoWire" if g_rw else None)
    g = g_fc or g_rw
    m["lineup_source"] = src_name
    for side, team, key in (("home", H, "abs_home"), ("away", A, "abs_away")):
        sd = (g or {}).get("sides", {}).get(side) or dict(status="n.d.", lineup=[], absent=[])
        if g_fc and g_rw and not sd["lineup"]:
            sd = g_rw["sides"].get(side, sd)
        games = m["stats_home" if side == "home" else "stats_away"]["played"] or 1
        att_mult, def_mult, details = model.absence_effect(sd["absent"], pl.get(team, []), games)
        m[key] = dict(att_mult=att_mult, def_mult=def_mult, details=details)
        m["lineup_" + side] = sd

    # meteo
    ev = next((e for e in espn_ev if e["us_home"] == H and e["us_away"] == A), None)
    m["venue"] = (ev or {}).get("venue")
    m["city"] = (ev or {}).get("city")
    wx = None
    if ev and ev.get("city"):
        ll = sources.geocode(ev["city"], L["country"])
        if ll:
            wx = sources.weather_at(ll[0], ll[1], fx["when"])
    m["weather"] = wx
    wmult, m["weather_text"] = model.weather_effect(wx)
    m["weather_mult"] = wmult

    # possesso palla (ESPN)
    m["possession"] = {}
    if ev:
        try:
            pos = sources.espn_possession(L["espn"], ev["id"], budget)
            if ev.get("home_id") and str(ev["home_id"]) in pos:
                m["possession"][H] = pos[str(ev["home_id"])]
            if ev.get("away_id") and str(ev["away_id"]) in pos:
                m["possession"][A] = pos[str(ev["away_id"])]
        except Exception:
            pass

    lh1 = lh0 * m["abs_home"]["att_mult"] * m["abs_away"]["def_mult"] * wmult
    la1 = la0 * m["abs_away"]["att_mult"] * m["abs_home"]["def_mult"] * wmult
    m["lh_base"], m["la_base"] = lh0, la0

    # quote reali
    od = None
    for r in odds_rows:
        if r["us_home"] == H and r["us_away"] == A and abs((r["date"] - fx["when"].date()).days) <= 1:
            od = r["odds"]
            break
    m["odds"] = od
    lh, la, market = model.blend_with_market(lh1, la1, od)
    m["lh"], m["la"], m["market"] = lh, la, market
    M = model.score_matrix(lh, la)
    Mht = model.score_matrix(lh * config.HT_SHARE, la * config.HT_SHARE, rho=0.0)
    m["p1x2"] = model.p1x2(M)
    m["p1x2_model"] = model.p1x2(model.score_matrix(lh1, la1))
    m["markets"] = model.all_markets(M, Mht)
    m["mk"] = {x["name"]: x for x in m["markets"]}
    flat = [(M[i, j], i, j) for i in range(7) for j in range(7)]
    flat.sort(reverse=True)
    m["exact"] = [dict(score=f"{i}-{j}", p=p, fair=round(1 / p, 1)) for p, i, j in flat[:6]]
    ph, pa = M.sum(axis=1), M.sum(axis=0)
    i = np.arange(M.shape[0])
    ptot = np.array([M[(i[:, None] + i[None, :]) == k].sum() for k in range(M.shape[0])])
    m["goals_home"] = dict(dist=[float(x) for x in ph[:6]], rng=model.goal_range(ph), mode=int(ph.argmax()))
    m["goals_away"] = dict(dist=[float(x) for x in pa[:6]], rng=model.goal_range(pa), mode=int(pa.argmax()))
    m["goals_tot"] = dict(dist=[float(x) for x in ptot[:8]], rng=model.goal_range(ptot), mode=int(ptot.argmax()))
    m["top"] = picks.top_picks(m["markets"], od)

    rel, why = 100, []
    if min(m["stats_home"]["played"], m["stats_away"]["played"]) < 4:
        rel -= 25; why.append("poche partite giocate")
    if not src_name:
        rel -= 15; why.append("formazioni e assenze non disponibili")
    if not od:
        rel -= 10; why.append("quote reali non disponibili")
    if not wx:
        rel -= 5; why.append("meteo non disponibile")
    m["reliability"], m["reliability_why"] = rel, why
    m["analysis"] = analysis.write_analysis(m)
    return m


if __name__ == "__main__":
    run()
