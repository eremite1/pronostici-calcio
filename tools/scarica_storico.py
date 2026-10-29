"""Scarica gli archivi per la taratura del modello (stagioni passate) e alcuni controlli."""
import os, json, time, requests
OUT = "storico_out"; os.makedirs(OUT, exist_ok=True)
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0"
def save(name, url, headers=None):
    for i in range(3):
        try:
            r = S.get(url, headers=headers or {}, timeout=40)
            if r.status_code == 200:
                open(os.path.join(OUT, name), "wb").write(r.content); print("ok", name, len(r.content)); return
            print("http", r.status_code, name)
        except Exception as e:
            print("err", name, e)
        time.sleep(3)
US = {"Serie_A": "I1", "EPL": "E0", "La_liga": "SP1", "Bundesliga": "D1", "Ligue_1": "F1"}
for lg, fd in US.items():
    for y in range(2019, 2027):
        save(f"us_{lg}_{y}.json", f"https://understat.com/getLeagueData/{lg}/{y}",
             {"X-Requested-With": "XMLHttpRequest", "Referer": f"https://understat.com/league/{lg}/{y}"})
        save(f"fd_{fd}_{y}.csv", f"https://www.football-data.co.uk/mmz4281/{y%100:02d}{(y+1)%100:02d}/{fd}.csv")
for d in ["20261028", "20261031", "20261027"]:
    for lg in ["fra.1", "ita.1"]:
        save(f"espn_{lg}_{d}.json", f"https://site.api.espn.com/apis/site/v2/sports/soccer/{lg}/scoreboard?dates={d}")
