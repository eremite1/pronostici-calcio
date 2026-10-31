"""Impostazioni generali del sistema di pronostici."""
import datetime as dt
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
CACHE = os.path.join(DATA, "cache")
DOCS = os.path.join(ROOT, "docs")
TEMPLATES = os.path.join(ROOT, "templates")
TZ = "Europe/Rome"

LEAGUES = [
    dict(key="serie_a", name="Serie A", flag="🇮🇹", understat="Serie_A", fd="I1", espn="ita.1",
         rotowire=["SERI", "ITA", "SERIEA"], country="IT"),
    dict(key="premier", name="Premier League", flag="🏴󠁧󠁢󠁥󠁮󠁧󠁿", understat="EPL", fd="E0", espn="eng.1",
         rotowire=["EPL"], country="GB"),
    dict(key="liga", name="LaLiga", flag="🇪🇸", understat="La_liga", fd="SP1", espn="esp.1",
         rotowire=["LIGA"], country="ES"),
    dict(key="bundesliga", name="Bundesliga", flag="🇩🇪", understat="Bundesliga", fd="D1", espn="ger.1",
         rotowire=["BUND", "GER", "BUN"], country="DE"),
    dict(key="ligue1", name="Ligue 1", flag="🇫🇷", understat="Ligue_1", fd="F1", espn="fra.1",
         rotowire=["FRAN", "LIG1", "FRA", "L1"], country="FR"),
]

# Finestra di partite analizzate: da adesso ai prossimi N giorni
DAYS_AHEAD = 4

# Modello
XG_WEIGHT = 0.70          # peso degli expected goals rispetto ai gol reali nella forza delle squadre
HALF_LIFE_DAYS = 250      # le partite vecchie di 250 giorni contano la metà (tarato sul passato)
RIDGE = 4.0               # prudenza: evita valori estremi quando ci sono poche partite
PROMOTED_PRIOR = (-0.15, -0.12)  # neopromosse: attacco e difesa partono leggermente sotto la media
DC_RHO = -0.10            # correzione Dixon-Coles per i risultati con pochi gol (tarato sul passato)
MARKET_WEIGHT = 0.85      # peso delle quote reali: sul passato le quote si sono rivelate più precise del modello
HT_SHARE = 0.45           # quota dei gol segnati nel primo tempo

# Schedina
SLIP_MIN_ODDS = 2.0
SLIP_MAX_ODDS = 3.0
PICK_MIN_PROB = 0.55
PICK_MIN_ODDS = 1.20
MIN_RELIABILITY = 60
CROSS_MIN_PROB = 0.60     # schedina incrociata: probabilità minima che il NOSTRO modello dà al pronostico di Pengwin


def season_start_year(today=None):
    today = today or dt.date.today()
    return today.year if today.month >= 7 else today.year - 1


def fd_season_code(year):
    return f"{year % 100:02d}{(year + 1) % 100:02d}"
