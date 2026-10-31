import requests, time
U = "https://www.mondopengwin.it/sitemap.xml"
A = "https://www.mondopengwin.it/pronostici/calcio/serie-a/sassuolo-fiorentina-statistiche-quote-e-pronostico-2026"
for lab, h in [("plain", {}), ("ua1", {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"}),
               ("ua2+lang", {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36", "Accept-Language": "it-IT,it;q=0.9,en;q=0.8"})]:
    for u in (U, A):
        r = requests.get(u, headers=h, timeout=60)
        print(lab, u[-30:], r.status_code, len(r.content), {k: v for k, v in r.headers.items() if k.lower().startswith(("x-", "server", "retry"))})
        time.sleep(2)
