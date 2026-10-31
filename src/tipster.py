"""Pronostici di Kristian Pengwin (mondopengwin.it): lettura e traduzione nei mercati del nostro sistema."""
import datetime as dt
import html
import re
import time

from . import names
from .fetch import get_text, load_cache, save_cache

BASE = "https://www.mondopengwin.it"
LEAGUE_PATH = {"serie_a": "serie-a", "premier": "premier-league", "liga": "la-liga", "bundesliga": "bundesliga",
               "ligue1": "ligue-1"}
MESI = {m: i + 1 for i, m in enumerate(["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
                                        "agosto", "settembre", "ottobre", "novembre", "dicembre"])}

# nomi italiani delle squadre straniere -> nome Understat
IT_ALIASES = {
    "barcellona": "Barcelona", "siviglia": "Sevilla", "maiorca": "Mallorca", "saragozza": "Real Zaragoza",
    "atletico": "Atletico Madrid", "athletic": "Athletic Club", "valladolid": "Real Valladolid",
    "bayern monaco": "Bayern Munich", "bayern": "Bayern Munich", "lipsia": "RasenBallsport Leipzig",
    "friburgo": "Freiburg", "stoccarda": "VfB Stuttgart", "francoforte": "Eintracht Frankfurt",
    "eintracht francoforte": "Eintracht Frankfurt", "colonia": "FC Cologne", "amburgo": "Hamburger SV",
    "werder brema": "Werder Bremen", "brema": "Werder Bremen", "union berlino": "Union Berlin",
    "hertha berlino": "Hertha Berlin", "magonza": "Mainz 05", "augusta": "Augsburg", "borussia dortmund": "Borussia Dortmund",
    "borussia monchengladbach": "Borussia M.Gladbach", "monchengladbach": "Borussia M.Gladbach",
    "bayer leverkusen": "Bayer Leverkusen", "norimberga": "Nurnberg", "hannover": "Hannover 96",
    "arminia bielefeld": "Arminia Bielefeld", "heidenheim": "FC Heidenheim", "st pauli": "St. Pauli",
    "marsiglia": "Marseille", "lione": "Lyon", "nizza": "Nice", "lilla": "Lille", "strasburgo": "Strasbourg",
    "tolosa": "Toulouse", "psg": "Paris Saint Germain", "paris saint germain": "Paris Saint Germain",
    "saint etienne": "Saint-Etienne", "nantes": "Nantes", "rennes": "Rennes",
    "manchester utd": "Manchester United", "man utd": "Manchester United", "nottingham": "Nottingham Forest",
    "wolverhampton": "Wolverhampton Wanderers", "wolves": "Wolverhampton Wanderers", "sheffield utd": "Sheffield United",
    "leeds united": "Leeds", "ipswich town": "Ipswich", "hull city": "Hull", "coventry city": "Coventry",
    "inter": "Inter", "milan": "AC Milan", "hellas verona": "Verona", "parma": "Parma Calcio 1913",
}
_IT = {names.norm(k): v for k, v in IT_ALIASES.items()}


def team(name, candidates):
    n = names.norm(name)
    if n in _IT and _IT[n] in candidates:
        return _IT[n]
    return names.match_team(name, candidates)


def split_title(title, candidates):
    """'SASSUOLO-FIORENTINA: STATISTICHE...' -> (casa, ospite) nei nomi Understat."""
    t = title.split(":")[0]
    t = re.sub(r"(?i)\b(pronostico|pronostici|calcio|quote|statistiche|e)\b", " ", t).strip(" -")
    parts = t.split("-")
    for i in range(1, len(parts)):
        h, a = "-".join(parts[:i]).strip(), "-".join(parts[i:]).strip()
        th, ta = team(h, candidates), team(a, candidates)
        if th and ta and th != ta:
            return th, ta
    return None


# ------------------------------------------------------------------ dal testo al mercato

def _num(s):
    return s.replace(",", ".")


def parse_tip(sentence, bold=(), home="", away=""):
    """Restituisce (nome mercato del nostro sistema, quota) oppure (None, quota) se non riconosciuto."""
    s = html.unescape(sentence or "")
    odds = None
    m = re.search(r"quota\s*(?:di\s*|pari a\s*|a\s*)?(\d{1,2}[.,]\d{1,2})", s, re.I)
    if m:
        odds = float(_num(m.group(1)))
    # porzione con il pronostico: il grassetto o il testo dopo "esito/segno/opzione/sul/sulla"
    cand = [b for b in bold if b.strip()] + [s]
    for c in cand:
        mk = to_market(c, home, away)
        if mk:
            return mk, odds
    return None, odds


TOKEN = re.compile(
    r"(?P<mg>multi\s?go(?:a)?l\s*(?P<mgs1>casa|ospite|trasferta)?\s*(?P<lo>\d)\s*-\s*(?P<hi>\d)\s*(?P<mgs2>casa|ospite|trasferta)?)"
    r"|(?P<pt>(?:primo tempo|1° tempo|1t)\s*(?P<ptou>over|under)\s*(?P<ptl>\d\.5))"
    r"|(?P<ou>(?P<ous1>casa|ospite|trasferta)?\s*(?P<ouw>over|under)\s*(?P<oul>\d\.5)\s*(?P<ous2>casa|ospite|trasferta)?)"
    r"|(?P<ng>no\s?goal)"
    r"|(?P<gg>\bgoal\b)"
    r"|(?P<dc>doppia chance\s*(?P<dcv>1x|x2|12))"
    r"|(?P<win>(?:vittoria|successo|affermazione|colpo)\s+(?:esterno\s+|interno\s+)?(?:della|del|dello|dell'|di|degli|dei)\s*(?P<who>[a-z' ]{3,25}))"
    r"|(?P<draw>\bpareggio\b)"
    r"|(?P<seg>(?<![\d.\-])\b(?P<segv>1x|x2|12|1|x|2)\b(?![\-.]?\d))")


def to_market(text, home="", away=""):
    t = html.unescape(text or "").lower().replace("’", "'")
    t = re.sub(r"(\d),(\d)", r"\1.\2", t)
    t = re.sub(r"\b(?:a |alla |con )?quota\b.*$", "", t)
    kws = list(re.finditer(r"esito|segno|opzione|sull'|sullo |sulla |sul |gioco |punto |scelgo |consiglio |"
                           r"pronostico è|pronostico: |per l'|per il |giocata", t))
    core = t[kws[-1].end():] if kws else t
    core = core.replace("gol/no gol", " ")
    core = re.sub(r"\bgg\b", "goal", core)
    core = re.sub(r"\bng\b", "no goal", core)
    core = re.sub(r"\bgol\b", "goal", core)
    core = re.sub(r"\b(over|under)\s*(\d)\b(?!\.)", r"\1 \2.5", core)
    found = []
    for m in TOKEN.finditer(core):
        g = m.groupdict()
        x = None
        if g["mg"]:
            side = g["mgs1"] or g["mgs2"]
            x = (f"Multigol {'casa' if side == 'casa' else 'ospite'} {g['lo']}-{g['hi']}" if side
                 else f"Multigol {g['lo']}-{g['hi']}")
        elif g["pt"]:
            x = f"1° tempo {g['ptou'].capitalize()} {g['ptl']}"
        elif g["ou"]:
            side = g["ous1"] or g["ous2"]
            x = (f"{'Casa' if side == 'casa' else 'Ospite'} {g['ouw'].capitalize()} {g['oul']}" if side
                 else f"{g['ouw'].capitalize()} {g['oul']}")
        elif g["ng"]:
            x = "No Goal"
        elif g["gg"]:
            x = "Goal"
        elif g["dc"]:
            x = g["dcv"].upper()
        elif g["win"] and home and away:
            who = names.norm(g["who"])
            hn, an = names.norm(home), names.norm(away)
            pref = lambda team_n: any(team_n.startswith(w) for w in who.split() if len(w) > 3)
            if any(w in who for w in hn.split() if len(w) > 2) or pref(hn) or _IT_REV(who) == home:
                x = "1"
            elif any(w in who for w in an.split() if len(w) > 2) or pref(an) or _IT_REV(who) == away:
                x = "2"
        elif g["draw"]:
            x = "X"
        elif g["seg"]:
            x = g["segv"].upper()
        if x:
            found.append(x)
    found = list(dict.fromkeys(found))
    if not found:
        return None
    if len(found) == 1:
        return found[0]
    a, b = found[0], found[1]
    esiti = ["1", "X", "2", "1X", "X2", "12"]
    if a in ("Goal", "No Goal") and b.startswith(("Over", "Under")):
        return f"{a} + {b}"
    if a in esiti and b not in esiti:
        return f"{a} + {b}"
    if b in esiti and a not in esiti:
        return f"{b} + {a}"
    return None


def _IT_REV(who):
    for k, v in _IT.items():
        if k and (k in who or who in k):
            return v
    return None


# ------------------------------------------------------------------ lettura dal vivo

def _text(h):
    h = re.sub(r"<script.*?</script>|<style.*?</style>", " ", h, flags=re.S)
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h))).strip()


def extract(h):
    r = {}
    t = re.search(r"<h1[^>]*>(.*?)</h1>", h, re.S)
    r["title"] = _text(t.group(1)) if t else ""
    p = re.search(r"Pubblicato il (\d{1,2}) (\w+) (\d{4})", h)
    if p and p.group(2).lower() in MESI:
        r["published"] = f"{p.group(3)}-{MESI[p.group(2).lower()]:02d}-{int(p.group(1)):02d}"
    i = h.find("Analisi e pronostico")
    if i < 0:
        i = h.find("pronostico di Kristian")
    seg = h[i:i + 8000] if i >= 0 else ""
    end = seg.find("Per non perderti")
    if end > 0:
        seg = seg[:end]
    body = _text(seg)
    sents = re.split(r"(?<=[.!?])\s+(?=[A-ZÈÀ])", body)
    tip = ""
    for s in reversed(sents):
        if re.search(r"quota|esito|segno|punto|gioco|puntiamo|consiglio|opzione|scelta", s, re.I):
            tip = s
            break
    r["tip"] = tip[-300:]
    r["bold"] = [_text(b)[:80] for b in re.findall(r"<strong>(.*?)</strong>", seg, re.S)][-3:]
    return r


def recent_articles(days=6):
    sm = get_text(BASE + "/sitemap.xml", tries=4, timeout=90)
    if not sm:
        return None
    since = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    out = []
    for u, l in re.findall(r"<url><loc>([^<]+)</loc><lastmod>([^<]+)</lastmod>", sm):
        m = re.match(BASE + r"/pronostici/calcio/([a-z0-9-]+)/(.+)", u)
        if m and l[:10] >= since:
            out.append(dict(url=u, lastmod=l, league_path=m.group(1)))
    return out


def tips_for(league_key, fixtures, teams, articles):
    """Pronostici Pengwin per le partite in programma di un campionato. fixtures: lista dict id, home, away, when."""
    if articles is None:
        return {}
    path = LEAGUE_PATH[league_key]
    cache = load_cache("pengwin.json", {})
    res = {}
    for a in articles:
        if a["league_path"] != path:
            continue
        c = cache.get(a["url"])
        if not c or c.get("lastmod") != a["lastmod"]:
            h = get_text(a["url"], tries=3)
            time.sleep(0.5)
            if not h:
                continue
            c = extract(h)
            c["lastmod"] = a["lastmod"]
            cache[a["url"]] = c
        ht = split_title(c.get("title", ""), teams)
        if not ht:
            continue
        for fx in fixtures:
            if (fx["home"], fx["away"]) != ht:
                continue
            pub = c.get("published") or a["lastmod"][:10]
            if not (-2 <= (fx["when"].date() - dt.date.fromisoformat(pub)).days <= 10):
                continue
            mk, odds = parse_tip(c.get("tip", ""), c.get("bold", []), fx["home"], fx["away"])
            res[fx["id"]] = dict(market=mk, odds=odds, url=a["url"], raw=c.get("tip", ""))
    # tieni la cache piccola
    keep = {a["url"] for a in articles}
    save_cache("pengwin.json", {k: v for k, v in cache.items() if k in keep})
    return res
