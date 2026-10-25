"""Script di prova 2: fonti per assenze e formazioni degli altri campionati."""
import json, os, re, datetime as dt
import requests

OUT = "probe_out"
os.makedirs(OUT, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
      "Accept-Language": "it-IT,it;q=0.9,en;q=0.8"}
today = dt.date.today()

def get(name, url, headers=None, show=400):
    h = dict(UA); h.update(headers or {})
    try:
        r = requests.get(url, headers=h, timeout=30)
        with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
            f.write(r.text)
        print(f"\n===== {name} | {r.status_code} | {len(r.text)} chars | {url}")
        print(r.text[:show].replace("\r", ""))
        return r
    except Exception as e:
        print(f"\n===== {name} | ERRORE {e} | {url}")

get("rw_epl.html", "https://www.rotowire.com/soccer/lineups.php?league=EPL")
get("rw_liga.html", "https://www.rotowire.com/soccer/lineups.php?league=LIGA")
get("rw_inj_epl.html", "https://www.rotowire.com/soccer/injury-report.php?league=EPL")
get("sg_inj_epl.html", "https://www.sportsgambler.com/injuries/football/england-premier-league/")
get("sg_lu_epl.html", "https://www.sportsgambler.com/lineups/football/england-premier-league/")
get("espn_roster.json", "https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/teams/359/roster", show=200)
get("espn_core_inj.json", "https://sports.core.api.espn.com/v2/sports/soccer/leagues/eng.1/teams/359/injuries", show=400)
get("fc_premier.html", "https://www.fantacalcio.it/probabili-formazioni-premier-league", show=200)
d1 = (today + dt.timedelta(days=1)).strftime("%Y%m%d")
get("espn_eng_day.json", f"https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/scoreboard?dates={d1}", show=200)
for lg in ["esp.1", "ger.1", "fra.1"]:
    get(f"espn_{lg}.json", f"https://site.api.espn.com/apis/site/v2/sports/soccer/{lg}/scoreboard", show=150)
for lg in ["EPL", "La_liga", "Bundesliga", "Ligue_1"]:
    get(f"us_{lg}.json", f"https://understat.com/getLeagueData/{lg}/2026",
        headers={"X-Requested-With": "XMLHttpRequest", "Referer": f"https://understat.com/league/{lg}/2026"}, show=100)
for lg in ["EPL", "Serie_A"]:
    get(f"us_{lg}_2025.json", f"https://understat.com/getLeagueData/{lg}/2025",
        headers={"X-Requested-With": "XMLHttpRequest", "Referer": f"https://understat.com/league/{lg}/2025"}, show=100)
