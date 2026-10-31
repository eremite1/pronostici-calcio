import os, re, requests
OUT = "storico_out"; os.makedirs(OUT, exist_ok=True)
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"
urls = {
 "robots.txt": "https://www.mondopengwin.it/robots.txt",
 "sitemap.xml": "https://www.mondopengwin.it/sitemap.xml",
 "sitemap_index.xml": "https://www.mondopengwin.it/sitemap_index.xml",
 "serie_a.html": "https://www.mondopengwin.it/pronostici/calcio/serie-a/",
 "calcio.html": "https://www.mondopengwin.it/pronostici/calcio/",
 "home.html": "https://www.mondopengwin.it/",
 "feed.xml": "https://www.mondopengwin.it/feed/",
 "wpjson.json": "https://www.mondopengwin.it/wp-json/wp/v2/posts?per_page=5",
 "article.html": "https://www.mondopengwin.it/pronostici/calcio/serie-a/sassuolo-fiorentina-statistiche-quote-e-pronostico-2026",
}
for n, u in urls.items():
    try:
        r = S.get(u, timeout=30)
        open(os.path.join(OUT, n), "wb").write(r.content)
        print(n, r.status_code, len(r.content), r.headers.get("content-type"))
    except Exception as e:
        print(n, "ERR", e)
