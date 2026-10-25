"""Fa combaciare i nomi delle squadre e dei giocatori tra fonti diverse."""
import difflib
import html
import re
import unicodedata

STOP = {"fc", "cf", "ac", "as", "afc", "ssc", "sc", "ss", "us", "rc", "cd", "ud", "sd", "calcio",
        "club", "de", "1913", "1907", "1909", "1919", "the"}

# nome come lo scrive una fonte (normalizzato)  ->  nome Understat
ALIASES = {
    # Premier
    "man city": "Manchester City", "man united": "Manchester United", "man utd": "Manchester United",
    "newcastle": "Newcastle United", "nottm forest": "Nottingham Forest", "nott m forest": "Nottingham Forest",
    "spurs": "Tottenham", "tottenham hotspur": "Tottenham", "brighton and hove albion": "Brighton",
    "brighton hove albion": "Brighton", "bournemouth": "Bournemouth", "wolves": "Wolverhampton Wanderers",
    "wolverhampton": "Wolverhampton Wanderers", "leeds united": "Leeds", "hull city": "Hull",
    "ipswich town": "Ipswich", "coventry city": "Coventry", "west ham united": "West Ham",
    "leicester city": "Leicester", "norwich city": "Norwich", "sheffield united": "Sheffield United",
    "sheffield utd": "Sheffield United", "luton town": "Luton", "stoke city": "Stoke",
    # Serie A
    "milan": "AC Milan", "internazionale": "Inter", "inter milan": "Inter", "parma": "Parma Calcio 1913",
    "hellas verona": "Verona", "roma": "Roma", "pisa sporting": "Pisa",
    # Liga
    "ath bilbao": "Athletic Club", "athletic": "Athletic Club", "athletic bilbao": "Athletic Club",
    "ath madrid": "Atletico Madrid", "atletico": "Atletico Madrid", "atl madrid": "Atletico Madrid",
    "betis": "Real Betis", "celta": "Celta Vigo", "espanol": "Espanyol", "la coruna": "Deportivo La Coruna",
    "deportivo": "Deportivo La Coruna", "deportivo la coruna": "Deportivo La Coruna",
    "santander": "Racing Santander", "racing": "Racing Santander", "sociedad": "Real Sociedad",
    "vallecano": "Rayo Vallecano", "rayo": "Rayo Vallecano", "deportivo alaves": "Alaves",
    "mallorca": "Mallorca", "real mallorca": "Mallorca", "real oviedo": "Real Oviedo", "oviedo": "Real Oviedo",
    "sp gijon": "Sporting Gijon", "real valladolid": "Real Valladolid", "valladolid": "Real Valladolid",
    "girona": "Girona", "las palmas": "Las Palmas", "leganes": "Leganes",
    # Bundesliga
    "dortmund": "Borussia Dortmund", "ein frankfurt": "Eintracht Frankfurt", "fc koln": "FC Cologne",
    "koln": "FC Cologne", "1 fc koln": "FC Cologne", "cologne": "FC Cologne", "hamburg": "Hamburger SV",
    "leverkusen": "Bayer Leverkusen", "mgladbach": "Borussia M.Gladbach", "m gladbach": "Borussia M.Gladbach",
    "borussia monchengladbach": "Borussia M.Gladbach", "monchengladbach": "Borussia M.Gladbach",
    "gladbach": "Borussia M.Gladbach", "rb leipzig": "RasenBallsport Leipzig",
    "leipzig": "RasenBallsport Leipzig", "mainz": "Mainz 05", "fsv mainz 05": "Mainz 05",
    "stuttgart": "VfB Stuttgart", "tsg hoffenheim": "Hoffenheim", "1899 hoffenheim": "Hoffenheim",
    "sc freiburg": "Freiburg", "bayern munchen": "Bayern Munich", "fc bayern": "Bayern Munich",
    "bayern": "Bayern Munich", "hamburger sv": "Hamburger SV", "1 fc union berlin": "Union Berlin",
    "sv werder bremen": "Werder Bremen", "fc augsburg": "Augsburg", "vfl wolfsburg": "Wolfsburg",
    "fc heidenheim": "FC Heidenheim", "heidenheim": "FC Heidenheim", "1 fc heidenheim 1846": "FC Heidenheim",
    "st pauli": "St. Pauli", "fc st pauli": "St. Pauli", "holstein kiel": "Holstein Kiel",
    "sc paderborn 07": "Paderborn", "sv elversberg": "Elversberg", "fc schalke 04": "Schalke 04",
    "schalke": "Schalke 04", "bochum": "Bochum", "darmstadt": "Darmstadt",
    # Ligue 1
    "paris sg": "Paris Saint Germain", "psg": "Paris Saint Germain", "paris saint germain": "Paris Saint Germain",
    "monaco": "Monaco", "as monaco": "Monaco", "aj auxerre": "Auxerre", "le havre ac": "Le Havre",
    "stade rennais": "Rennes", "olympique lyonnais": "Lyon", "olympique lyon": "Lyon",
    "olympique de marseille": "Marseille", "olympique marseille": "Marseille", "stade brestois": "Brest",
    "stade brestois 29": "Brest", "rc lens": "Lens", "rc strasbourg": "Strasbourg",
    "strasbourg alsace": "Strasbourg", "ogc nice": "Nice", "st etienne": "Saint-Etienne",
    "saint etienne": "Saint-Etienne", "losc lille": "Lille", "lille osc": "Lille", "fc nantes": "Nantes",
    "toulouse fc": "Toulouse", "angers sco": "Angers", "fc lorient": "Lorient", "estac troyes": "Troyes",
    "le mans fc": "Le Mans", "fc metz": "Metz", "montpellier hsc": "Montpellier", "stade reims": "Reims",
}


def norm(s):
    s = html.unescape(str(s or ""))
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().replace("&", " and ").replace("'", "").replace("’", "")
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def core(s):
    toks = [t for t in norm(s).split() if t not in STOP]
    return " ".join(toks) if toks else norm(s)


_ALIAS_N = {norm(k): v for k, v in ALIASES.items()}


def match_team(name, candidates):
    """Restituisce il nome tra `candidates` che corrisponde a `name`, oppure None."""
    if not name or not candidates:
        return None
    cands = list(candidates)
    by_norm = {norm(c): c for c in cands}
    by_core = {core(c): c for c in cands}
    n, c = norm(name), core(name)
    if n in by_norm:
        return by_norm[n]
    for key in (n, c):
        tgt = _ALIAS_N.get(key)
        if tgt and tgt in cands:
            return tgt
        if tgt and norm(tgt) in by_norm:
            return by_norm[norm(tgt)]
    if c in by_core:
        return by_core[c]
    # uno contenuto nell'altro (es. "Ipswich Town" / "Ipswich")
    ct = set(c.split())
    hits = [cand for k, cand in by_core.items() if ct and (ct <= set(k.split()) or set(k.split()) <= ct)]
    if len(hits) == 1:
        return hits[0]
    best, score = None, 0.0
    for k, cand in by_core.items():
        r = difflib.SequenceMatcher(None, c, k).ratio()
        if r > score:
            best, score = cand, r
    return best if score >= 0.72 else None


def player_tokens(name):
    return [t for t in norm(name).split() if len(t) > 1]


def match_player(name, players):
    """players: lista di dict con chiave 'player_name'. Restituisce il dict o None."""
    toks = player_tokens(name)
    if not toks:
        return None
    full = norm(name)
    for p in players:
        if norm(p["player_name"]) == full:
            return p
    initials = [t for t in norm(name).split() if len(t) == 1]
    # cognome: il token più lungo, poi tutti gli altri
    cands = []
    for p in players:
        pt = player_tokens(p["player_name"])
        common = set(toks) & set(pt)
        if not common:
            continue
        score = sum(len(t) for t in common)
        if initials and pt and pt[0][0] != initials[0]:
            score -= 3
        cands.append((score, p))
    if not cands:
        return None
    cands.sort(key=lambda x: -x[0])
    if len(cands) > 1 and cands[0][0] == cands[1][0]:
        return None
    return cands[0][1] if cands[0][0] >= 4 else None
