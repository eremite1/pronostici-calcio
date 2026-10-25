"""Script di prova: controlla quali fonti dati rispondono da GitHub e salva dei campioni."""
import json, os, re, sys, datetime as dt
import requests

OUT = "probe_out"
os.makedirs(OUT, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
      "Accept-Language": "it-IT,it;q=0.9,en;q=0.8"}
today = dt.date.today()

def get(name, url, headers=None, show=600):
    h = dict(UA); h.update(headers or {})
    try:
        r = requests.get(url, headers=h, timeout=30)
        txt = r.text
        with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
            f.write(txt)
        print(f"\n===== {name} | {r.status_code} | {len(txt)} chars | {url}")
        print(txt[:show].replace("\r", ""))
        return r
    except Exception as e:
        print(f"\n===== {name} | ERRORE {e} | {url}")

get("fd_fixtures.csv", "https://www.football-data.co.uk/fixtures.csv", show=1500)
for code in ["I1", "E0", "SP1", "D1", "F1"]:
    get(f"fd_2627_{code}.csv", f"https://www.football-data.co.uk/mmz4281/2627/{code}.csv", show=700)
get("fd_2526_I1.csv", "https://www.football-data.co.uk/mmz4281/2526/I1.csv", show=300)

r = get("us_league_page.html", "https://understat.com/league/Serie_A/2026", show=300)
if r is not None:
    for var in ["datesData", "teamsData", "playersData"]:
        m = re.search(var + r"\s*=\s*JSON\.parse\('(.+?)'\)", r.text)
        print(var, "trovato nel html" if m else "NON trovato nel html")
get("us_getLeagueData.json", "https://understat.com/getLeagueData/Serie_A/2026",
    headers={"X-Requested-With": "XMLHttpRequest", "Referer": "https://understat.com/league/Serie_A/2026"}, show=800)

get("om.json", "https://api.open-meteo.com/v1/forecast?latitude=41.93&longitude=12.45&hourly=temperature_2m,precipitation,wind_speed_10m&forecast_days=7", show=300)
get("om_geo.json", "https://geocoding-api.open-meteo.com/v1/search?name=Bergamo&count=1", show=300)

r = get("espn_scoreboard.json", "https://site.api.espn.com/apis/site/v2/sports/soccer/ita.1/scoreboard", show=300)
try:
    ev = r.json()["events"]
    print("ESPN eventi:", [(e["id"], e["name"], e["date"]) for e in ev[:5]])
    eid = ev[0]["id"]
    s = get("espn_summary.json", f"https://site.api.espn.com/apis/site/v2/sports/soccer/ita.1/summary?event={eid}", show=200)
    sj = s.json()
    print("ESPN summary chiavi:", list(sj.keys()))
    for k in ["rosters", "injuries", "odds", "gameInfo"]:
        if k in sj:
            print(k, json.dumps(sj[k])[:700])
except Exception as e:
    print("ESPN parse errore", e)
d = (today + dt.timedelta(days=0)).strftime("%Y%m%d")
get("espn_scoreboard_dates.json", f"https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/scoreboard?dates={d}-{(today+dt.timedelta(days=7)).strftime('%Y%m%d')}", show=200)

get("clubelo_fixtures.csv", "http://api.clubelo.com/Fixtures", show=800)
get("clubelo_today.csv", f"http://api.clubelo.com/{today.isoformat()}", show=300)

get("tm_injuries.html", "https://www.transfermarkt.it/serie-a/verletztespieler/wettbewerb/IT1", show=200)
get("fc_probabili.html", "https://www.fantacalcio.it/probabili-formazioni-serie-a", show=200)
get("sofa_events.json", f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{today.isoformat()}", show=300)
get("fbref_seriea.html", "https://fbref.com/en/comps/11/Serie-A-Stats", show=200)
