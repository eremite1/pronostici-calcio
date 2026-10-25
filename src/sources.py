"""Lettura di tutte le fonti dati (ognuna è indipendente: se una non risponde, le altre vanno avanti)."""
import csv
import datetime as dt
import html as htmlmod
import io
import re
import time

from bs4 import BeautifulSoup

from . import config, names
from .fetch import get_text, get_json, load_cache, save_cache, warn

UTC = dt.timezone.utc


def _f(x, default=None):
    try:
        if x is None or x == "":
            return default
        return float(x)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------- Understat (xG, calendario, giocatori)

def understat_league(code, season, use_cache=False):
    cname = f"understat_{code}_{season}.json"
    if use_cache:
        c = load_cache(cname)
        if c:
            return c
    url = f"https://understat.com/getLeagueData/{code}/{season}"
    d = get_json(url, headers={"X-Requested-With": "XMLHttpRequest",
                               "Referer": f"https://understat.com/league/{code}/{season}"})
    if d and use_cache:
        save_cache(cname, d)
    return d


def understat_matches(data):
    """Lista partite giocate e da giocare, con orari in UTC."""
    out = []
    for m in (data or {}).get("dates", []):
        try:
            when = dt.datetime.strptime(m["datetime"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
        except Exception:
            continue
        r = dict(id=str(m["id"]), home=m["h"]["title"], away=m["a"]["title"], when=when,
                 played=bool(m.get("isResult")))
        if r["played"]:
            r.update(hg=int(m["goals"]["h"]), ag=int(m["goals"]["a"]),
                     hxg=_f(m["xG"]["h"], 0.0), axg=_f(m["xG"]["a"], 0.0))
        out.append(r)
    return out


def understat_team_history(data):
    """Per ogni squadra: elenco partite con xG, xGA, PPDA, ecc."""
    out = {}
    for t in (data or {}).get("teams", {}).values():
        rows = []
        for h in t.get("history", []):
            ppda = h.get("ppda") or {}
            rows.append(dict(
                date=h.get("date", "")[:10], h_a=h.get("h_a"), xg=_f(h.get("xG"), 0), xga=_f(h.get("xGA"), 0),
                scored=int(h.get("scored", 0)), missed=int(h.get("missed", 0)), result=h.get("result"),
                ppda=(_f(ppda.get("att"), 0) / _f(ppda.get("def"), 1)) if _f(ppda.get("def")) else None,
                deep=_f(h.get("deep"), 0), deep_allowed=_f(h.get("deep_allowed"), 0)))
        rows.sort(key=lambda r: r["date"])
        out[t["title"]] = rows
    return out


# ---------------------------------------------------------------- football-data.co.uk (tiri, quote reali)

def _fd_rows(text):
    if not text:
        return []
    text = text.replace("ï»¿", "").lstrip("﻿")
    return list(csv.DictReader(io.StringIO(text)))


def fd_season(code, season_year):
    url = f"https://www.football-data.co.uk/mmz4281/{config.fd_season_code(season_year)}/{code}.csv"
    rows = _fd_rows(get_text(url))
    out = []
    for r in rows:
        if not r.get("HomeTeam") or r.get("FTHG") in (None, ""):
            continue
        try:
            date = dt.datetime.strptime(r["Date"], "%d/%m/%Y").date()
        except Exception:
            try:
                date = dt.datetime.strptime(r["Date"], "%d/%m/%y").date()
            except Exception:
                continue
        out.append(dict(date=date, home=r["HomeTeam"], away=r["AwayTeam"],
                        hg=int(_f(r.get("FTHG"), 0)), ag=int(_f(r.get("FTAG"), 0)),
                        hthg=_f(r.get("HTHG")), htag=_f(r.get("HTAG")),
                        hs=_f(r.get("HS")), as_=_f(r.get("AS")), hst=_f(r.get("HST")), ast=_f(r.get("AST")),
                        hc=_f(r.get("HC")), ac=_f(r.get("AC"))))
    return out


_FIXTURES_CACHE = {}


def fd_fixture_odds(div):
    """Quote medie reali dei bookmaker per le prossime partite (file fixtures.csv)."""
    if "rows" not in _FIXTURES_CACHE:
        _FIXTURES_CACHE["rows"] = _fd_rows(get_text("https://www.football-data.co.uk/fixtures.csv"))
        if not _FIXTURES_CACHE["rows"]:
            warn("Quote reali non disponibili (football-data fixtures.csv non raggiungibile)")
    out = []
    for r in _FIXTURES_CACHE["rows"]:
        if r.get("Div") != div:
            continue
        try:
            date = dt.datetime.strptime(r["Date"], "%d/%m/%Y").date()
        except Exception:
            continue
        o = dict(H=_f(r.get("AvgH")), D=_f(r.get("AvgD")), A=_f(r.get("AvgA")),
                 O25=_f(r.get("Avg>2.5")), U25=_f(r.get("Avg<2.5")),
                 maxH=_f(r.get("MaxH")), maxD=_f(r.get("MaxD")), maxA=_f(r.get("MaxA")),
                 maxO25=_f(r.get("Max>2.5")), maxU25=_f(r.get("Max<2.5")))
        if not o["H"]:
            o["H"], o["D"], o["A"] = _f(r.get("B365H")), _f(r.get("B365D")), _f(r.get("B365A"))
        if not o["O25"]:
            o["O25"], o["U25"] = _f(r.get("B365>2.5")), _f(r.get("B365<2.5"))
        out.append(dict(date=date, home=r["HomeTeam"], away=r["AwayTeam"], odds=o))
    return out


# ---------------------------------------------------------------- ESPN (stadio, città, possesso palla)

def espn_events(espn_code, day):
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{espn_code}/scoreboard?dates={day:%Y%m%d}"
    d = get_json(url, tries=2)
    out = []
    for e in (d or {}).get("events", []):
        try:
            comp = e["competitions"][0]
            teams = {c["homeAway"]: c["team"] for c in comp["competitors"]}
            venue = comp.get("venue") or {}
            addr = venue.get("address") or {}
            out.append(dict(id=e["id"], when=e.get("date"), home=teams["home"]["displayName"],
                            away=teams["away"]["displayName"], home_id=teams["home"].get("id"),
                            away_id=teams["away"].get("id"), venue=venue.get("fullName"),
                            city=addr.get("city"), country=addr.get("country")))
        except Exception:
            continue
    return out


def espn_possession(espn_code, event_id, budget):
    """Possesso medio delle ultime partite delle due squadre (usa una cache per non riscaricare)."""
    cache = load_cache("espn_stats.json", {})
    summ = get_json(f"https://site.api.espn.com/apis/site/v2/sports/soccer/{espn_code}/summary?event={event_id}",
                    tries=2)
    res = {}
    if not summ:
        return res
    for block in summ.get("lastFiveGames", []) or []:
        tid = str((block.get("team") or {}).get("id"))
        vals, shots = [], []
        for ev in block.get("events", []) or []:
            eid = str(ev.get("id"))
            if not eid or eid == "None":
                continue
            if eid not in cache and budget[0] > 0:
                budget[0] -= 1
                s = None
                for lg in (espn_code, "all"):
                    s = get_json(f"https://site.api.espn.com/apis/site/v2/sports/soccer/{lg}/summary?event={eid}",
                                 tries=1)
                    if s:
                        break
                stats = {}
                for t in ((s or {}).get("boxscore") or {}).get("teams", []) or []:
                    st = {x.get("name"): x.get("displayValue") for x in t.get("statistics", []) or []}
                    stats[str(t["team"]["id"])] = dict(pos=_f(st.get("possessionPct")),
                                                       shots=_f(st.get("totalShots")),
                                                       sot=_f(st.get("shotsOnTarget")))
                cache[eid] = stats
                time.sleep(0.15)
            st = (cache.get(eid) or {}).get(tid)
            if st and st.get("pos") is not None:
                vals.append(st["pos"])
        if vals:
            res[tid] = round(sum(vals) / len(vals), 1)
    save_cache("espn_stats.json", cache)
    return res


# ---------------------------------------------------------------- Open-Meteo (meteo all'ora della partita)

def geocode(city, country):
    if not city:
        return None
    cache = load_cache("geo.json", {})
    key = f"{city}|{country}"
    if key in cache:
        return cache[key]
    res = None
    for cc in (country, None):
        url = "https://geocoding-api.open-meteo.com/v1/search?count=1&language=en&name=" + requests_quote(city)
        if cc:
            url += f"&countryCode={cc}"
        d = get_json(url, tries=2)
        if d and d.get("results"):
            r = d["results"][0]
            res = [r["latitude"], r["longitude"]]
            break
    cache[key] = res
    save_cache("geo.json", cache)
    return res


def requests_quote(s):
    from urllib.parse import quote
    return quote(s)


def weather_at(lat, lon, kickoff):
    url = ("https://api.open-meteo.com/v1/forecast?latitude=%.4f&longitude=%.4f"
           "&hourly=temperature_2m,precipitation,snowfall,wind_speed_10m,wind_gusts_10m,relative_humidity_2m,weather_code"
           "&timezone=UTC&forecast_days=8" % (lat, lon))
    d = get_json(url, tries=2)
    if not d or "hourly" not in d:
        return None
    h = d["hourly"]
    times = h["time"]
    start = kickoff.replace(minute=0, second=0, microsecond=0)
    idx = []
    for k in range(3):  # ora d'inizio e le due successive
        key = (start + dt.timedelta(hours=k)).strftime("%Y-%m-%dT%H:00")
        if key in times:
            idx.append(times.index(key))
    if not idx:
        return None

    def avg(name):
        vals = [h[name][i] for i in idx if h.get(name) and h[name][i] is not None]
        return sum(vals) / len(vals) if vals else None

    return dict(temp=avg("temperature_2m"), rain=avg("precipitation"), snow=avg("snowfall"),
                wind=avg("wind_speed_10m"), gust=avg("wind_gusts_10m"), hum=avg("relative_humidity_2m"),
                code=h["weather_code"][idx[0]] if h.get("weather_code") else None)


# ---------------------------------------------------------------- RotoWire (probabili formazioni e infortuni)

def rotowire(codes, team_names):
    """Prova i codici di campionato finché trova una pagina con le squadre giuste."""
    for code in codes:
        page = get_text(f"https://www.rotowire.com/soccer/lineups.php?league={code}", tries=2)
        if not page or "lineup is-soccer" not in page:
            continue
        games = _parse_rotowire(page)
        hits = sum(1 for g in games if names.match_team(g["home"], team_names))
        if games and hits >= max(1, len(games) // 2):
            return games
    return None


def _parse_rotowire(page):
    out = []
    blocks = page.split('class="lineup is-soccer')[1:]
    for b in blocks:
        b = b[:60000]
        teams = re.findall(r'lineup__mteam is-(home|visit)">\s*([^<]+?)\s*<', b)
        if len(teams) < 2:
            continue
        g = dict(home=htmlmod.unescape(teams[0][1]), away=htmlmod.unescape(teams[1][1]), sides={})
        for side in ("home", "visit"):
            m = re.search(r'<ul class="lineup__list is-%s">(.*?)</ul>' % side, b, re.S)
            if not m:
                continue
            ul = m.group(1)
            status = "confermata" if "is-confirmed" in ul else ("probabile" if "is-expected" in ul else "n.d.")
            parts = re.split(r'lineup__title is-middle', ul, maxsplit=1)
            starters = re.findall(r'lineup__pos[^>]*>\s*([^<]*?)\s*</div>\s*<a title="([^"]+)"', parts[0])
            injured = []
            if len(parts) > 1:
                for li in re.findall(r'<li class="lineup__player">(.*?)</li>', parts[1], re.S):
                    nm = re.search(r'title="([^"]+)"', li)
                    st = re.search(r'lineup__inj">\s*([^<]+?)\s*<', li)
                    pos = re.search(r'lineup__pos[^>]*>\s*([^<]*?)\s*<', li)
                    if nm:
                        injured.append(dict(name=htmlmod.unescape(nm.group(1)),
                                            status=(st.group(1).upper() if st else "OUT"),
                                            pos=pos.group(1) if pos else "", desc=""))
            g["sides"]["home" if side == "home" else "away"] = dict(
                status=status, lineup=[dict(pos=p, name=htmlmod.unescape(n)) for p, n in starters],
                absent=injured)
        out.append(g)
    return out


# ---------------------------------------------------------------- Fantacalcio.it (Serie A)

def fantacalcio():
    page = get_text("https://www.fantacalcio.it/probabili-formazioni-serie-a", tries=2)
    if not page:
        return None
    soup = BeautifulSoup(page, "html.parser")
    out = []
    for li in soup.select("li.match.match-item"):
        try:
            home = li.select_one('[itemprop="homeTeam"] meta[itemprop="name"]')["content"]
            away = li.select_one('[itemprop="awayTeam"] meta[itemprop="name"]')["content"]
        except Exception:
            continue
        g = dict(home=home, away=away, sides={"home": dict(status="probabile", lineup=[], absent=[]),
                                              "away": dict(status="probabile", lineup=[], absent=[])})
        for side, sel in (("home", ".team.team-home"), ("away", ".team.team-away")):
            t = li.select_one(sel)
            if t:
                g["sides"][side]["lineup"] = [dict(pos="", name=s.get_text(strip=True))
                                              for s in t.select(".team-lineup .player-name span")]
        for cls, status in (("suspendeds", "SQUAL"), ("injureds", "OUT"), ("dubts", "QUES")):
            sec = li.select_one(f"section.{cls}")
            if not sec:
                continue
            for i, cont in enumerate(sec.select(":scope > div.content")[:2]):
                side = "home" if i == 0 else "away"
                for item in cont.select("li"):
                    nm = item.select_one(".player-name span")
                    if not nm:
                        continue
                    desc_el = item.select_one(".description")
                    desc = desc_el.get_text(" ", strip=True) if desc_el else ""
                    st = status
                    low = desc.lower()
                    if status == "OUT" and any(k in low for k in ("da valutare", "in dubbio", "recuperabile",
                                                                   "possibile recupero", "convocazione")):
                        st = "QUES"
                    g["sides"][side]["absent"].append(dict(name=nm.get_text(strip=True), status=st, pos="",
                                                           desc=desc))
        out.append(g)
    return out
