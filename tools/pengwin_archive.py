"""Legge l'archivio dei pronostici di Kristian Pengwin (Mondo Pengwin) per la verifica sul passato.
Salva solo: url, data, partita, frase finale del pronostico (non gli articoli interi)."""
import html, json, os, re, sys, time
import requests

OUT = "storico_out"; os.makedirs(OUT, exist_ok=True)
S = requests.Session()
S.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"
LG = r"(serie-a|premier-league|la-liga|bundesliga|ligue-1)"
MESI = {m: i + 1 for i, m in enumerate(["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
                                        "agosto", "settembre", "ottobre", "novembre", "dicembre"])}


def text(h):
    h = re.sub(r"<script.*?</script>|<style.*?</style>", " ", h, flags=re.S)
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h))).strip()


def extract(h):
    r = {}
    t = re.search(r"<h1[^>]*>(.*?)</h1>", h, re.S)
    r["title"] = text(t.group(1)) if t else ""
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
    body = text(seg)
    sents = re.split(r"(?<=[.!?])\s+(?=[A-ZÈÀ])", body)
    tip = ""
    for s in reversed(sents):
        if re.search(r"quota|esito|segno|punto|gioco|puntiamo|consiglio|opzione|scelta", s, re.I):
            tip = s
            break
    r["tip"] = tip[-300:]
    r["bold"] = [text(b)[:80] for b in re.findall(r"<strong>(.*?)</strong>", seg, re.S)][-3:]
    return r


def main():
    sm = S.get("https://www.mondopengwin.it/sitemap.xml", timeout=60).text
    items = re.findall(r"<url><loc>([^<]+)</loc><lastmod>([^<]+)</lastmod>", sm)
    urls = [(u, l) for u, l in items if re.match(r"https://www.mondopengwin.it/pronostici/calcio/" + LG + "/.+", u)
            and l[:10] >= sys.argv[1]]
    print("articoli:", len(urls), flush=True)
    out = open(os.path.join(OUT, "pengwin_tips.jsonl"), "w", encoding="utf-8")
    t0 = time.time()
    for k, (u, l) in enumerate(urls):
        try:
            r = S.get(u, timeout=30)
            if r.status_code == 200:
                d = extract(r.text)
                d.update(url=u, lastmod=l)
                out.write(json.dumps(d, ensure_ascii=False) + "\n")
            else:
                print("http", r.status_code, u)
        except Exception as e:
            print("err", u, e)
        if k % 200 == 0:
            print(k, round(time.time() - t0), flush=True); out.flush()
        time.sleep(0.8)
    out.close()


if __name__ == "__main__":
    main()
